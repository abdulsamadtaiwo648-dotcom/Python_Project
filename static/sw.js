const CACHE_NAME = 'solobiz-offline-v3';

// Only cache public, user-independent assets. Authenticated HTML pages must
// never be cached because one user's dashboard could otherwise be shown after
// logout or to another user on the same device.
const PRECACHE_ASSETS = [
  '/dashboard',
  '/static/logo.svg',
  '/static/manifest.json',
  '/static/favicon.png',
  '/static/tailwind.js'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_ASSETS))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter((key) => key !== CACHE_NAME)
        .map((key) => caches.delete(key))
    )).then(() => clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Do not cache authenticated API calls or unsafe requests.
  if (request.method !== 'GET' || url.origin !== self.location.origin ||
      url.pathname.startsWith('/api/')) {
    return;
  }

  // Navigation requests should be network-first so the app remains functional offline,
  // but they can fall back to a cached shell when the browser is truly offline.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match('/')))
    );
    return;
  }

  // Static assets can be cached for offline access without hiding the app.
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) return cachedResponse;
      return fetch(request).then((networkResponse) => {
        if (!networkResponse || !networkResponse.ok) return networkResponse;
        const responseCopy = networkResponse.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, responseCopy));
        return networkResponse;
      }).catch(() => Response.error());
    })
  );
});
