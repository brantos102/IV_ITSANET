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

export const VERSION_LECTOR='20261020-60';

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

/** El recorte coincide con object-fit:cover y con el marco visible, también en vertical. */
export function regionDeLectura(ancho, alto, visorAncho=ancho, visorAlto=alto, completo=false){
  if(!(ancho>0&&alto>0))return null;
  const relacion=visorAncho>0&&visorAlto>0?visorAncho/visorAlto:ancho/alto;
  let w=Math.min(ancho,alto*relacion),h=Math.min(alto,ancho/relacion);
  if(!completo){w*=.84;h*=.76;}
  return {x:(ancho-w)/2,y:(alto-h)/2,w,h};
}

async function lectorDeVideo({foto=false,usarNativo=true}={}) {
  if (usarNativo&&typeof window.BarcodeDetector === 'function') {
    try {
      const soportados = window.BarcodeDetector.getSupportedFormats ? await window.BarcodeDetector.getSupportedFormats() : FORMATOS;
      const formatos = FORMATOS.filter(f=>soportados.includes(f));
      // EAN/QR solamente no cubre las etiquetas alfanuméricas de bodega.
      if (formatos.includes('code_128')) {
        const detector = new window.BarcodeDetector({formats:formatos});let respaldo=null,cerrado=false,intento=0,canvas=null,ctx=null;
        return {motor:'Nativo + respaldo local',intervalo:90,async leer(video,{forzar=false}={}){
          let origen=video;
          const ancho=video.videoWidth||video.naturalWidth,alto=video.videoHeight||video.naturalHeight;
          if(ancho&&alto&&typeof document!=='undefined'){
            canvas ||= document.createElement('canvas');ctx ||= canvas.getContext('2d');
            const cover=typeof getComputedStyle==='function'&&getComputedStyle(video).objectFit==='cover';
            const r=foto?{x:0,y:0,w:ancho,h:alto}:regionDeLectura(ancho,alto,cover?video.clientWidth:ancho,cover?video.clientHeight:alto,forzar||++intento%3===0);
            const escala=foto?1:Math.min(1,1600/Math.max(r.w,r.h));canvas.width=Math.max(1,Math.round(r.w*escala));canvas.height=Math.max(1,Math.round(r.h*escala));
            ctx.drawImage(video,r.x,r.y,r.w,r.h,0,0,canvas.width,canvas.height);origen=canvas;
          }
          let codigos=[];try{codigos=await detector.detect(origen);}catch{if(!forzar)throw new Error('Fotograma ilegible');}
          if(codigos.length||!forzar||cerrado)return codigos;
          respaldo ||= lectorDeVideo({foto,usarNativo:false});const lector=await respaldo;
          if(cerrado){lector.cerrar();return [];}
          return lector.leer(video,{forzar:true});
        },cerrar(){cerrado=true;if(canvas){canvas.width=0;canvas.height=0;}respaldo?.then(r=>r.cerrar());}};
      }
    } catch { /* Un lector nativo no compatible usa el respaldo sobre video. */ }
  }
  const {MultiFormatReader, DecodeHintType, BarcodeFormat, BinaryBitmap, HybridBinarizer, HTMLCanvasElementLuminanceSource} = await import('../vendor/zxing.js?v=20261020-60');
  const formatos=FORMATOS.map(f=>BarcodeFormat[f.toUpperCase()]);
  const rapido=new MultiFormatReader(),completo=new MultiFormatReader();
  rapido.setHints(new Map([[DecodeHintType.POSSIBLE_FORMATS,formatos]]));
  completo.setHints(new Map([[DecodeHintType.TRY_HARDER,true],[DecodeHintType.POSSIBLE_FORMATS,formatos]]));
  const canvas = document.createElement('canvas'),rotado=document.createElement('canvas');
  const contexto = canvas.getContext('2d',{willReadFrequently:true}),contextoRotado=rotado.getContext('2d',{willReadFrequently:true});
  let intento=0;
  const decodificar=(origen,lector)=>[{rawValue:lector.decodeWithState(new BinaryBitmap(new HybridBinarizer(new HTMLCanvasElementLuminanceSource(origen)))).getText()}];
  return {
    motor:'ZXing local',intervalo:110,
    leer(video,{forzar=false}={}) {
      const ancho=video.videoWidth||video.naturalWidth,alto=video.videoHeight||video.naturalHeight;
      if(!ancho||!alto)return [];
      const todo=foto||forzar||++intento%3===0;
      const cover=typeof getComputedStyle==='function'&&getComputedStyle(video).objectFit==='cover';
      const r=foto?{x:0,y:0,w:ancho,h:alto}:regionDeLectura(ancho,alto,cover?video.clientWidth:ancho,cover?video.clientHeight:alto,todo);
      const escala=foto?1:Math.min(1,(todo?1920:1280)/Math.max(r.w,r.h));
      const w=Math.max(1,Math.round(r.w*escala)),h=Math.max(1,Math.round(r.h*escala));
      if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
      contexto.drawImage(video,r.x,r.y,r.w,r.h,0,0,w,h);
      try{return decodificar(canvas,todo?completo:rapido);}catch{
        // También lee etiquetas giradas: no obliga a girar el teléfono.
        if(!todo)return [];
        rotado.width=h;rotado.height=w;contextoRotado.translate(0,w);contextoRotado.rotate(-Math.PI/2);contextoRotado.drawImage(canvas,0,0);
        try{return decodificar(rotado,completo);}catch{return [];}
      }
    },
    cerrar(){rapido.reset();completo.reset();canvas.width=0;canvas.height=0;rotado.width=0;rotado.height=0;},
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
  const repetirTrasMs = opciones.repetirTrasMs ?? 2500;
  const detector = await lectorDeVideo();
  const intervaloMs=Math.max(60,opciones.intervaloMs||detector.intervalo);
  let flujo;
  try { flujo = await navigator.mediaDevices.getUserMedia({
    video: {
      ...(opciones.dispositivo?{deviceId:{exact:opciones.dispositivo}}:{facingMode:{ideal:'environment'}}),
      width: { ideal: 1920 },height: { ideal: 1080 },frameRate: { ideal:30,max:30 },
    },audio:false,
  }); } catch(e) { detector.cerrar(); throw e; }
  const pista=flujo.getVideoTracks?.()[0];let capacidades={};
  try{capacidades=pista?.getCapabilities?.()||{};if(capacidades.focusMode?.includes('continuous'))await pista.applyConstraints({advanced:[{focusMode:'continuous'}]});}catch{/* Ajuste opcional. */}
  video.srcObject = flujo;video.setAttribute('playsinline', '');video.muted = true;
  try { await video.play(); }
  catch(e) { for (const pista of flujo.getTracks()) pista.stop(); video.srcObject=null; detector.cerrar(); throw e; }
  let ultimo='',ultimoEn=0,vivo=true,detectando=false,fotograma=-1;
  async function leer(forzar=false){
    if(!vivo||video.readyState<2)return 'APAGADA';
    if(detectando)return 'OCUPADA';
    if(opciones.puedeLeer&&!opciones.puedeLeer())return 'PAUSADA';
    if(!forzar&&Number.isFinite(video.currentTime)&&video.currentTime===fotograma)return 'SIN_FOTOGRAMA';
    fotograma=video.currentTime;detectando=true;
    try{
      const codigos=await detector.leer(video,{forzar});
      if(!vivo||opciones.puedeLeer&&!opciones.puedeLeer())return 'PAUSADA';
      const unicos=[...new Set(codigos.map(c=>String(c.rawValue||'').trim()).filter(Boolean))];
      if(unicos.length>1)return 'VARIOS';
      const valor=unicos[0];if(!valor)return 'SIN_CODIGO';
      const ahora=Date.now();if(valor===ultimo&&ahora-ultimoEn<repetirTrasMs)return 'REPETIDO';
      ultimo=valor;ultimoEn=ahora;await alLeer(valor);return 'LEIDO';
    }catch{return 'SIN_CODIGO';}finally{detectando=false;}
  }
  const temporizador=setInterval(()=>leer(),intervaloMs);
  function cerrar(){if(!vivo)return;vivo=false;clearInterval(temporizador);for(const p of flujo.getTracks())p.stop();video.srcObject=null;detector.cerrar();}
  // Mantiene la API anterior: la devolución sigue siendo una función de apagado.
  cerrar.leerAhora=()=>leer(true);
  cerrar.zoom=capacidades.zoom&&capacidades.zoom.max>capacidades.zoom.min?{min:capacidades.zoom.min,max:capacidades.zoom.max,step:capacidades.zoom.step||.1,valor:pista?.getSettings?.().zoom||capacidades.zoom.min}:null;
  cerrar.ajustarZoom=async valor=>{if(!vivo||!cerrar.zoom||!Number.isFinite(valor)||valor<cerrar.zoom.min||valor>cerrar.zoom.max)return false;await pista.applyConstraints({advanced:[{zoom:valor}]});return vivo;};
  cerrar.tieneLinterna=capacidades.torch===true;
  cerrar.linterna=async encender=>{if(!vivo||!cerrar.tieneLinterna)return false;await pista.applyConstraints({advanced:[{torch:!!encender}]});return vivo;};
  const ajustes=pista?.getSettings?.()||{};
  cerrar.diagnostico={motor:detector.motor,resolucion:[ajustes.width||video.videoWidth||0,ajustes.height||video.videoHeight||0],fps:ajustes.frameRate||null,zoom:!!cerrar.zoom,linterna:cerrar.tieneLinterna};
  opciones.alEstado?.(cerrar.diagnostico);
  return cerrar;
}
