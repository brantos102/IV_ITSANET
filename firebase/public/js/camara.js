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
 * es lo que ya funciona. En HTTP interno se puede tomar una foto desde el
 * selector nativo y decodificarla localmente. Su lector se carga solo al usarlo.
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
           'IP interna por HTTP puedes tomar una foto del código o usar la pistola.';
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

  const soportados = window.BarcodeDetector.getSupportedFormats ? await window.BarcodeDetector.getSupportedFormats() : FORMATOS;
  const formatos = FORMATOS.filter(f=>soportados.includes(f));
  if (!formatos.length) throw new Error('No hay formatos de código compatibles; usa una foto.');
  const detector = new window.BarcodeDetector({ formats: formatos });

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
  try { await video.play(); }
  catch(e) { for (const pista of flujo.getTracks()) pista.stop(); video.srcObject=null; throw e; }

  let ultimo = '';
  let ultimoEn = 0;
  let vivo = true;
  let detectando = false;

  const temporizador = setInterval(async () => {
    if (!vivo || detectando || video.readyState < 2) return;
    detectando = true;
    try {
      const codigos = await detector.detect(video);
      if (!vivo || !codigos.length) return;

      const valor = String(codigos[0].rawValue || '').trim();
      if (!valor) return;

      const ahora = Date.now();
      if (valor === ultimo && ahora - ultimoEn < repetirTrasMs) return;
      ultimo = valor;
      ultimoEn = ahora;
      alLeer(valor);
    } catch {
      // Un fotograma ilegible no es un error: el siguiente llega en 180 ms.
    } finally { detectando = false; }
  }, intervaloMs);

  return function cerrar() {
    vivo = false;
    clearInterval(temporizador);
    for (const pista of flujo.getTracks()) pista.stop();
    video.srcObject = null;
  };
}

/** Una foto desde capture/galería funciona sin getUserMedia; no se sube al servidor. */
export async function leerCodigoFoto(archivo) {
  if (!archivo || !/^image\//.test(archivo.type) || archivo.size > 20*1024*1024) {
    throw new Error('Selecciona una imagen de hasta 20 MB.');
  }
  const {BrowserMultiFormatReader, DecodeHintType} = await import('../vendor/zxing.js?v=20261015-24');
  const pistas = new Map([[DecodeHintType.TRY_HARDER, true]]);
  const lector = new BrowserMultiFormatReader(pistas);
  const url=URL.createObjectURL(archivo);
  try {
    const r=await lector.decodeFromImageUrl(url);
    return String(r.getText() || '').trim();
  } catch { throw new Error('No se pudo leer el código. Encuadra una sola etiqueta, con buena luz y sin reflejos, y toma otra foto.'); }
  finally { lector.reset(); URL.revokeObjectURL(url); }
}
