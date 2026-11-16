const CACHE_NAME = 'solobiz-offline-{{ version }}';
const PRIVATE_CACHE_NAME = 'solobiz-private-{{ version }}';
const OFFLINE_SHELL_KEY = new URL('/__solobiz_offline_dashboard__', self.location.origin).href;
const AUTHENTICATED_PAGE_PATHS = new Set(['/dashboard', '/expenses', '/inventory', '/sales', '/analytics', '/profile']);
const isAuthenticatedPage = (pathname) => AUTHENTICATED_PAGE_PATHS.has(pathname) || pathname.startsWith('/dashboard/');

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
        if (pageUrl.origin !== self.location.origin || !isAuthenticatedPage(pageUrl.pathname)) return;
        const response = await fetch(pageUrl.href, { cache: 'no-store', credentials: 'same-origin' });
        const finalUrl = new URL(response.url || pageUrl.href);
        if (!response.ok || finalUrl.origin !== self.location.origin || !isAuthenticatedPage(finalUrl.pathname)) return;
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
    const isDashboard = isAuthenticatedPage(url.pathname);
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
        const isAuthenticatedDashboard = response.ok && isAuthenticatedPage(finalUrl.pathname);
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

// ---------------------------------------------------------------------------
// Push notifications (stock alerts)
// ---------------------------------------------------------------------------
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) { data = { body: event.data?.text() || '' }; }
  const title = data.title || 'SoloBiz';
  const options = {
    body: data.body || '',
    tag: data.tag || 'solobiz-alert',
    renotify: true,
    icon: '/static/favicon.png',
    badge: '/static/favicon.png',
    data: { url: data.url || '/inventory' }
  };

  event.waitUntil((async () => {
    const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    const focused = windows.find((client) => client.focused && client.visibilityState === 'visible');
    if (focused) {
      // SoloBiz is open and in front: show the alert inside the page instead
      // of a system notification on top of it.
      focused.postMessage({ type: 'PUSH_ALERT', title, body: options.body, tag: options.tag });
      return;
    }
    await self.registration.showNotification(title, options);
  })());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || '/inventory', self.location.origin);
  if (target.origin !== self.location.origin) return;
  event.waitUntil((async () => {
    const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    const existing = windows.find((client) => new URL(client.url).origin === self.location.origin);
    if (existing) {
      await existing.focus();
      if ('navigate' in existing) return existing.navigate(target.href);
      return undefined;
    }
    return clients.openWindow(target.href);
  })());
});
