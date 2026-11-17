// SoloBiz service worker. The React app is one shell for every signed-in page,
// so the shell holds no personal data. Account data (API reads) is kept in a
// separate private cache that is emptied on sign-out.
const CACHE_NAME = 'solobiz-offline-{{ version }}';
const PRIVATE_CACHE_NAME = 'solobiz-private-{{ version }}';
const SHELL_KEY = new URL('/__solobiz_app_shell__', self.location.origin).href;
const APP_PATHS = new Set(['/dashboard', '/sales', '/inventory', '/expenses', '/budget', '/profile', '/reports', '/website']);
const READ_APIS = new Set([
  '/api/session', '/api/dashboard', '/api/income', '/api/expenses',
  '/api/inventory-presets', '/api/business_profile', '/api/website'
]);

const PRECACHE_ASSETS = [
  '/static/logo.svg',
  '/static/manifest.json',
  '/static/favicon.png',
  '/static/tailwind.js',
  '/static/solobiz-ui.css'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => Promise.all(PRECACHE_ASSETS.map(async (asset) => {
      try {
        const response = await fetch(asset, { cache: 'no-store' });
        if (response.ok) await cache.put(asset, response);
      } catch (error) {
        console.warn('[PWA] Could not precache', asset, error);
      }
    })))
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
  if (event.data?.type === 'CLEAR_PRIVATE_OFFLINE_DATA') {
    event.waitUntil(caches.delete(PRIVATE_CACHE_NAME));
  }
});

const offlinePage = (status) => new Response(
  '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline</title>' +
  '<body style="font:16px system-ui;padding:32px;text-align:center"><h1>You are offline</h1><p>Reconnect and try again.</p></body></html>',
  { status, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
);

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  // Account data: network first, last good copy when offline.
  if (READ_APIS.has(url.pathname)) {
    event.respondWith((async () => {
      const cache = await caches.open(PRIVATE_CACHE_NAME);
      try {
        const response = await fetch(request);
        if (response.ok) await cache.put(url.pathname, response.clone());
        return response;
      } catch (_) {
        return (await cache.match(url.pathname)) || Response.error();
      }
    })());
    return;
  }
  if (url.pathname.startsWith('/api/')) return;

  // Pages of the app: the same React shell for all of them.
  if (request.mode === 'navigate' && APP_PATHS.has(url.pathname)) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      try {
        const response = await fetch(request, { cache: 'no-cache' });
        if (response.ok && response.headers.get('content-type')?.includes('text/html') && !response.redirected) {
          await cache.put(SHELL_KEY, response.clone());
        }
        return response;
      } catch (_) {
        return (await cache.match(SHELL_KEY)) || offlinePage(503);
      }
    })());
    return;
  }
  if (request.mode === 'navigate') return;

  // Static and built assets: cached copy first.
  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      }).catch(() => Response.error()))
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
