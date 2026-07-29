#!/usr/bin/env python3
"""
Assemble the deployable site from the built dashboard.

dashboard.py owns the content. This file owns nothing but delivery: it wraps the
built HTML so a phone treats it as an installed app rather than a web page, and so
it opens on a trail with no signal.

Three things get injected that a plain file:// copy does not need:

  * a web app manifest, so "Add to Home Screen" produces an icon and a standalone
    window instead of a browser tab with a URL bar eating 60px of a 390px screen.
  * a service worker, so the second and every later visit is served from the phone's
    own cache. This is the whole point. Trail Camp has no coverage; the dashboard
    still opens.
  * robots noindex, because a GitHub Pages site is readable by anyone who knows the
    URL and there is no reason to help a search engine publish training data.

The cache is versioned by the build stamp. A new build changes CACHE, the worker
drops the old cache on activate, and the phone picks up the new copy the next time
it has signal. Without the version the phone would serve the first build forever.
"""

import hashlib
import pathlib
import re
import shutil
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "docs"
DASH = ROOT / "whitney-dashboard.html"
LOGGER = ROOT / "logger" / "whitney-logger.html"

# ── the head injection. Kept inline rather than in a separate file so a reader can
#    see the whole delivery contract in one place.
HEAD = """<link rel="manifest" href="manifest.webmanifest">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#122436">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Whitney">
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="icon" href="icon.svg" type="image/svg+xml">
"""

# ── the offline banner and worker registration, appended before </body>.
#    The banner is deliberately quiet: it says when the data was built, so a cached
#    copy opened on the trail cannot be mistaken for a live one.
TAIL = """<div id="swnote" style="position:fixed;left:0;right:0;bottom:0;
 background:#122436;color:#cfe3ea;font:11.5px/1.4 -apple-system,BlinkMacSystemFont,
 'Segoe UI',Roboto,sans-serif;padding:7px 12px;text-align:center;z-index:99;
 display:none">
</div>
<script>
(function(){
  var BUILT = "%(built)s";
  var note = document.getElementById("swnote");
  function show(msg){ note.textContent = msg; note.style.display = "block"; }

  function stamp(){
    show(navigator.onLine
      ? "Built " + BUILT + " \\u00b7 cached for offline use"
      : "Offline \\u2014 showing the copy built " + BUILT);
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").then(stamp).catch(function(){
      show("Built " + BUILT + " \\u00b7 offline caching unavailable");
    });
  } else {
    stamp();
  }
  window.addEventListener("online", stamp);
  window.addEventListener("offline", stamp);
  // the banner is informational, not a dialog — one tap dismisses it for good
  note.addEventListener("click", function(){ note.style.display = "none"; });
})();
</script>
"""

MANIFEST = """{
 "name": "Mt. Whitney Training",
 "short_name": "Whitney",
 "description": "Training, fuelling and altitude readiness for October 2, 2026.",
 "start_url": "./index.html",
 "scope": "./",
 "display": "standalone",
 "orientation": "portrait",
 "background_color": "#f6f8fa",
 "theme_color": "#122436",
 "icons": [
  {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
  {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
  {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
  {"src": "icon.svg", "sizes": "any", "type": "image/svg+xml"}
 ]
}
"""

SW = """/* Cache-first for the shell, so the dashboard opens with the radio off.
   CACHE is stamped by build/site.py; a new build evicts the old one on activate. */
const CACHE = "whitney-%(ver)s";
const SHELL = ["./", "./index.html", "./logger.html",
               "./manifest.webmanifest", "./icon.svg",
               "./icon-192.png", "./icon-512.png"];

self.addEventListener("install", e => {
  // addAll rejects the whole batch if any single request 404s, which would leave
  // the worker uninstalled and offline silently broken. Add them individually.
  e.waitUntil(caches.open(CACHE)
    .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  e.respondWith(
    caches.match(e.request).then(hit => {
      // Serve the cache immediately, then refresh it in the background. On the
      // trail the network attempt fails and the cached copy is already returned.
      const net = fetch(e.request).then(r => {
        if (r && r.ok) caches.open(CACHE).then(c => c.put(e.request, r.clone()));
        return r;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
"""

ROBOTS = "User-agent: *\nDisallow: /\n"


