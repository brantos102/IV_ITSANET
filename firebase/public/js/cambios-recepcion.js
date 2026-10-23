/** Un canal por recepción y página. Solo invalida vistas; jamás guarda un conteo. */
const canales=new Map();
const visible=()=>typeof document==='undefined'||!document.hidden;
const emitir=(nombre,detail)=>{if(typeof document!=='undefined'&&typeof document.dispatchEvent==='function'&&typeof CustomEvent!=='undefined')document.dispatchEvent(new CustomEvent(nombre,{detail}));};
function notificar(c,aviso){
 for(const o of c.oyentes){try{Promise.resolve(o.cambiar(aviso)).catch(e=>o.fallar?.(e));}catch(e){o.fallar?.(e);}}
 emitir('itsanet:operacion-actualizada',aviso);
}
function estado(c,modo){if(c.modo===modo)return;const anterior=c.modo;c.modo=modo;emitir('itsanet:sincronizacion',{recepcion:c.codigo,modo});if(anterior==='sin_conexion'&&['directa','respaldo'].includes(modo))notificar(c,{recepcion:c.codigo,secciones:c.codigo?['conteos','recepcion','imagenes']:['operacion','catalogo'],reconectado:true});}
function recibir(c,d){
 if(!visible()||d.revision===c.revision)return;
 const secciones=Array.isArray(d.secciones)?d.secciones:Object.keys(d.secciones||{}).filter(k=>c.huellas?.[k]!==d.secciones[k]);
 c.revision=d.revision;if(!Array.isArray(d.secciones))c.huellas=d.secciones;
 notificar(c,{...d,secciones});
}
function arrancar(c){
 if(c.cerrado||!visible())return;
 const ruta='/api/operacion'+(c.codigo?'/recepciones/'+encodeURIComponent(c.codigo):'')+'/cambios';
 async function respaldo(){
  if(c.cerrado||!visible()||c.consultando)return;c.consultando=true;const control=new AbortController();c.control=control;let tiempoAgotado=false;const limite=setTimeout(()=>{tiempoAgotado=true;control.abort();},8000);
  try{const r=await fetch(ruta+'/estado',{credentials:'same-origin',cache:'no-store',signal:control.signal});if(!r.ok)throw Object.assign(new Error(r.status===401?'Tu sesión caducó: vuelve a entrar.':'No se pudo comprobar la actualización de la recepción.'),{status:r.status});const d=await r.json();if(c.cerrado)return;recibir(c,d);estado(c,'respaldo');}
  catch(e){if(!c.cerrado&&(e.name!=='AbortError'||tiempoAgotado)){const cambio=c.modo!=='sin_conexion';estado(c,'sin_conexion');if(cambio)for(const o of c.oyentes)o.fallar?.(e);}}
  finally{clearTimeout(limite);c.consultando=false;if(c.control===control)c.control=null;}
 }
 c.respaldo=()=>{if(!c.reloj)c.reloj=setInterval(respaldo,4000);respaldo();};
 if(typeof EventSource==='undefined'){c.respaldo();return;}
 try{
  c.fuente=new EventSource(ruta,{withCredentials:true});
  c.espera=setTimeout(()=>c.respaldo(),3500);
  c.fuente.addEventListener('cambio',e=>{if(c.cerrado)return;try{const d=JSON.parse(e.data);c.control?.abort();clearTimeout(c.espera);clearInterval(c.reloj);c.reloj=null;estado(c,'directa');recibir(c,d);}catch{c.respaldo();}});
  c.fuente.onerror=()=>{if(!c.cerrado&&visible())c.respaldo();};
 }catch{c.respaldo();}
}
function detener(c){c.control?.abort();c.fuente?.close();c.fuente=null;clearInterval(c.reloj);clearTimeout(c.espera);c.reloj=null;}

/** Secciones: conteos, recepcion, imagenes, presencia; global: operacion. */
export function escucharCambiosRecepcion(codigo='',alCambiar=()=>{},alFallar=null){
 if(typeof window==='undefined'||typeof document==='undefined')return ()=>{};
 const key=String(codigo||'');let c=canales.get(key);
 if(!c){c={codigo:key,oyentes:new Set(),cerrado:false,revision:'',modo:'conectando'};canales.set(key,c);
  c.visibilidad=()=>{detener(c);if(visible()){c.revision='';arrancar(c);}};
  c.salir=()=>detener(c);document.addEventListener('visibilitychange',c.visibilidad);window.addEventListener('pagehide',c.salir);
  window.addEventListener('pageshow',c.visibilidad);
 }
 const o={cambiar:alCambiar,fallar:alFallar};c.oyentes.add(o);
 if(!c.fuente&&!c.reloj)arrancar(c);
 return ()=>{c.oyentes.delete(o);if(c.oyentes.size)return;c.cerrado=true;detener(c);document.removeEventListener('visibilitychange',c.visibilidad);window.removeEventListener('pagehide',c.salir);window.removeEventListener('pageshow',c.visibilidad);canales.delete(key);};
}

/** Confirmación de escritura propia: actualiza las otras vistas de esta página. */
export function avisarCambioLocal(recepcion,secciones=['conteos']){
 const aviso={recepcion,secciones,local:true};const c=canales.get(String(recepcion||''));if(c)notificar(c,aviso);else emitir('itsanet:operacion-actualizada',aviso);
 const global=canales.get('');if(global&&global!==c)notificar(global,{recepcion:'',secciones:['operacion'],local:true});
}
