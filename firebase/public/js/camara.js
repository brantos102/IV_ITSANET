/**
 * Escaneo con la cámara del teléfono.
 *
 * El 80% de la operación es en handheld o celular. Muchos llevan pistola, pero
 * no todos, y a veces el código está en una etiqueta a la que la pistola no
 * llega bien —una caja al fondo de un pallet, un código impreso pequeño—.
 *
 * Se usa `BarcodeDetector`, que viene en el propio navegador: en Chrome de
 * Android funciona sin instalar nada ni cargar librerías. Donde no está —Safari
 * de iPhone, por ejemplo— se dice y se sigue con el teclado y la pistola, que
 * es lo que ya funciona. No se carga un motor de respaldo de 800 KB por el
 * camino: el almacén tiene el WiFi que tiene.
 */

const FORMATOS = [
  'code_128', 'code_39', 'code_93', 'codabar',
  'ean_13', 'ean_8', 'upc_a', 'upc_e',
  'itf', 'data_matrix', 'qr_code',
];

export const camaraDisponible = () =>
  typeof window !== 'undefined'
  && 'BarcodeDetector' in window
  && !!navigator.mediaDevices?.getUserMedia;

/** Por qué no se puede, en términos que digan qué hacer. */
export function motivoNoDisponible() {
  if (typeof window === 'undefined') return 'Sin navegador.';
  if (!navigator.mediaDevices?.getUserMedia) {
    return 'Este navegador no da acceso a la cámara. Hace falta HTTPS; con la ' +
           'app abierta desde su enlace ya lo es.';
  }
  if (!('BarcodeDetector' in window)) {
    return 'Este navegador no sabe leer códigos con la cámara. En Android, ' +
           'Chrome sí. Mientras tanto, usa la pistola o escribe el código.';
  }
  return '';
}

/**
 * Enciende la cámara y avisa de cada código leído.
 *
 * Devuelve una función para apagarla. Apagarla importa: una cámara encendida
 * se come la batería del handheld en una jornada.
 *
 * @param {HTMLVideoElement} video  dónde se ve lo que enfoca la cámara
 * @param {(codigo: string) => void} alLeer
 * @param {object} opciones  { intervaloMs, repetirTrasMs }
 */
export async function abrirCamara(video, alLeer, opciones = {}) {
  const intervaloMs = opciones.intervaloMs || 180;
  // El mismo código delante de la cámara se lee treinta veces por segundo. Sin
  // esta espera, un solo acercamiento registraría decenas de unidades.
  const repetirTrasMs = opciones.repetirTrasMs ?? 2500;

  const detector = new window.BarcodeDetector({ formats: FORMATOS });

  const flujo = await navigator.mediaDevices.getUserMedia({
    video: {
      // La trasera: la frontal enfoca al operario.
      facingMode: { ideal: 'environment' },
      width: { ideal: 1280 },
      height: { ideal: 720 },
    },
    audio: false,
  });

  video.srcObject = flujo;
  video.setAttribute('playsinline', '');   // iOS no abre pantalla completa
  await video.play();

  let ultimo = '';
  let ultimoEn = 0;
  let vivo = true;

  const temporizador = setInterval(async () => {
    if (!vivo || video.readyState < 2) return;
    try {
      const codigos = await detector.detect(video);
      if (!codigos.length) return;

      const valor = String(codigos[0].rawValue || '').trim();
      if (!valor) return;

      const ahora = Date.now();
      if (valor === ultimo && ahora - ultimoEn < repetirTrasMs) return;
      ultimo = valor;
      ultimoEn = ahora;
      alLeer(valor);
    } catch {
      // Un fotograma ilegible no es un error: el siguiente llega en 180 ms.
    }
  }, intervaloMs);

  return function cerrar() {
    vivo = false;
    clearInterval(temporizador);
    for (const pista of flujo.getTracks()) pista.stop();
    video.srcObject = null;
  };
}
