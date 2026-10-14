/**
 * Service worker: la app se abre aunque el handheld pierda la red.
 *
 * Estrategia: RED PRIMERO para todo lo propio. La caché solo responde cuando la
 * red falla. Es deliberado: la alternativa (caché primero) deja a un operario
 * con la versión vieja del código después de un despliegue, que es justo el
 * problema que ya costó una jornada en este proyecto.
 *
 * Al subir una versión hay que cambiar VERSION. `skipWaiting` + `clients.claim`
 * hacen que el reemplazo surta efecto en la siguiente carga, no en la siguiente
 * semana.
 */
const VERSION = 'iv-2026-10-14-13';

/** Lo mínimo para que la app arranque sin red. */
const CONCHA = [
  '/', '/index.html', '/recepciones.html', '/validar.html', '/admin.html',
  '/usuarios.html', '/kpis.html',
  '/css/app.css', '/manifest.webmanifest', '/icono.svg',
  '/js/config.js', '/js/auth.js', '/js/datos.js', '/js/conteo.js',
  '/js/informe.js', '/js/proxy.js', '/js/imagen.js', '/js/kpi.js', '/js/camara.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(VERSION)
      // Si un archivo falla no se cae la instalación: se cachea lo que haya.
      .then((c) => Promise.allSettled(CONCHA.map((u) => c.add(u))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // Firestore, el proxy y las librerías de CDN se gestionan solos; el SDK ya
  // guarda los datos en IndexedDB y cachear sus respuestas rompería el
  // tiempo real.
  if (url.origin !== self.location.origin) return;

  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const copia = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copia)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match('/index.html'))),
  );
});
