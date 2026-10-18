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

async function lectorDeVideo({foto=false}={}) {
  if (typeof window.BarcodeDetector === 'function') {
    try {
      const soportados = window.BarcodeDetector.getSupportedFormats ? await window.BarcodeDetector.getSupportedFormats() : FORMATOS;
      const formatos = FORMATOS.filter(f=>soportados.includes(f));
      if (formatos.length) {
        const detector = new window.BarcodeDetector({formats:formatos});
        return {intervalo:90,leer:video=>detector.detect(video),cerrar(){}};
      }
    } catch { /* Un lector nativo no compatible usa el respaldo sobre video. */ }
  }
  const {MultiFormatReader, DecodeHintType, BarcodeFormat, BinaryBitmap, HybridBinarizer, HTMLCanvasElementLuminanceSource} = await import('../vendor/zxing.js?v=20261018-47');
  const formatos=FORMATOS.map(f=>BarcodeFormat[f.toUpperCase()]);
  const rapido=new MultiFormatReader(),completo=new MultiFormatReader();
  rapido.setHints(new Map([[DecodeHintType.POSSIBLE_FORMATS,formatos]]));
  completo.setHints(new Map([[DecodeHintType.TRY_HARDER,true],[DecodeHintType.POSSIBLE_FORMATS,formatos]]));
  const canvas = document.createElement('canvas');
  const contexto = canvas.getContext('2d',{willReadFrequently:true});
  let intento=0;
  return {
    intervalo:110,
    leer(video) {
      const ancho=video.videoWidth||video.naturalWidth,alto=video.videoHeight||video.naturalHeight;
      if(!ancho||!alto)return [];
      // La foto elegida conserva toda su resolución. En vivo alternamos un
      // recorte central rápido y el encuadre completo para no omitir bordes.
      const todo=foto||++intento%2===0;
      const w=todo?ancho:Math.round(ancho*.82),h=todo?alto:Math.round(alto*.64);
      const escala=foto?1:Math.min(1,(todo?1920:1280)/Math.max(w,h));
      const destinoW=Math.max(1,Math.round(w*escala)),destinoH=Math.max(1,Math.round(h*escala));
      if(canvas.width!==destinoW||canvas.height!==destinoH){canvas.width=destinoW;canvas.height=destinoH;}
      contexto.drawImage(video,(ancho-w)/2,(alto-h)/2,w,h,0,0,destinoW,destinoH);
      const bitmap = new BinaryBitmap(new HybridBinarizer(new HTMLCanvasElementLuminanceSource(canvas)));
      return [{rawValue:(todo?completo:rapido).decodeWithState(bitmap).getText()}];
    },
    cerrar(){rapido.reset();completo.reset();canvas.width=0;canvas.height=0;},
  };
}

/** Alternativa sobre HTTP: foto del código elegida por el usuario; no es evidencia ni conteo. */
export async function leerCodigoDeImagen(archivo){
 if(!archivo||!archivo.type.startsWith('image/')||archivo.size>12*1024*1024)throw new Error('Elige una imagen del código de hasta 12 MB.');
 const url=URL.createObjectURL(archivo),img=new Image();let lector;
 try{img.src=url;await img.decode();if(img.naturalWidth*img.naturalHeight>24_000_000)throw new Error('La fotografía es demasiado grande. Acércate al código o recorta la foto.');lector=await lectorDeVideo({foto:true});const codigos=await lector.leer(img);const unicos=[...new Set(codigos.map(c=>c.rawValue).filter(Boolean))];if(unicos.length!==1)throw new Error(unicos.length?'Hay varios códigos. Fotografía solo la etiqueta que deseas consultar.':'No se pudo leer. Acerca la etiqueta, evita reflejos o escribe el código.');return unicos[0];}
 catch(e){if(e.message?.includes('fotograf')||e.message?.includes('códigos')||e.message?.includes('No se pudo leer'))throw e;throw new Error('No se pudo leer el código de esta foto. Acércate a la etiqueta o escribe el código.');}
 finally{lector?.cerrar();URL.revokeObjectURL(url);}
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
  // El mismo código delante de la cámara se lee treinta veces por segundo. Sin
  // esta espera, un solo acercamiento registraría decenas de unidades.
  const repetirTrasMs = opciones.repetirTrasMs ?? 2500;

  const detector = await lectorDeVideo();
  const intervaloMs=Math.max(60,opciones.intervaloMs||detector.intervalo);
  let flujo;
  try { flujo = await navigator.mediaDevices.getUserMedia({
    video: {
      // La trasera: la frontal enfoca al operario.
      facingMode: { ideal: 'environment' },
      width: { ideal: 1920 },
      height: { ideal: 1080 },
      frameRate: { ideal:30,max:30 },
    },
    audio: false,
  }); } catch(e) { detector.cerrar(); throw e; }

  // Es opcional: equipos sin este control mantienen su enfoque predeterminado.
  const pista=flujo.getVideoTracks?.()[0];
  try{if(pista?.getCapabilities?.().focusMode?.includes('continuous'))await pista.applyConstraints({advanced:[{focusMode:'continuous'}]});}catch{/* El navegador conserva la cámara aunque rechace este ajuste. */}

  video.srcObject = flujo;
  video.setAttribute('playsinline', '');   // iOS no abre pantalla completa
  video.muted = true;
  try { await video.play(); }
  catch(e) { for (const pista of flujo.getTracks()) pista.stop(); video.srcObject=null; detector.cerrar(); throw e; }

  let ultimo = '';
  let ultimoEn = 0;
  let vivo = true;
  let detectando = false;
  let fotograma=-1;

  const temporizador = setInterval(async () => {
    if (!vivo || detectando || video.readyState < 2 || (opciones.puedeLeer && !opciones.puedeLeer())) return;
    if(Number.isFinite(video.currentTime)&&video.currentTime===fotograma)return;
    fotograma=video.currentTime;
    detectando = true;
    try {
      const codigos = await detector.leer(video);
      if (!vivo || (opciones.puedeLeer&&!opciones.puedeLeer()) || !codigos.length) return;

      const valor = String(codigos[0].rawValue || '').trim();
      if (!valor) return;

      const ahora = Date.now();
      if (valor === ultimo && ahora - ultimoEn < repetirTrasMs) return;
      ultimo = valor;
      ultimoEn = ahora;
      await alLeer(valor);
    } catch {
      // Un fotograma ilegible es normal. Nunca se procesan dos a la vez.
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
