/* Cache-first for the shell, so the dashboard opens with the radio off.
   CACHE is stamped by build/site.py; a new build evicts the old one on activate. */
const CACHE = "whitney-085df550c3";
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
