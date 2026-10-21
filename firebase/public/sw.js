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
const VERSION = 'iv-20261021-61';

/** Lo mínimo para que la app arranque sin red. */
const BASE = new URL(self.registration.scope);
const recurso = (ruta) => new URL(ruta.replace(/^\//, ''), BASE).href;
const VERSION_RECURSOS = '20261021-61';
const CONCHA = [
  '/', '/index.html', '/recepciones.html', '/validar.html', '/admin.html',
  '/usuarios.html', '/cuenta.html', '/kpis.html',
  '/css/app.css', '/css/marca.css', '/css/marca.css?v=20261021-61', '/css/operacion.css', '/logo-itsa.png', '/icono.png', '/manifest.webmanifest', '/icono.svg',
  '/js/arranque.js', '/js/config.js', '/js/auth.js', '/js/datos.js', '/js/conteo.js',
  '/js/barra-supervision.js', '/js/correo-redactado.js', '/js/correo-miniaturas.js', '/js/correo-editor.js', '/js/miniaturas.js', '/js/ubicacion-final.js', '/js/posiciones.js', '/js/tipos-foto.js', '/js/correos-embarques.js', '/js/manual-fotos.js', '/js/visor-imagen.js', '/js/mi-correo.js', '/js/avisos-entregas.js', '/js/clientes-operacion.js', '/js/entregas-supervisor.js', '/js/corregir-conteo.js', '/js/admin-entregas.js', '/js/admin-politicas.js','/js/editar-recepcion.js','/js/columnas-informe.js','/js/informes-registro.js',
  '/js/notificaciones.js', '/js/cierre-ayuda.js', '/js/borrador-conteo.js', '/js/captura-foto.js', '/js/orden-informe.js',
  '/js/ingreso.js', '/js/bultos.js', '/js/evidencias.js', '/js/fotos-embarques.js', '/js/admin-operacion.js',
  '/js/informe.js', '/js/proxy.js', '/js/imagen.js', '/js/kpi.js', '/js/camara.js', '/js/glosario.js',
  '/js/csv.js', '/js/modelos-depot.js', '/js/usuarios.js', '/js/fechas.js', '/js/etiquetas.js', '/js/local.js', '/vendor/firebase-sdk.js', '/vendor/xlsx.full.min.js', '/vendor/JsBarcode.all.min.js', '/vendor/jspdf.umd.min.js', '/vendor/jspdf.plugin.autotable.min.js',
].map(u => /^\/(js|vendor)\/.+\.js$/.test(u) ? `${u}?v=${VERSION_RECURSOS}` : u);

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(VERSION)
      // Si un archivo falla no se cae la instalación: se cachea lo que haya.
      .then((c) => Promise.allSettled(CONCHA.map((u) => c.add(recurso(u)))))
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
  // Las sesiones y respuestas de la API nunca se guardan ni se reproducen
  // desde cache. Bajo /app/ tampoco se controla el resto del servidor.
  if (!url.pathname.startsWith(BASE.pathname) || url.pathname.startsWith('/api/')) return;

  e.respondWith(
    fetch(req, {cache:'no-cache'})
      .then((res) => {
        if (res && res.ok) {
          const copia = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copia)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => {
        if (hit) return hit;
        if (req.mode === 'navigate') return caches.match(recurso('/index.html'));
        return Response.error();
      })),
  );
});