def icon_svg():
    """A summit wedge. Drawn rather than fetched so the repo has no binary dependency."""
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
 <defs><linearGradient id="s" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#122436"/><stop offset=".58" stop-color="#1f4d5e"/>
  <stop offset="1" stop-color="#1f7a68"/></linearGradient></defs>
 <rect width="512" height="512" rx="96" fill="url(#s)"/>
 <path d="M74 372 L196 196 L262 286 L316 214 L438 372 Z" fill="#f6f8fa"/>
 <path d="M196 196 L154 256 L238 256 Z" fill="#cfe3ea"/>
 <circle cx="196" cy="196" r="15" fill="#ffd479"/>
 <text x="256" y="446" font-family="-apple-system,Helvetica,Arial,sans-serif"
  font-size="62" font-weight="700" fill="#cfe3ea" text-anchor="middle">14,505</text>
</svg>
"""


def raster(svg_path, out, size):
    """
    Render the icon to PNG without a headless browser or cairo.

    Pillow cannot read SVG, so the wedge is redrawn here with the same geometry
    scaled from the 512 viewBox. Duplicated geometry is a real cost, but the
    alternative is a cairosvg build or a Chromium screenshot for a 12 KB icon.
    """
    from PIL import Image, ImageDraw
    k = size / 512
    def p(*xy):
        return [(x * k, y * k) for x, y in xy]

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=96 * k, fill=(18, 44, 62, 255))
    # gradient approximated by three horizontal bands — invisible at 192px
    for i, col in enumerate([(31, 77, 94), (31, 105, 100), (31, 122, 104)]):
        y0 = int(size * (0.34 + i * 0.22))
        d.rectangle([0, y0, size, size], fill=col + (255,))
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=96 * k, outline=None)
    d.polygon(p((74, 372), (196, 196), (262, 286), (316, 214), (438, 372)),
              fill=(246, 248, 250, 255))
    d.polygon(p((196, 196), (154, 256), (238, 256)), fill=(207, 227, 234, 255))
    r = 15 * k
    cx, cy = 196 * k, 196 * k
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 212, 121, 255))
    img.save(out, "PNG")


def main():
    if not DASH.exists():
        raise SystemExit(f"missing {DASH} — run build/dashboard.py first")

    html = DASH.read_text(encoding="utf-8")
    built = dt.date.today().strftime("%b %-d, %Y") if hasattr(dt.date.today(), "strftime") else ""
    try:
        built = dt.date.today().strftime("%b %-d, %Y")
    except ValueError:               # platforms without %-d
        built = dt.date.today().strftime("%b %d, %Y").replace(" 0", " ")

    # version the cache by content, not by clock: an identical rebuild must not
    # force every phone to re-download the shell
    ver = hashlib.sha256(html.encode("utf-8")).hexdigest()[:10]

    SITE.mkdir(exist_ok=True)

    # ── head injection, idempotent
    if "manifest.webmanifest" not in html:
        html = html.replace("</head>", HEAD + "</head>", 1)
    if "sw.js" not in html:
        html = html.replace("</body>", (TAIL % {"built": built}) + "</body>", 1)

    (SITE / "index.html").write_text(html, encoding="utf-8")

    if LOGGER.exists():
        lg = LOGGER.read_text(encoding="utf-8")
        if "manifest.webmanifest" not in lg:
            lg = lg.replace("</head>", HEAD + "</head>", 1)
        (SITE / "logger.html").write_text(lg, encoding="utf-8")

    (SITE / "manifest.webmanifest").write_text(MANIFEST, encoding="utf-8")
    (SITE / "sw.js").write_text(SW % {"ver": ver}, encoding="utf-8")
    (SITE / "robots.txt").write_text(ROBOTS, encoding="utf-8")
    (SITE / "icon.svg").write_text(icon_svg(), encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")   # Pages must not run Jekyll

    for s in (192, 512):
        raster(SITE / "icon.svg", SITE / f"icon-{s}.png", s)

    tot = sum(p.stat().st_size for p in SITE.iterdir() if p.is_file())
    print(f"docs/ built — cache version {ver}, {tot/1024:.0f} KB total")
    for p in sorted(SITE.iterdir()):
        if p.is_file():
            print(f"   {p.name:26s} {p.stat().st_size/1024:7.1f} KB")


if __name__ == "__main__":
    main()
