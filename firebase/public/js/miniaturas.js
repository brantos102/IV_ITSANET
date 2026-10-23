/** Vistas privadas: dos lecturas simultáneas, carga visible y sin reintentos en bucle. */
const cola=[],pendientes=new Map(),fallidas=new Map();let activas=0,observador=null;
const vacia='data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="240" height="180"%3E%3Crect width="100%25" height="100%25" fill="%23edf2f7"/%3E%3C/svg%3E';
function avanzar(){while(activas<2&&cola.length){const tarea=cola.shift();if(tarea.img&&!tarea.img.isConnected)continue;activas++;tarea.ejecutar().finally(()=>{activas--;avanzar();});}}
async function obtener(url){
 if((fallidas.get(url)||0)>Date.now())throw Error('Vista previa temporalmente no disponible.');
 if(pendientes.has(url))return pendientes.get(url);
 const p=(async()=>{const control=new AbortController(),timer=setTimeout(()=>control.abort(),15000);try{const r=await fetch(url+'?miniatura=1',{credentials:'same-origin',signal:control.signal});if(!r.ok||r.status===204||!/^image\//i.test(r.headers.get('content-type')||''))throw Error('Vista previa no disponible.');return await r.blob();}finally{clearTimeout(timer);}})();
 pendientes.set(url,p);try{return await p;}catch(e){fallidas.set(url,Date.now()+30000);while(fallidas.size>256)fallidas.delete(fallidas.keys().next().value);throw e;}finally{pendientes.delete(url);}
}
export function cargarMiniatura(img,url,{inmediata=false}={}){
 if(!/^\/api\/app\/archivos\/[A-Za-z0-9_-]+$/.test(url||''))return;
 img.src=vacia;img.dataset.miniaturaEstado='pendiente';
 const version=(img._versionMiniatura||0)+1;img._versionMiniatura=version;
 const ejecutar=async()=>{try{const blob=await obtener(url);if(!img.isConnected||img._versionMiniatura!==version)return;const src=URL.createObjectURL(blob);const liberar=()=>URL.revokeObjectURL(src);img.addEventListener('load',liberar,{once:true});img.addEventListener('error',liberar,{once:true});setTimeout(liberar,15000);img.src=src;img.dataset.miniaturaEstado='lista';}catch{if(img.isConnected&&img._versionMiniatura===version){img.dataset.miniaturaEstado='no-disponible';img.dispatchEvent(new Event('error'));}}};
 const iniciar=()=>{cola.push({img,ejecutar});avanzar();};
 if(inmediata||!globalThis.IntersectionObserver){requestAnimationFrame(iniciar);return;}
 if(!observador)observador=new IntersectionObserver(entradas=>{for(const e of entradas)if(e.isIntersecting){observador.unobserve(e.target);const iniciar=e.target._cargarMiniatura;delete e.target._cargarMiniatura;iniciar?.();}},{rootMargin:'80px'});
 img._cargarMiniatura=iniciar;requestAnimationFrame(()=>{if(img.isConnected)observador.observe(img);});
}
export function limpiarMiniaturas(raiz){for(const img of raiz.querySelectorAll('img')){observador?.unobserve(img);delete img._cargarMiniatura;img._versionMiniatura=(img._versionMiniatura||0)+1;}}

/** Misma cola acotada para la copia manual, con autorización de la sesión. */
export function leerMiniatura(url){
 if(!/^\/api\/app\/archivos\/[A-Za-z0-9_-]+$/.test(url||''))return Promise.reject(Error('Fotografía inválida.'));
 return new Promise((resolve,reject)=>{cola.push({ejecutar:async()=>{try{const b=await obtener(url);if(b.size>1048576)throw Error('Vista previa demasiado grande.');resolve(b);}catch(e){reject(e);}}});avanzar();});
}
