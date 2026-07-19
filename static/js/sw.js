/* ========================================================================
   Entropy — Service Worker v3
   ======================================================================== */

const CACHE = "entropy-v3";
const STATIC_CACHE = "entropy-static-v3";

// ── Pre-cached static assets ──
const ASSETS = [
  "/static/css/entropy-site.css",
  "/static/js/entropy-theme.js",
  "/static/js/entropy-likes.js",
  "/static/img/favicon.png",
];

// ── Install: cache static assets ──
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
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
        keys
          .filter((k) => k !== CACHE && k !== STATIC_CACHE)
          .map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// ── Helper: should this request be cached? ──
function isStaticAsset(url) {
  return url.includes("/static/");
}

function isPage(url) {
  return (
    url.origin === self.location.origin &&
    !url.pathname.includes("/static/") &&
    !url.pathname.match(/\.(js|css|png|jpg|jpeg|gif|svg|ico|webp|json)$/i)
  );
}

function isNavigation(url) {
  return isPage(url) && url.pathname !== "/sw.js" && url.pathname !== "/manifest.json";
}

// ── Fetch: smarter strategy ──
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  if (!event.request.url.startsWith("http")) return;

  const url = new URL(event.request.url);

  // ── Static assets: cache-first ──
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) => {
        return cache.match(event.request).then((cached) => {
          const fetchPromise = fetch(event.request)
            .then((response) => {
              if (response.ok) {
                cache.put(event.request, response.clone());
              }
              return response;
            })
            .catch(() => cached);
          return cached || fetchPromise;
        });
      })
    );
    return;
  }

  // ── Navigations (HTML pages): network-first, cache fallback, offline fallback ──
  if (isNavigation(url)) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE).then((cache) => {
              cache.put(event.request, clone);
            });
          }
          return response;
        })
        .catch(() => {
          return caches.match(event.request).then((cached) => {
            if (cached) return cached;
            // Offline: serve the offline page for navigations
            return caches.match("/offline/");
          });
        })
    );
    return;
  }

  // ── API calls (like AJAX): network-only, no cache ──
  if (url.pathname.startsWith("/accounts/online/")) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(JSON.stringify({ count: "?" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      })
    );
    return;
  }

  // ── Everything else: network-first ──
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && response.type === "basic") {
          const clone = response.clone();
          caches.open(CACHE).then((cache) => {
            cache.put(event.request, clone);
          });
        }
        return response;
      })
      .catch(() => {
        return caches.match(event.request);
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
      for (const client of windowClients) {
        if (client.url.startsWith(self.location.origin) && "focus" in client) {
          client.focus();
          if ("navigate" in client) {
            client.navigate(urlToOpen);
          }
          return;
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});
