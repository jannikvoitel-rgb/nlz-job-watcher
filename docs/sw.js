/* Service Worker: App offline verfuegbar halten.
 *
 * Das Geruest kommt aus dem Cache, die Stellenliste zuerst aus dem Netz -
 * sonst zeigt die App nach einem Lauf noch alte Stellen. Ohne Netz wird
 * die letzte gespeicherte Liste genommen.
 */
// Bei jeder Änderung am Gerüst (index.html, app.js, styles.css) die
// Zahl hochsetzen. Sonst behalten schon installierte Apps - etwa die
// auf dem Homescreen - die alte Fassung aus ihrem Cache. Beim Aktivieren
// werden alle Caches mit anderem Namen gelöscht.
var CACHE = "nlz-stellen-v2";
var SHELL = [
  ".",
  "index.html",
  "styles.css",
  "app.js",
  "manifest.webmanifest",
  "icon.svg"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(SHELL);
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(names.map(function (name) {
        return name === CACHE ? null : caches.delete(name);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") { return; }

  var isData = request.url.indexOf("jobs.json") !== -1;

  if (isData) {
    event.respondWith(
      fetch(request).then(function (response) {
        if (response && response.ok) {
          var copy = response.clone();
          caches.open(CACHE).then(function (c) { c.put(request, copy); });
        }
        return response;
      }).catch(function () {
        return caches.match(request);
      })
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(function (cached) {
      return cached || fetch(request).then(function (response) {
        if (response && response.ok && response.type === "basic") {
          var copy = response.clone();
          caches.open(CACHE).then(function (c) { c.put(request, copy); });
        }
        return response;
      });
    })
  );
});
