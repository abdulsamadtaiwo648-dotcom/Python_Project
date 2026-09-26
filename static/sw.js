const CACHE_NAME = 'solobiz-offline-20260926.2';

// Only cache public, user-independent static assets. Authenticated HTML pages
// must never be cached because dynamic Jinja2 server variables (CSRF token,
// user session, username) must always remain live and real-time.
const PRECACHE_ASSETS = [
  '/static/logo.svg',
  '/static/manifest.json',
  '/static/favicon.png',
  '/static/tailwind.js'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      await Promise.all(PRECACHE_ASSETS.map(async (asset) => {
        try {
          const response = await fetch(asset, { cache: 'no-store' });
          if (response.ok) {
            await cache.put(asset, response);
          }
        } catch (error) {
          console.warn('[PWA] Could not precache', asset, error);
        }
      }));
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.map(async (key) => {
        // Delete all old cache stores to purge stale broken versions
        if (key !== CACHE_NAME) {
          console.log('[PWA] Evicting outdated cache store:', key);
          return caches.delete(key);
        }
        // In the current cache store, ensure /dashboard is never retained
        const currentCache = await caches.open(key);
        await currentCache.delete('/dashboard');
      })
    )).then(() => clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Do not intercept non-GET requests or API calls
  if (request.method !== 'GET' || url.origin !== self.location.origin ||
      url.pathname.startsWith('/api/')) {
    return;
  }

  // Navigation requests: always fetch directly from network in real-time.
  // Never freeze authenticated dashboard HTML in Service Worker cache.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request, { cache: 'no-cache' })
        .then((response) => response)
        .catch(() => caches.match(request).then((cached) => cached || caches.match('/')))
    );
    return;
  }

  // Static assets: serve cached copy if available, otherwise fetch and cache
  if (url.pathname.startsWith('/static/')) {
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
  }
});
