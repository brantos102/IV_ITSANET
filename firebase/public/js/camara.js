/**
 * Escaneo con la cámara del teléfono.
 *
 * El 80% de la operación es en handheld o celular. Muchos llevan pistola, pero
 * no todos, y a veces el código está en una etiqueta a la que la pistola no
 * llega bien —una caja al fondo de un pallet, un código impreso pequeño—.
 *
 * Se usa `BarcodeDetector`, que viene en el propio navegador: en Chrome de
 * Android funciona sin instalar nada ni cargar librerías. Donde no está —Safari
 * de iPhone, por ejemplo— el lector local ZXing procesa el mismo video en
 * vivo. Ambos necesitan permiso de cámara y un origen seguro (HTTPS).
 */

const FORMATOS = [
  'code_128', 'code_39', 'code_93', 'codabar',
  'ean_13', 'ean_8', 'upc_a', 'upc_e',
  'itf', 'data_matrix', 'qr_code',
];

export const camaraDisponible = () =>
  typeof window !== 'undefined'
  && window.isSecureContext !== false
  && !!navigator.mediaDevices?.getUserMedia;

/** Por qué no se puede, en términos que digan qué hacer. */
export function motivoNoDisponible() {
  if (typeof window === 'undefined') return 'Sin navegador.';
  if (window.isSecureContext === true && !navigator.mediaDevices?.getUserMedia) {
    return 'Este navegador no ofrece acceso a la cámara. Abre la app directamente en Chrome o Safari actualizado y revisa los permisos del dispositivo.';
  }
  if (window.isSecureContext === false || !navigator.mediaDevices?.getUserMedia) {
    return 'La cámara en vivo requiere abrir la app por HTTPS con un certificado confiable. '
         + 'La IP interna por HTTP no permite activarla. Solicita al administrador la dirección HTTPS.';
  }
  return '';
}

/** Distingue el requisito HTTPS del permiso y de una cámara ocupada. */
export function errorDeCamara(error) {
  if (!camaraDisponible()) return motivoNoDisponible();
  if (['NotAllowedError','SecurityError'].includes(error?.name))
    return 'Permite Cámara en los permisos de este sitio y del navegador en el teléfono; vuelve a tocar Cámara.';
  if (['NotFoundError','DevicesNotFoundError'].includes(error?.name))
    return 'No se encontró una cámara disponible. Revisa la cámara del teléfono o usa el lector de códigos.';
  if (['NotReadableError','TrackStartError','AbortError'].includes(error?.name))
    return 'La cámara está ocupada o no pudo iniciarse. Cierra otras apps o pestañas que la usen y vuelve a intentarlo.';
  return 'No se pudo iniciar la cámara. Cierra el visor y vuelve a intentarlo.';
}

async function lectorDeVideo() {
  if (typeof window.BarcodeDetector === 'function') {
    try {
      const soportados = window.BarcodeDetector.getSupportedFormats ? await window.BarcodeDetector.getSupportedFormats() : FORMATOS;
      const formatos = FORMATOS.filter(f=>soportados.includes(f));
      if (formatos.length) {
        const detector = new window.BarcodeDetector({formats:formatos});
        return {leer:video=>detector.detect(video),cerrar(){}};
      }
    } catch { /* Un lector nativo no compatible usa el respaldo sobre video. */ }
  }
  const {MultiFormatReader, DecodeHintType, BarcodeFormat, BinaryBitmap, HybridBinarizer, HTMLCanvasElementLuminanceSource} = await import('../vendor/zxing.js?v=20261017-36');
  const lector = new MultiFormatReader();
  lector.setHints(new Map([[DecodeHintType.TRY_HARDER,true],
    [DecodeHintType.POSSIBLE_FORMATS,FORMATOS.map(f=>BarcodeFormat[f.toUpperCase()])]]));
  const canvas = document.createElement('canvas');
  const contexto = canvas.getContext('2d',{willReadFrequently:true});
  return {
    leer(video) {
      if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
        canvas.width=video.videoWidth;canvas.height=video.videoHeight;
      }
      contexto.drawImage(video,0,0);
      const bitmap = new BinaryBitmap(new HybridBinarizer(new HTMLCanvasElementLuminanceSource(canvas)));
      return [{rawValue:lector.decodeWithState(bitmap).getText()}];
    },
    cerrar(){lector.reset();canvas.width=0;canvas.height=0;},
  };
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
  if (!camaraDisponible()) throw new Error(motivoNoDisponible());
  const intervaloMs = opciones.intervaloMs || 180;
  // El mismo código delante de la cámara se lee treinta veces por segundo. Sin
  // esta espera, un solo acercamiento registraría decenas de unidades.
  const repetirTrasMs = opciones.repetirTrasMs ?? 2500;

  const detector = await lectorDeVideo();
  let flujo;
  try { flujo = await navigator.mediaDevices.getUserMedia({
    video: {
      // La trasera: la frontal enfoca al operario.
      facingMode: { ideal: 'environment' },
      width: { ideal: 1280 },
      height: { ideal: 720 },
    },
    audio: false,
  }); } catch(e) { detector.cerrar(); throw e; }

  video.srcObject = flujo;
  video.setAttribute('playsinline', '');   // iOS no abre pantalla completa
  video.muted = true;
  try { await video.play(); }
  catch(e) { for (const pista of flujo.getTracks()) pista.stop(); video.srcObject=null; detector.cerrar(); throw e; }

  let ultimo = '';
  let ultimoEn = 0;
  let vivo = true;
  let detectando = false;

  const temporizador = setInterval(async () => {
    if (!vivo || detectando || video.readyState < 2 || (opciones.puedeLeer && !opciones.puedeLeer())) return;
    detectando = true;
    try {
      const codigos = await detector.leer(video);
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
    detector.cerrar();
  };
}
