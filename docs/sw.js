/* Cache-first for the shell, so the dashboard opens with the radio off.
   CACHE is stamped by build/site.py; a new build evicts the old one on activate. */
const CACHE = "whitney-c4766c7645";
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

/* The page itself is network-first; everything else stays cache-first.

   This split is the whole fix for "I bookmarked it and it never updates". The old
   handler returned `hit || net` for every request, which serves the cached copy and
   only *then* refreshes it in the background. For icons that is right. For index.html
   it means the screen is painted from the previous build every single time, so the
   phone is permanently one visit behind: open it and you see last week, close it, open
   it again and you finally see this week — by which point there is usually a newer
   build again. Bumping CACHE per build did not help, because the stale copy is already
   on screen before the new worker activates.

   Offline still works, which is the constraint that matters at Trail Camp: when fetch
   rejects, or when it has not answered within NET_TIMEOUT_MS, the cached copy is served
   instead. A slow bar of signal falls back fast rather than hanging on a white screen,
   and the late network response still repopulates the cache for next time. */
const NET_TIMEOUT_MS = 3000;

function isPage(req) {
  return req.mode === "navigate" ||
         (req.headers.get("accept") || "").includes("text/html");
}

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const req = e.request;

  if (isPage(req)) {
    e.respondWith(new Promise(resolve => {
      let settled = false;
      const done = r => { if (!settled) { settled = true; resolve(r); } };

      // Fall back to cache if the network is merely slow, not just when it fails.
      const timer = setTimeout(() => {
        caches.match(req).then(hit => { if (hit) done(hit); });
      }, NET_TIMEOUT_MS);

      fetch(req).then(r => {
        clearTimeout(timer);
        if (r && r.ok) {
          const copy = r.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        done(r);
      }).catch(() => {
        clearTimeout(timer);
        caches.match(req).then(hit => done(hit || Response.error()));
      });
    }));
    return;
  }

  // Static shell assets: cache-first, refreshed in the background.
  e.respondWith(
    caches.match(req).then(hit => {
      const net = fetch(req).then(r => {
        if (r && r.ok) caches.open(CACHE).then(c => c.put(req, r.clone()));
        return r;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
