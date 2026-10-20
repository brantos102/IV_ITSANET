/** Carga privada acotada: Google y archivos originales siempre simulados. */
import fs from 'node:fs';
import assert from 'node:assert/strict';
const fuente=fs.readFileSync(new URL('../public/js/miniaturas.js',import.meta.url),'utf8');
const tareas=[],llamadas=[];let activas=0,maximo=0,pasadas=0,falladas=0;
const pausa=()=>new Promise(r=>setImmediate(r));
async function esperar(fn){for(let i=0;i<100&&!fn();i++)await new Promise(r=>timer(r,5));assert(fn(),'La tarea no terminó');}
globalThis.requestAnimationFrame=fn=>queueMicrotask(fn);
// Evitar que la liberación de object URLs mantenga Node abierto 15 segundos.
const timer=globalThis.setTimeout;globalThis.setTimeout=(fn,ms,...args)=>{const t=timer(fn,ms,...args);t.unref();return t;};
globalThis.fetch=(url,opciones)=>new Promise((resolve,reject)=>{
 llamadas.push(url);activas++;maximo=Math.max(maximo,activas);
 tareas.push((status=200)=>{activas--;resolve(new Response(status===204?null:new Blob(['imagen'],{type:'image/png'}),{status,headers:{'content-type':'image/png'}}));});
 opciones.signal.addEventListener('abort',()=>{activas--;reject(new DOMException('Cancelada','AbortError'));},{once:true});
});
class Imagen extends EventTarget{isConnected=true;dataset={};src='';}
const {cargarMiniatura,limpiarMiniaturas}=await import('data:text/javascript;base64,'+Buffer.from(fuente).toString('base64'));
async function caso(nombre,fn){try{await fn();pasadas++;console.log('  ok '+nombre);}catch(e){falladas++;console.error('FALLA '+nombre,e);}}
await caso('comparar duplicados simultáneos evita repetir la petición privada',async()=>{
 const a=new Imagen(),b=new Imagen();cargarMiniatura(a,'/api/app/archivos/uno');cargarMiniatura(b,'/api/app/archivos/uno');await pausa();assert.equal(llamadas.length,1);tareas.shift()();await esperar(()=>a.dataset.miniaturaEstado==='lista'&&b.dataset.miniaturaEstado==='lista');assert.equal(a.dataset.miniaturaEstado,'lista');assert.equal(b.dataset.miniaturaEstado,'lista');a.dispatchEvent(new Event('load'));b.dispatchEvent(new Event('load'));
});
await caso('lote mantiene máximo dos peticiones y omite imágenes retiradas de la interfaz',async()=>{
 const imagenes=Array.from({length:10},()=>new Imagen());imagenes.forEach((img,i)=>cargarMiniatura(img,'/api/app/archivos/lote'+i));await pausa();assert.equal(activas,2);imagenes[8].isConnected=false;
 while(tareas.length||activas){if(tareas.length)tareas.shift()();await new Promise(r=>timer(r,5));}
 await esperar(()=>imagenes[9].dataset.miniaturaEstado==='lista');
 assert.equal(maximo,2);assert(!llamadas.some(u=>u.includes('lote8?')));assert.equal(imagenes[9].dataset.miniaturaEstado,'lista');imagenes.forEach(img=>img.dispatchEvent(new Event('load')));
});
await caso('204 ofrece alternativa y no vuelve a consultar en bucle',async()=>{
 const a=new Imagen();let errores=0;a.addEventListener('error',()=>errores++);cargarMiniatura(a,'/api/app/archivos/fallida');await pausa();tareas.shift()(204);await pausa();const cantidad=llamadas.length;const b=new Imagen();cargarMiniatura(b,'/api/app/archivos/fallida');await pausa();assert.equal(a.dataset.miniaturaEstado,'no-disponible');assert.equal(b.dataset.miniaturaEstado,'no-disponible');assert.equal(errores,1);assert.equal(llamadas.length,cantidad);
});
await caso('cerrar el modal invalida respuestas tardías y no carga una URL externa',async()=>{
 const a=new Imagen();cargarMiniatura(a,'/api/app/archivos/tardia');await pausa();limpiarMiniaturas({querySelectorAll:()=>[a]});tareas.shift()();await pausa();assert.notEqual(a.dataset.miniaturaEstado,'lista');const antes=llamadas.length;cargarMiniatura(new Imagen(),'https://otro.example/archivo');await pausa();assert.equal(llamadas.length,antes);
});
console.log(`\n  ${pasadas} pasadas, ${falladas} falladas`);if(falladas)process.exitCode=1;
