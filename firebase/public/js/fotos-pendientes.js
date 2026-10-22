import {pedir,nuevoIdentificador} from './local.js?v=20261022-63';
import {confirmar} from './modal.js?v=20261022-63';
let conexion;
const trabajos=new WeakMap();
function abrirDb(){
 if(!globalThis.indexedDB)return Promise.reject(new Error('Este navegador no ofrece almacenamiento local de fotos.'));
 if(!conexion)conexion=new Promise((ok,no)=>{const r=indexedDB.open('itsanet-fotos-pendientes',1);r.onupgradeneeded=()=>r.result.createObjectStore('fotos',{keyPath:'id'});r.onsuccess=()=>ok(r.result);r.onerror=()=>{conexion=null;no(r.error);};});
 return conexion;
}
async function guardar(job){const db=await abrirDb();await new Promise((ok,no)=>{const tx=db.transaction('fotos','readwrite');tx.objectStore('fotos').put(job);tx.oncomplete=ok;tx.onerror=()=>no(tx.error);tx.onabort=()=>no(tx.error||new Error('No se confirmó la copia temporal.'));});}
async function borrar(id){const db=await abrirDb();await new Promise((ok,no)=>{const tx=db.transaction('fotos','readwrite');tx.objectStore('fotos').delete(id);tx.oncomplete=ok;tx.onerror=()=>no(tx.error);});}
async function listar(actor,recepcion){const db=await abrirDb();return new Promise((ok,no)=>{const tx=db.transaction('fotos'),r=tx.objectStore('fotos').getAll();r.onsuccess=()=>ok(r.result.filter(j=>j.actor===actor&&j.recepcion===recepcion).sort((a,b)=>a.fecha.localeCompare(b.fecha)));r.onerror=()=>no(r.error);});}
export const actorFotos=()=>pedir('/yo',{base:'/api/auth'}).then(r=>String(r.id));
export async function subirFotoProtegida(recepcion,f,imagen,datos,actor){
 const firma=JSON.stringify([actor,recepcion,datos]);let item=trabajos.get(f);
 if(!item||item.firma!==firma){const anterior=item?.job;item={firma,job:{id:anterior?.actor===actor&&anterior?.recepcion===recepcion?anterior.id:nuevoIdentificador(),actor,recepcion,fecha:anterior?.fecha||new Date().toISOString(),payload:{...datos,operadorOrigen:actor,nombre:f.name||'evidencia.jpg',base64:imagen.base64,tipo:imagen.tipo}}};trabajos.set(f,item);}
 let persistida=false;try{await guardar(item.job);persistida=true;}catch{/* El envío puede confirmar una foto aunque el navegador no tenga espacio. */}
 let r;try{r=await pedir(`/recepciones/${encodeURIComponent(recepcion)}/archivos/foto`,{cuerpo:item.job.payload});}
 catch(e){if(!persistida)e.message+=' No se pudo crear una copia temporal en este navegador. Conserva la imagen original y mantén esta ventana abierta.';else e.message+=' La copia temporal se conserva para recuperarla desde esta cuenta y este navegador.';throw e;}
 if(persistida){try{await borrar(item.job.id);}catch{/* Reintentar una confirmada conserva la deduplicación del servidor. */}}
 trabajos.delete(f);return r;
}
function descargar(job){const p=job.payload,a=document.createElement('a');a.href='data:'+p.tipo+';base64,'+p.base64;a.download=p.nombre;a.click();}
export async function abrirFotosPendientes(recepcion,{alGuardar=()=>{}}={}){
 const actor=await actorFotos(),d=document.createElement('dialog');d.className='modal-operativa fotos-pendientes-dialogo';
 d.innerHTML='<header><h2>Fotos pendientes de este navegador</h2><button data-cerrar class="b-sec">Cerrar</button></header><p class="guia-modal">Se muestran solo las fotos de tu cuenta y esta recepción. Revisa su destino antes de reintentar. Se conservan hasta confirmar el guardado o descartarlas explícitamente.</p><div data-lista></div><p data-estado role="status"></p>';
 document.body.append(d);d.showModal();let ocupado=false;
 async function pintar(){const raiz=d.querySelector('[data-lista]');raiz.replaceChildren();let filas;try{filas=await listar(actor,recepcion);}catch{raiz.textContent='No se pudo consultar el almacenamiento local. Mantén abiertas las selecciones sin guardar y conserva sus archivos originales.';return;}
  if(!filas.length){raiz.textContent='No hay fotos pendientes de esta cuenta para '+recepcion+'.';return;}
  for(const j of filas){const p=j.payload,card=document.createElement('article'),img=document.createElement('img'),titulo=document.createElement('p'),nota=document.createElement('p');img.src='data:'+p.tipo+';base64,'+p.base64;img.alt=p.nombre;img.style.cssText='width:130px;height:100px;object-fit:contain';titulo.textContent=p.nombre;nota.className='mini';nota.textContent=[p.tipoEvidencia,p.sku&&'SKU '+p.sku,p.unidadId&&'Unidad '+p.unidadId,p.origen&&'Lista '+p.origen,p.embarqueFoto&&'Embarque '+p.embarqueFoto].filter(Boolean).join(' · ');card.append(img,titulo,nota);
   const boton=(texto,fn)=>{const b=document.createElement('button');b.type='button';b.className='b-sec';b.textContent=texto;b.onclick=async()=>{if(ocupado)return;ocupado=true;d.querySelectorAll('button').forEach(x=>x.disabled=true);try{await fn();}catch(e){d.querySelector('[data-estado]').textContent=e.message;}finally{ocupado=false;d.querySelectorAll('button').forEach(x=>x.disabled=false);}};card.append(b);};
   boton('Reintentar guardado',async()=>{if(await actorFotos()!==actor)throw new Error('La sesión cambió. Entra con la cuenta original.');await pedir(`/recepciones/${encodeURIComponent(recepcion)}/archivos/foto`,{cuerpo:p});await borrar(j.id);d.querySelector('[data-estado]').textContent='Foto confirmada en el servidor; copia a Drive en segundo plano.';await alGuardar();await pintar();});
   boton('Descargar copia temporal',()=>descargar(j));
   boton('Descartar copia local',async()=>{if(await confirmar({titulo:'¿Descartar esta copia temporal?',texto:'Conserva o descarga la imagen antes de descartarla. Esta acción no elimina una foto ya guardada en el servidor.',aceptar:'Descartar copia local',peligro:true})){await borrar(j.id);await pintar();}});raiz.append(card);
  }
 }
 d.querySelector('[data-cerrar]').onclick=()=>{if(!ocupado)d.close();};d.addEventListener('cancel',e=>{if(ocupado)e.preventDefault();});d.addEventListener('close',()=>d.remove(),{once:true});await pintar();return d;
}
