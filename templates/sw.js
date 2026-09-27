const CACHE_NAME = 'solobiz-offline-{{ version }}';
const PRIVATE_CACHE_NAME = 'solobiz-private-{{ version }}';
const OFFLINE_SHELL_KEY = new URL('/__solobiz_offline_dashboard__', self.location.origin).href;

// Public assets are shared. The dashboard shell is stored separately because
// it contains user-specific values and is removed when the user logs out.
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
    caches.keys()
      .then((keys) => Promise.all(keys
        .filter((key) => key !== CACHE_NAME && key !== PRIVATE_CACHE_NAME)
        .map((key) => caches.delete(key))))
      .then(() => clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'CLEAR_PRIVATE_OFFLINE_SHELL') {
    event.waitUntil(caches.delete(PRIVATE_CACHE_NAME));
    return;
  }

  if (event.data?.type === 'CACHE_DASHBOARD_SHELL' && event.data.url) {
    event.waitUntil((async () => {
      try {
        const pageUrl = new URL(event.data.url, self.location.origin);
        if (pageUrl.origin !== self.location.origin ||
            !(pageUrl.pathname === '/dashboard' || pageUrl.pathname.startsWith('/dashboard/'))) return;
        const response = await fetch(pageUrl.href, { cache: 'no-store', credentials: 'same-origin' });
        const finalUrl = new URL(response.url || pageUrl.href);
        if (!response.ok || finalUrl.origin !== self.location.origin ||
            !(finalUrl.pathname === '/dashboard' || finalUrl.pathname.startsWith('/dashboard/'))) return;
        const privateCache = await caches.open(PRIVATE_CACHE_NAME);
        await privateCache.put(OFFLINE_SHELL_KEY, response);
      } catch (error) {
        console.warn('[PWA] Could not save the dashboard for offline use:', error);
      }
    })());
  }
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Do not intercept non-GET requests or API calls
  if (request.method !== 'GET' || url.origin !== self.location.origin ||
      url.pathname.startsWith('/api/')) {
    return;
  }

  if (request.mode === 'navigate') {
    const isDashboard = url.pathname === '/dashboard' || url.pathname.startsWith('/dashboard/');
    const isLogout = url.pathname === '/logout';

    event.respondWith((async () => {
      if (isLogout) {
        await caches.delete(PRIVATE_CACHE_NAME);
        try {
          return await fetch(request, { cache: 'no-cache' });
        } catch (_) {
          return new Response(
            '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline</title><body style="font:16px system-ui;padding:2rem;background:#0f172a;color:#fff"><h1>Signed out on this device</h1><p>You are offline. Connect to the internet to finish signing out of SoloBiz.</p></body></html>',
            { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        }
      }

      try {
        const response = await fetch(request, { cache: 'no-cache' });
        const finalUrl = new URL(response.url || request.url);
        const isAuthenticatedDashboard = response.ok &&
          (finalUrl.pathname === '/dashboard' || finalUrl.pathname.startsWith('/dashboard/'));
        if (isAuthenticatedDashboard) {
          const privateCache = await caches.open(PRIVATE_CACHE_NAME);
          await privateCache.put(OFFLINE_SHELL_KEY, response.clone());
        }
        return response;
      } catch (_) {
        if (isDashboard || url.pathname === '/') {
          const privateCache = await caches.open(PRIVATE_CACHE_NAME);
          const offlineShell = await privateCache.match(OFFLINE_SHELL_KEY);
          if (offlineShell) return offlineShell;
        }
        return new Response(
          '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline</title><body style="font:16px system-ui;padding:2rem;background:#0f172a;color:#fff"><h1>You are offline</h1><p>Open SoloBiz once while online to make the dashboard available offline.</p></body></html>',
          { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
      }
    })());
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
