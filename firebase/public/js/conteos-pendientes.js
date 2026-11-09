/** Cola durable del dispositivo. Un pendiente nunca se presenta como un conteo del servidor. */
import {nuevoIdentificador} from './local.js?v=20261109-71';

export function crearAlmacenPendientes(nombre='itsanet-conteos-pendientes') {
 let conexion;
 function abrir(){
  if(!globalThis.indexedDB)throw new Error('Este navegador no ofrece almacenamiento local seguro para pendientes. Conserva la ficha abierta.');
  if(!conexion)conexion=new Promise((ok,no)=>{const r=indexedDB.open(nombre,1);
   r.onupgradeneeded=()=>{const s=r.result.createObjectStore('trabajos',{keyPath:'id'});s.createIndex('actor','actor');};
   r.onsuccess=()=>{const db=r.result;db.onversionchange=()=>{db.close();conexion=null;};ok(db);};
   r.onerror=r.onblocked=()=>{conexion=null;no(new Error('No se pudo abrir la cola local. No cierres ni borres la ficha.'));};
  });return conexion;
 }
 async function mutar(id,fn){const db=await abrir();return new Promise((ok,no)=>{
  const tx=db.transaction('trabajos','readwrite'),s=tx.objectStore('trabajos'),r=s.get(id);let resultado,error;
  r.onsuccess=()=>{try{resultado=fn(r.result);if(resultado)s.put(resultado);}catch(e){error=e;tx.abort();}};
  tx.oncomplete=()=>ok(resultado);tx.onerror=tx.onabort=()=>no(error&&error.name!=='QuotaExceededError'?error:new Error('No se confirmó el guardado local. Puede faltar espacio. Conserva la ficha y sus fotos.'));
 });}
 async function listar(actor){const db=await abrir();return new Promise((ok,no)=>{const tx=db.transaction('trabajos'),r=tx.objectStore('trabajos').index('actor').getAll(String(actor));let filas;
  r.onsuccess=()=>filas=r.result;tx.oncomplete=()=>ok(filas.sort((a,b)=>a.fecha.localeCompare(b.fecha)));tx.onerror=tx.onabort=()=>no(new Error('No se pudo leer la cola del dispositivo.'));
 });}
 return {mutar,listar};
}

export const esFalloTransitorio=e=>['SIN_RED','SIN_RESPUESTA_APP','SIN_SESION'].includes(e?.codigo)||
 e?.name==='AbortError'||e?.estado===429||e?.estado>=500;

