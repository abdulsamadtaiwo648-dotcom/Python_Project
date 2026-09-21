const CACHE_NAME = 'solobiz-offline-v1';

// Assets to pre-cache on install
const PRECACHE_ASSETS = [
  '/dashboard',
  '/static/logo.svg',
  '/static/manifest.json',
  '/static/favicon.png',
  '/static/tailwind.js'
];

// 1. Install & Cache App Shell
self.addEventListener('install', (event) => {
  self.skipWaiting(); // Force the new service worker to activate immediately
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('Some assets failed to precache:', err);
      });
    })
  );
});

// 2. Activate & Claim Control Immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    clients.claim() // Take control of all open pages immediately
  );
});

// 3. Intercept Refreshes and Network Requests
self.addEventListener('fetch', (event) => {
  // Handle Page Refreshes / Navigation (e.g. dragging down to refresh on /dashboard)
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          // If online, update the cached copy of this page
          return caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, networkResponse.clone());
            return networkResponse;
          });
        })
        .catch(() => {
          // IF OFFLINE: Return the cached page matching the requested URL
          return caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // Fallback to cached dashboard if exact URL match fails
            return caches.match('/dashboard');
          });
        })
    );
    return;
  }

  // Handle static assets (CSS, JS, Images)
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      return cachedResponse || fetch(event.request);
    })
  );
});
