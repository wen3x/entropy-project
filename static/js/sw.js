/* ========================================================================
   Entropy — Service Worker
   ======================================================================== */

const CACHE = "entropy-v1";
const ASSETS = [
  "/static/css/entropy-site.css",
  "/static/js/entropy-theme.js",
  "/static/js/entropy-likes.js",
  "/static/img/logo.svg",
  "/static/img/logo.png",
  "/static/img/favicon.png",

];

// ── Install: cache static assets ──
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => {
      return cache.addAll(ASSETS).catch(() => {
        // Non-critical; proceed even if some fail
      });
    })
  );
  self.skipWaiting();
});

// ── Activate: clean old caches ──
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// ── Fetch: network-first, fallback to cache ──
self.addEventListener("fetch", (event) => {
  // Only handle GET requests
  if (event.request.method !== "GET") return;

  // Skip non-http(s) requests
  if (!event.request.url.startsWith("http")) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful responses for static assets
        if (response.ok && event.request.url.includes("/static/")) {
          const clone = response.clone();
          caches.open(CACHE).then((cache) => {
            cache.put(event.request, clone);
          });
        }
        return response;
      })
      .catch(() => {
        // Offline: serve from cache
        return caches.match(event.request).then((cached) => {
          return cached || new Response("Offline", { status: 503 });
        });
      })
  );
});

// ── Push event: receive push notification ──
self.addEventListener("push", (event) => {
  let pushData = {
    title: "Entropy",
    body: "Новое уведомление",
    icon: "/static/img/favicon.png",
    badge: "/static/img/favicon.png",
    data: { url: "/" },
  };

  if (event.data) {
    try {
      const parsed = event.data.json();
      pushData = { ...pushData, ...parsed };
    } catch (e) {
      pushData.body = event.data.text() || pushData.body;
    }
  }

  event.waitUntil(
    self.registration.showNotification(pushData.title, {
      body: pushData.body,
      icon: pushData.icon,
      badge: pushData.badge,
      data: pushData.data,
      vibrate: [200, 100, 200],
      requireInteraction: true,
      tag: "entropy-notification",
    })
  );
});

// ── Notification click: open the related page ──
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const urlToOpen = event.notification.data?.url || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      // If already open, focus and navigate
      for (const client of windowClients) {
        if (client.url.startsWith(self.location.origin) && "focus" in client) {
          client.focus();
          if ("navigate" in client) {
            client.navigate(urlToOpen);
          }
          return;
        }
      }
      // Otherwise open new window
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});
