import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const anteriores=Object.fromEntries(['window','document','EventSource','fetch'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
const ventana=new EventTarget(),documento=new EventTarget();documento.hidden=false;
Object.defineProperty(globalThis,'window',{value:ventana,configurable:true});
Object.defineProperty(globalThis,'document',{value:documento,configurable:true});
const conexiones=[];
class Fuente extends EventTarget{
 constructor(url){super();this.url=url;this.cerrada=false;conexiones.push(this);}
 close(){this.cerrada=true;}
 recibir(datos){const e=new Event('cambio');Object.defineProperty(e,'data',{value:JSON.stringify(datos)});this.dispatchEvent(e);}
}
Object.defineProperty(globalThis,'EventSource',{value:Fuente,configurable:true});
const {escucharCambiosRecepcion,avisarCambioLocal}=await cargar('cambios-recepcion.js');
const pausa=()=>new Promise(r=>setTimeout(r,5));
try{
 await test('SSE: dos vistas comparten una conexión y solo cambian al recibir nueva revisión',()=>{
  const a=[],b=[],eventos=[];const ver=e=>eventos.push(e.detail);documento.addEventListener('itsanet:operacion-actualizada',ver);
  const uno=escucharCambiosRecepcion('R65',e=>a.push(e)),dos=escucharCambiosRecepcion('R65',e=>b.push(e));
  const f=conexiones.at(-1);eq(conexiones.filter(c=>c.url.includes('R65')).length,1);
  f.recibir({recepcion:'R65',revision:'uno',secciones:['conteos'],equipoSku:[]});f.recibir({recepcion:'R65',revision:'uno',secciones:['conteos'],equipoSku:[]});
  eq(a.length,1);eq(b.length,1);eq(eventos.length,1);
  uno();ok(!f.cerrada);dos();ok(f.cerrada);documento.removeEventListener('itsanet:operacion-actualizada',ver);
 });
 await test('SSE: una escritura confirmada avisa la vista actual y el canal global sin registrar datos',()=>{
  const a=[],b=[];const uno=escucharCambiosRecepcion('R66',e=>a.push(e)),dos=escucharCambiosRecepcion('',e=>b.push(e));
  avisarCambioLocal('R66',['conteos']);eq(a.length,1);eq(b.length,1);ok(a[0].local);eq(b[0].secciones,['operacion']);uno();dos();
 });
 await test('SSE: proxy sin canal directo activa consulta de firma y recupera SSE',async()=>{
  const recibidos=[];let consultas=0;
  globalThis.fetch=async()=>{consultas++;return new Response(JSON.stringify({recepcion:'R67',revision:'respaldo1',secciones:{conteos:'1'},equipoSku:[]}));};
  const parar=escucharCambiosRecepcion('R67',e=>recibidos.push(e));const f=conexiones.at(-1);f.onerror();await pausa();
  eq(consultas,1);eq(recibidos[0].secciones,['conteos']);
  f.recibir({recepcion:'R67',revision:'directa2',secciones:['conteos'],equipoSku:[]});eq(recibidos.length,2);parar();
 });
 await test('SSE: reconectar con la misma revisión recupera la vista tras un fallo de red',async()=>{
  const local=await cargar('local.js'),vistos=[],fallos=[];let sinRed=false;
  globalThis.fetch=async ruta=>{if(String(ruta).endsWith('/estado')&&sinRed)throw new Error('Sin red de prueba');return new Response(JSON.stringify([{sku:'S',contado:2}]));};
  const parar=local.escucharSkus('R69',d=>vistos.push(d),e=>fallos.push(e)),f=conexiones.at(-1);
  f.recibir({recepcion:'R69',revision:'misma',secciones:['conteos'],equipoSku:[]});await pausa();eq(vistos.length,1);
  sinRed=true;f.onerror();await pausa();eq(fallos.length,1);
  sinRed=false;f.recibir({recepcion:'R69',revision:'misma',secciones:['conteos'],equipoSku:[]});await pausa();eq(vistos.length,2);eq(vistos[1][0].contado,2);parar();
 });
 await test('SSE: suspende al ocultar y recupera la revisión al volver sin perder suscriptores',()=>{
  let avisos=0;const parar=escucharCambiosRecepcion('R68',()=>avisos++),f=conexiones.at(-1);
  f.recibir({recepcion:'R68',revision:'uno',secciones:['conteos']});eq(avisos,1);
  documento.hidden=true;documento.dispatchEvent(new Event('visibilitychange'));ok(f.cerrada);
  documento.hidden=false;documento.dispatchEvent(new Event('visibilitychange'));const nueva=conexiones.at(-1);ok(nueva!==f);
  nueva.recibir({recepcion:'R68',revision:'uno',secciones:['conteos']});eq(avisos,2);parar();
 });
}finally{
 for(const [k,v] of Object.entries(anteriores)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k];}
}
resumen();
