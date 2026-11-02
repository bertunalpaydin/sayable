{% load static %}/* Service worker: makes Sayable installable and keeps the page shell
   available. Recordings always need the server, so API calls are never cached. */

const CACHE = "sayable-v1";
const SHELL = [
  "{% static 'core/app.css' %}",
  "{% static 'core/app.js' %}",
  "{% static 'core/icons/icon-192.png' %}",
  "{% url 'offline' %}",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("{% url 'offline' %}")));
    return;
  }
  if (url.pathname.startsWith("{% get_static_prefix %}")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request))
    );
  }
});
