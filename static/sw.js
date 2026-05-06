// Coviction Service Worker — offline shell caching

const CACHE_NAME = 'coviction-v1';

const SHELL_ASSETS = [

  '/app/',

  '/app/coviction-app.html',

];



self.addEventListener('install', (event) => {

  event.waitUntil(

    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))

  );

  self.skipWaiting();

});



self.addEventListener('activate', (event) => {

  event.waitUntil(

    caches.keys().then((keys) =>

      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))

    )

  );

  self.clients.claim();

});



self.addEventListener('fetch', (event) => {

  // Only cache GET requests for the app shell

  if (event.request.method !== 'GET') return;



  const url = new URL(event.request.url);



  // Don't cache API calls

  if (url.pathname.startsWith('/sessions') ||

      url.pathname.startsWith('/ask') ||

      url.pathname.startsWith('/search') ||

      url.pathname.startsWith('/health')) {

    return;

  }



  event.respondWith(

    caches.match(event.request).then((cached) => {

      // Network-first for HTML, cache-first for static assets

      if (event.request.headers.get('accept')?.includes('text/html')) {

        return fetch(event.request)

          .then((response) => {

            const clone = response.clone();

            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));

            return response;

          })

          .catch(() => cached);

      }

      return cached || fetch(event.request);

    })

  );

});
