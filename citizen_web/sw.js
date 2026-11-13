/* RoadWatch service worker: caches the app shell so it opens offline. API calls are never cached. */
var CACHE = "rw-shell-v1";
var SHELL = [
  "./", "index.html", "style.css", "app.js", "manifest.webmanifest",
  "icons/icon-192.png", "icons/icon-512.png",
  "assets/photos/street.jpg", "assets/photos/goodshot.jpg",
  "assets/photos/pothole_sq.jpg", "assets/photos/crack_sq.jpg", "assets/photos/waterlogging_sq.jpg",
  "assets/photos/broken_road_sq.jpg", "assets/photos/other_sq.jpg",
  "assets/photos/pothole.jpg", "assets/photos/crack.jpg", "assets/photos/waterlogging.jpg",
  "assets/photos/broken_road.jpg", "assets/photos/other.jpg"
];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // API and map live on another origin
  e.respondWith(
    fetch(req).then(function (res) {
      if (res && res.ok) { var copy = res.clone(); caches.open(CACHE).then(function (c) { c.put(req, copy); }); }
      return res;
    }).catch(function () {
      return caches.match(req).then(function (hit) { return hit || (req.mode === "navigate" ? caches.match("index.html") : Response.error()); });
    })
  );
});

self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var target = (e.notification.data && e.notification.data.url) || "./#/alerts";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) { if ("focus" in list[i]) { list[i].navigate && list[i].navigate(target); return list[i].focus(); } }
    return self.clients.openWindow(target);
  }));
});