export function crearColaConteos({actor,transportar,alCambiar=()=>{},alConfirmar=()=>{},almacen=crearAlmacenPendientes(),ahora=()=>Date.now()}={}){
 if(!actor||typeof transportar!=='function')throw new Error('Falta cuenta o transporte de la cola.');
 actor=String(actor);const propietario=nuevoIdentificador();let trabajando=null,activo=true,reloj=null;
 let dispositivo;try{dispositivo=localStorage.getItem('itsanet.conteos.dispositivo');if(!dispositivo){dispositivo=nuevoIdentificador();localStorage.setItem('itsanet.conteos.dispositivo',dispositivo);}}catch{dispositivo=nuevoIdentificador();}
 const vigente=()=>{if(!activo)throw Object.assign(new Error('La pantalla cambió de sesión. El pendiente se conserva.'),{codigo:'CUENTA_CAMBIADA'});};
 async function notificar(){try{await alCambiar(await almacen.listar(actor));}catch{/* El aviso no confirma ni elimina trabajos. */}}
 async function guardar({recepcion,tipo='CONTEO',cuerpo,fotos=[],datosFotos={}}){
  vigente();const id=cuerpo?.idempotencyKey;
  if(!id||!recepcion||!['CONTEO','CERO','REPARTO'].includes(tipo)||!Number.isFinite(Number(cuerpo.cantidad))||Number(cuerpo.cantidad)<0||Number(cuerpo.cantidad)>100000)throw new Error('El conteo pendiente no es válido. Revisa cantidad, recepción e identificador.');
  if(fotos.some(f=>!(f instanceof Blob)))throw new Error('No se confirmó una de las fotos. Conserva la ficha y vuelve a seleccionarla.');
  const payload=JSON.parse(JSON.stringify(cuerpo)),firma=JSON.stringify([actor,recepcion,tipo,payload,datosFotos,fotos.map(f=>[f.name,f.size,f.lastModified])]);
  const j=await almacen.mutar(id,previo=>{if(previo){if(previo.actor!==actor||previo.firma!==firma)throw new Error('Este identificador ya tiene otro pendiente. Revisa la cola antes de repetir.');return previo;}
   const fecha=new Date(ahora()).toISOString();return {id,actor,recepcion:String(recepcion).toUpperCase(),tipo,firma,fecha,estado:'PENDIENTE',intentos:0,proximo:0,
    cuerpo:{...payload,operadorPendiente:actor,capturadoEnDispositivo:fecha,dispositivoOrigen:dispositivo,envioDiferido:true},datosFotos,
    fotos:fotos.map(f=>({blob:f,nombre:f.name||'evidencia.jpg',tipo:f.type,url:''}))};});
  // Solo después del commit de IndexedDB se permite limpiar el formulario.
  await notificar();return j;
 }
 async function sincronizar(forzar=false){
  if(trabajando)return trabajando;if(!activo)return;
  trabajando=(async()=>{
   for(const candidato of await almacen.listar(actor)){
    if(!activo)break;
    if(candidato.estado==='CONFIRMADO'||candidato.estado==='REVISION')continue;
    if(!forzar&&Number(candidato.proximo)>ahora())continue;
    const j=await almacen.mutar(candidato.id,p=>{
     if(!p||p.actor!==actor||['CONFIRMADO','REVISION'].includes(p.estado)||p.dueno&&p.dueno!==propietario&&p.hasta>ahora())return undefined;
     return {...p,estado:'ENVIANDO',dueno:propietario,hasta:ahora()+60000,intentos:p.intentos+1};});
    if(!j)continue;
    const actualizar=patch=>almacen.mutar(j.id,p=>{
     if(p?.actor!==actor||p.dueno!==propietario)throw new Error('La cola cambió de pestaña. Se conserva el identificador original.');
     return {...p,...patch};});
    const latido=setInterval(()=>actualizar({hasta:ahora()+60000}).catch(()=>{}),15000);
    try{
     await notificar();vigente();
     const resultado=await transportar(j,{vigente,actualizar});vigente();
     const confirmado=await actualizar({estado:'CONFIRMADO',resultado,confirmadoEn:new Date(ahora()).toISOString(),fotos:[],dueno:null,hasta:0,error:null});
     try{await alConfirmar(confirmado);}catch{/* El ACK ya está persistido; no repetir por un error de presentación. */}
    }catch(e){
     const temporal=esFalloTransitorio(e);await actualizar({estado:temporal?'PENDIENTE':'REVISION',dueno:null,hasta:0,
      proximo:ahora()+Math.min(60000,5000*2**Math.min(j.intentos-1,4)),error:{codigo:e.codigo||e.name||'ERROR',mensaje:e.message||'No se confirmó el envío.'}});
     // Una caída afecta a todos; evita una solicitud fallida por cada registro.
     if(temporal)break;
    }finally{clearInterval(latido);await notificar();}
   }
  })().finally(()=>{trabajando=null;});return trabajando;
 }
 async function reintentar(id,{confirmarSobrante=false,repartoVigente,embarqueFoto}={}){
  await almacen.mutar(id,j=>{if(!j||j.actor!==actor||j.estado!=='REVISION')throw new Error('Selecciona un pendiente en revisión de tu cuenta.');
   if(confirmarSobrante&&j.error?.codigo!=='CONFIRMAR_SOBRANTE')throw new Error('El servidor no ha solicitado confirmar un sobrante.');
   if(embarqueFoto!==undefined&&j.error?.codigo!=='ELEGIR_EMBARQUE')throw new Error('Este pendiente no solicita cambiar el destino de las fotos.');
   return {...j,estado:'PENDIENTE',proximo:0,error:null,datosFotos:{...j.datosFotos,...(embarqueFoto!==undefined?{embarqueFoto}:{})},cuerpo:{...j.cuerpo,...(confirmarSobrante?{confirmarSobrante:true}:{}),
    ...(repartoVigente!==undefined&&j.tipo==='REPARTO'?{contadoEsperado:repartoVigente}:{})}};});
  await notificar();return sincronizar(true);
 }
 async function restaurar(trabajos){
  vigente();if(!Array.isArray(trabajos)||trabajos.length>5000)throw new Error('El respaldo no contiene una lista válida de pendientes.');
  for(const j of trabajos)if(!j||j.actor!==actor||typeof j.id!=='string'||!j.id||j.id.length>80||!j.recepcion||!['CONTEO','CERO','REPARTO'].includes(j.tipo)||
    j.cuerpo?.idempotencyKey!==j.id||!j.cuerpo.sku||!Number.isFinite(Number(j.cuerpo.cantidad))||Number(j.cuerpo.cantidad)<0||Number(j.cuerpo.cantidad)>100000||
    !Array.isArray(j.fotos)||j.fotos.some(f=>!(f.blob instanceof Blob)))throw new Error('El respaldo tiene datos inválidos o pertenece a otra cuenta.');
  let nuevas=0;
  for(const j of trabajos)await almacen.mutar(j.id,p=>{
   if(p){if(p.actor!==actor)throw new Error('El identificador del respaldo pertenece a otra cuenta.');return p;}
   nuevas++;return {...j,estado:'PENDIENTE',dueno:null,hasta:0,proximo:0,intentos:0,error:null,cuerpo:{...j.cuerpo,operadorPendiente:actor}};
  });
  await notificar();return nuevas;
 }
 const reconectar=()=>{sincronizar(true).catch(()=>{});};
 function iniciar(){reloj=setInterval(()=>sincronizar().catch(()=>{}),5000);globalThis.addEventListener?.('online',reconectar);reconectar();}
 function detener(){activo=false;clearInterval(reloj);globalThis.removeEventListener?.('online',reconectar);}
 return {guardar,sincronizar,reintentar,restaurar,iniciar,detener,listar:()=>almacen.listar(actor),notificar};
}
