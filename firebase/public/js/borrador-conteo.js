/** Borrador local por cuenta/recepción/pestaña. Nunca envía ni registra unidades. */
import {nuevoIdentificador} from './local.js?v=20261019-54';
let conexion;
function abrir(){
 if(!globalThis.indexedDB)return Promise.reject(new Error('No hay almacenamiento local de fotos en este navegador.'));
 if(!conexion)conexion=new Promise((ok,no)=>{const r=indexedDB.open('itsanet-borradores-conteo',1);r.onupgradeneeded=()=>r.result.createObjectStore('borradores',{keyPath:'clave'});r.onsuccess=()=>{const db=r.result;db.onversionchange=()=>{db.close();conexion=null;};ok(db);};r.onerror=r.onblocked=()=>{conexion=null;no(new Error('No se pudo abrir la copia local del conteo.'));};});
 return conexion;
}
async function transaccion(clave,valor,modo='get'){
 const db=await abrir();return new Promise((ok,no)=>{const tx=db.transaction('borradores',modo==='get'?'readonly':'readwrite'),s=tx.objectStore('borradores'),r=modo==='get'?s.get(clave):modo==='delete'?s.delete(clave):s.put(valor);let resultado;r.onsuccess=()=>resultado=r.result;tx.oncomplete=()=>ok(resultado);tx.onerror=tx.onabort=()=>no(new Error('No se confirmó la copia local. Conserva la pantalla y las imágenes originales.'));});
}
export function crearBorradorConteo({actor,recepcion,almacen}={}){
 if(!actor||!recepcion)throw new Error('Falta la cuenta o recepción del borrador.');
 if(!almacen)try{almacen=globalThis.sessionStorage;}catch{}
 let pestana;try{pestana=almacen?.getItem('itsanet.conteo.pestana');}catch{}
 if(!pestana){pestana=nuevoIdentificador();try{almacen?.setItem('itsanet.conteo.pestana',pestana);}catch{}}
 const contexto={actor:String(actor),recepcion:String(recepcion).toUpperCase()},clave='conteo:'+JSON.stringify([contexto.actor,contexto.recepcion,pestana]);let cola=Promise.resolve(),local=null;const ids=new WeakMap();const identificar=f=>{if(!ids.has(f))ids.set(f,nuevoIdentificador());return ids.get(f);};
 const valida=r=>r?.actor===contexto.actor&&r?.recepcion===contexto.recepcion;
 const escribir=r=>{local=r;try{almacen?.setItem(clave,JSON.stringify(r));}catch{}};
 function anotar(datos){const r={...contexto,fecha:new Date().toISOString(),datos};escribir(r);return r;}
 function guardar(datos,fotos=[],cache=[]){
  const meta=anotar({...datos,fotosIds:fotos.map(identificar)}),snapshot={clave,...meta,fotos:fotos.map((f,i)=>({id:identificar(f),blob:f,nombre:f.name,tipo:f.type,modificada:f.lastModified,url:cache[i]||''}))};
  const actual=cola.catch(()=>{}).then(()=>transaccion(clave,snapshot,'put'));cola=actual;return actual;
 }
 async function recuperar(){
  let meta;try{meta=JSON.parse(almacen?.getItem(clave)||'null');}catch{}meta=meta||local;
  if(meta?.descartado)return null;
  let copia;try{copia=await transaccion(clave);}catch{}
  if(!valida(meta))meta=null;if(!valida(copia))copia=null;
  const r=meta||copia;if(!r?.datos)return null;
  const misma=copia?.datos?.claveEnvio===r.datos.claveEnvio&&copia?.datos?.actual?.sku===r.datos.actual?.sku;
  const porId=new Map((copia?.fotos||[]).map(f=>[f.id,f]));
  const fotos=misma?(r.datos.fotosIds||[]).map(id=>porId.get(id)).filter(f=>f?.blob instanceof Blob).map(f=>{const archivo=new File([f.blob],f.nombre||'evidencia.jpg',{type:f.tipo||f.blob.type,lastModified:f.modificada});ids.set(archivo,f.id);return {archivo,url:f.url||''};}):[];
  return {...r,fotos};
 }
 function borrar(){escribir({...contexto,descartado:true});const actual=cola.catch(()=>{}).then(()=>transaccion(clave,null,'delete'));cola=actual;return actual;}
 return {anotar,guardar,recuperar,borrar,identificar,clave};
}
