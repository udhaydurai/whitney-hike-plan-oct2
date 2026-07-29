#!/usr/bin/env python3
"""
Verify the built site the way the phone will see it.

Four things that a visual check cannot catch and that all three have bitten this
project before:

  1. JS console errors — a silent throw leaves charts blank on the phone only.
  2. Horizontal overflow at 390px — a single wide table pushes the whole page sideways.
  3. Service worker registration — if this fails, offline does not work and nothing
     on screen says so.
  4. An actual offline reload — registration succeeding is not the same as the shell
     being cached. This drops the network and reloads.

Run: python3 tools/verify_site.py
"""

import http.server
import functools
import pathlib
import socketserver
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "docs"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def serve(directory):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(directory))

    class Quiet(socketserver.TCPServer):
        allow_reuse_address = True

    httpd = Quiet(("127.0.0.1", 0), handler)
    httpd.RequestHandlerClass.log_message = lambda *a, **k: None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def main():
    from playwright.sync_api import sync_playwright

    httpd, base = serve(SITE)
    fails, warns = [], []

    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = br.new_context(viewport={"width": 390, "height": 844},
                             device_scale_factor=3, is_mobile=True,
                             has_touch=True, service_workers="allow")
        pg = ctx.new_page()

        errs, cons = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: cons.append((m.type, m.text)))

        pg.goto(f"{base}/index.html", wait_until="load")
        pg.wait_for_timeout(1500)

        # ── 1. errors
        bad = [t for k, t in cons if k == "error"] + errs
        print(f"1. JS errors                 : {len(bad)}")
        for b in bad[:6]:
            print(f"     {b[:160]}")
        if bad:
            fails.append(f"{len(bad)} JS error(s)")

        # ── 2. overflow
        sw_ = pg.evaluate("document.documentElement.scrollWidth")
        cw = pg.evaluate("document.documentElement.clientWidth")
        print(f"2. Horizontal overflow       : scrollWidth {sw_} vs client {cw}")
        if sw_ > cw + 1:
            wide = pg.evaluate("""() => [...document.querySelectorAll('*')]
                .filter(e => e.getBoundingClientRect().right > %d + 1)
                .slice(0,5).map(e => e.tagName + (e.className ? '.'+e.className : ''))""" % cw)
            print(f"     widest offenders: {wide}")
            fails.append(f"overflows by {sw_ - cw}px")

        # ── 3. service worker
        reg = pg.evaluate("""async () => {
            if (!('serviceWorker' in navigator)) return 'unsupported';
            const r = await navigator.serviceWorker.getRegistration();
            return r ? (r.active ? 'active' : 'registered-not-active') : 'none';
        }""")
        print(f"3. Service worker            : {reg}")
        if reg != "active":
            fails.append(f"service worker {reg}")

        keys = pg.evaluate("async () => (await caches.keys())")
        cached = pg.evaluate("""async () => {
            const ks = await caches.keys();
            if (!ks.length) return [];
            const c = await caches.open(ks[0]);
            return (await c.keys()).map(r => new URL(r.url).pathname);
        }""")
        print(f"   cache buckets             : {keys}")
        print(f"   cached entries            : {len(cached)}")
        for c in cached:
            print(f"     {c}")
        if not any(c.endswith("index.html") for c in cached):
            fails.append("index.html not in the offline cache")

        # ── 4. real offline reload
        #
        # set_offline alone is not enough: Chromium does not always route service
        # worker fetches through the page's network emulation, and the first version
        # of this check logged a live 304 against the server while the page believed
        # it was offline. Killing the server removes the ambiguity — if anything still
        # renders, it came from the cache.
        ctx.set_offline(True)
        httpd.shutdown()
        httpd.server_close()
        try:
            pg.reload(wait_until="load")
            pg.wait_for_timeout(700)
            title = pg.title()
            secs = pg.evaluate("document.querySelectorAll('section').length")
            svgs = pg.evaluate("document.querySelectorAll('svg').length")
            banner = pg.evaluate("""() => {
                const n = document.getElementById('swnote');
                return n && n.style.display !== 'none' ? n.textContent.trim() : '';
            }""")
            print(f"4. Offline reload            : ok — {secs} sections, {svgs} SVGs")
            print(f"   title                     : {title}")
            print(f"   banner                    : {banner or '(hidden)'}")
            if secs < 5:
                fails.append(f"offline reload rendered only {secs} sections")
            if "Offline" not in banner:
                warns.append("offline banner did not say Offline")
        except Exception as e:
            print(f"4. Offline reload            : FAILED — {e}")
            fails.append("offline reload failed")
        ctx.set_offline(False)

        # ── 5. manifest parses and the icons resolve
        import json
        mf = json.loads((SITE / "manifest.webmanifest").read_text())
        missing = [i["src"] for i in mf["icons"] if not (SITE / i["src"]).exists()]
        print(f"5. Manifest                  : {len(mf['icons'])} icons, "
              f"{len(missing)} missing")
        if missing:
            fails.append(f"manifest references missing {missing}")

        pg.screenshot(path=str(ROOT / "verify-mobile.png"), full_page=False)
        br.close()

    print()
    for w in warns:
        print(f"warn  {w}")
    if fails:
        print(f"FAIL  {len(fails)} problem(s):")
        for f in fails:
            print(f"   - {f}")
        sys.exit(1)
    print("PASS  site is mobile-clean, installable and works offline")


if __name__ == "__main__":
    main()
