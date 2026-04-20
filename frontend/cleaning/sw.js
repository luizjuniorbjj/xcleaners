/**
 * Xcleaners Service Worker
 *
 * Caching strategies:
 *   - App shell: Cache First (precached on install)
 *   - Core JS/CSS: Cache First (versioned)
 *   - API GET: Network First (fallback to cache)
 *   - API POST/PATCH/PUT/DELETE: Network Only (queued if offline for team role)
 *   - Fonts: Stale While Revalidate
 *   - CDN libs: Cache First
 */

const CACHE_VERSION = 'xcleaners-v26';
const SHELL_CACHE = `${CACHE_VERSION}-shell`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;
const API_CACHE = `${CACHE_VERSION}-api`;

// App shell resources (precached on install)
const SHELL_ASSETS = [
  '/cleaning/app',
  '/cleaning/static/css/design-system.css?v=11',
  '/cleaning/static/css/app.css?v=11',
  '/cleaning/static/css/schedule.css?v=11',
  '/cleaning/static/js/shared/demo-data.js?v=11',
  '/cleaning/static/js/shared/cleaning-api.js?v=11',
  '/cleaning/static/js/shared/sse-client.js?v=12',
  '/cleaning/static/js/shared/offline-store.js?v=11',
  '/cleaning/static/js/shared/i18n.js?v=11',
  '/cleaning/static/js/auth-ui.js?v=15',
  '/cleaning/static/js/router.js?v=14',
  '/cleaning/static/js/app.js?v=14',
  '/cleaning/static/vendor/fullcalendar.min.js',
  '/cleaning/static/icons/icon-192.png',
];

// Cleaner API endpoints that should be cached for offline access
const CLEANER_CACHE_PATTERNS = [
  /\/api\/v1\/clean\/[^/]+\/my-jobs\/today$/,
  /\/api\/v1\/clean\/[^/]+\/my-jobs\/[a-f0-9-]+$/,
  /\/api\/v1\/clean\/[^/]+\/my-schedule/,
  /\/api\/v1\/clean\/[^/]+\/my-earnings/,
];

// ----- Install -----

self.addEventListener('install', (event) => {
  console.log('[SW] Installing Xcleaners service worker');
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => {
      return cache.addAll(SHELL_ASSETS).catch((err) => {
        console.warn('[SW] Some shell assets failed to cache:', err);
      });
    })
  );
  self.skipWaiting();
});

// ----- Activate -----

self.addEventListener('activate', (event) => {
  console.log('[SW] Activating Xcleaners service worker');
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => (key.startsWith('xcleaners-') || key.startsWith('cleanclaw-')) && key !== SHELL_CACHE && key !== DYNAMIC_CACHE && key !== API_CACHE)
          .map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// ----- Fetch -----

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET for caching (POST/PATCH/PUT/DELETE go straight to network)
  if (event.request.method !== 'GET') {
    // For team role offline queue, the app.js handles queuing via IndexedDB
    return;
  }

  // SSE streams - network only
  if (url.pathname.includes('/stream')) {
    return;
  }

  // Cleaner API endpoints - network first with aggressive caching for offline
  if (url.pathname.startsWith('/api/') && CLEANER_CACHE_PATTERNS.some(p => p.test(url.pathname))) {
    event.respondWith(networkFirst(event.request, API_CACHE));
    return;
  }

  // API calls - network first, fallback to cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(event.request, API_CACHE));
    return;
  }

  // Google Fonts - stale while revalidate
  if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
    event.respondWith(staleWhileRevalidate(event.request, DYNAMIC_CACHE));
    return;
  }

  // CDN resources (FullCalendar, etc) - cache first
  if (url.hostname !== self.location.hostname) {
    event.respondWith(cacheFirst(event.request, DYNAMIC_CACHE));
    return;
  }

  // Cleaning static assets - cache first
  if (url.pathname.startsWith('/cleaning/static/')) {
    event.respondWith(cacheFirst(event.request, SHELL_CACHE));
    return;
  }

  // SPA catch-all: serve app.html for /cleaning/app paths
  if (url.pathname.startsWith('/cleaning/app')) {
    event.respondWith(
      caches.match('/cleaning/app').then((cached) => {
        return cached || fetch(event.request);
      })
    );
    return;
  }

  // Default: network first
  event.respondWith(networkFirst(event.request, DYNAMIC_CACHE));
});

// ----- Caching Strategies -----

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    return offlineFallback();
  }
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return offlineFallback();
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request).then((response) => {
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  }).catch(() => cached);
  return cached || fetchPromise;
}

function offlineFallback() {
  return caches.match('/cleaning/app').then((cached) => {
    if (cached) return cached;
    return new Response(
      '<html><body style="font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;color:#374151;">' +
      '<div style="text-align:center;"><h1>Offline</h1><p>Xcleaners is not available offline right now.</p><p>Please check your connection and try again.</p></div>' +
      '</body></html>',
      { headers: { 'Content-Type': 'text/html' } }
    );
  });
}

// ----- Push Notifications -----

self.addEventListener('push', (event) => {
  let data = { title: 'Xcleaners', body: 'You have a new notification' };
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body || '',
    icon: '/cleaning/static/icons/icon-192.png',
    badge: '/cleaning/static/icons/icon-192.png',
    vibrate: [200, 100, 200],
    data: data.data || {},
    actions: data.actions || [],
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'Xcleaners', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || '/cleaning/app';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url.includes('/cleaning/app') && 'focus' in client) {
          return client.focus();
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});
