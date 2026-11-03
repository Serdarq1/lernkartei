// Offline cache for Lernkartei. Bump VERSION whenever index.html, data.js or the icons change,
// so installed apps fetch the new files and drop the old cache.
const VERSION = "lernkartei-v1";
const SHELL = ["./", "index.html", "data.js", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Stale-while-revalidate: answer from the cache at once (works offline), refresh it in the background.
// Covers our own files and the Google Fonts stylesheet + font files.
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const ours = url.origin === location.origin;
  if (!ours && !/^fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) return;
  const key = ours && req.mode === "navigate" ? "index.html" : req;
  e.respondWith(caches.open(VERSION).then(async cache => {
    const hit = await cache.match(key);
    const fresh = fetch(req).then(res => {
      if (res.ok || res.type === "opaque") cache.put(key, res.clone());
      return res;
    }).catch(() => hit);
    return hit || fresh;
  }));
});
