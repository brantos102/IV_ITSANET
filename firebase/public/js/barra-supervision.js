import {pedir} from './local.js?v=20261018-40.1';
import {abrirEtiqueta} from './etiquetas.js?v=20261018-40.1';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function iniciarBarra({usuario,perfil}){
 const cabecera=document.querySelector('.envoltorio>header,body>header');
 document.querySelector('#barraSupervision')?.remove();
 if(!cabecera||!usuario||!['SUPERVISOR','ADMIN'].includes(perfil?.rol))return;
 const nav=document.createElement('nav');nav.id='barraSupervision';nav.className='acciones barra-supervision';nav.setAttribute('aria-label','Herramientas de supervisión');
 nav.innerHTML='<button class="b-sec" data-catalogo title="Consultar Depot y actualizar el catálogo de productos">↻ Catálogo</button><button class="b-sec" data-etiqueta>▥ Etiqueta por código</button>';
 const inicio=cabecera.querySelector('a[href="./"],a[href="./index.html"]');
 (inicio?.parentElement||cabecera).append(nav);
 nav.querySelector('[data-catalogo]').onclick=()=>abrirCatalogo();
 nav.querySelector('[data-etiqueta]').onclick=()=>etiquetaCatalogo();
}
function dialogo(titulo){const d=document.createElement('dialog');d.className='modal-operativa';d.innerHTML=`<header class="acciones"><h2>${titulo}</h2><button class="b-sec" data-cerrar>Cerrar</button></header><div data-cuerpo></div><p role="status" data-estado></p>`;document.body.append(d);d.showModal();d.querySelector('[data-cerrar]').onclick=()=>d.close();d.addEventListener('close',()=>d.remove());return d;}
async function abrirCatalogo(){
 const d=dialogo('Catálogo de Depot'),c=d.querySelector('[data-cuerpo]'),estado=d.querySelector('[data-estado]');
 c.innerHTML='<p>Actualiza los productos desde las conexiones Depot guardadas por ADMIN. Puedes continuar contando con el catálogo actual mientras se consulta.</p><button class="b-primario" data-actualizar>Actualizar catálogo ahora</button>';
 try{const r=await pedir('/estado',{base:'/api/catalogo'});estado.textContent=`${r.productos_en_cache??r.productos??0} productos · última actualización: ${r.actualizado_en?new Date(r.actualizado_en).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}):'sin confirmar'}`;}catch(e){estado.textContent=e.message;}
 c.querySelector('button').onclick=async ev=>{const b=ev.currentTarget;b.disabled=true;d.querySelector('[data-cerrar]').disabled=true;estado.textContent='Consultando Depot y actualizando productos…';try{const r=await pedir('/depot/sincronizar',{base:'/api/catalogo',cuerpo:{}});estado.textContent=`Catálogo actualizado: ${r.productos} productos.${r.errores?.length?' Conexiones pendientes: '+r.errores.join(', '):''}`;}catch(e){estado.textContent=e.message;}finally{b.disabled=false;d.querySelector('[data-cerrar]').disabled=false;}};
}
let recursos=null;
function cargarRecursosEtiqueta(){
 if(recursos)return recursos;
 recursos=Promise.all([
  globalThis.JsBarcode?Promise.resolve():new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=new URL('../vendor/JsBarcode.all.min.js?v=20261018-40',import.meta.url).href;script.onload=resolve;script.onerror=()=>{script.remove();reject(new Error('No se pudo cargar el código de barras. Recarga y vuelve a intentar.'));};document.head.append(script);}),
  document.querySelector('link[href*="css/operacion.css"]')?Promise.resolve():new Promise((resolve,reject)=>{const link=document.createElement('link');link.rel='stylesheet';link.href=new URL('../css/operacion.css',import.meta.url).href;link.onload=resolve;link.onerror=()=>{link.remove();reject(new Error('No se pudo cargar el formato de etiquetas.'));};document.head.append(link);})
 ]).catch(e=>{recursos=null;throw e;});return recursos;
}
async function etiquetaCatalogo(){
 const d=dialogo('Imprimir etiqueta desde el catálogo'),c=d.querySelector('[data-cuerpo]'),estado=d.querySelector('[data-estado]');
 c.innerHTML='<form><label class="campo"><span>Código SKU o código de barras</span><input data-codigo required minlength="3" placeholder="Escanea o escribe el código"></label><button class="b-primario">Buscar en catálogo</button></form><div data-resultados></div>';
 c.querySelector('form').onsubmit=async ev=>{ev.preventDefault();estado.textContent='Buscando en el catálogo actualizado…';c.querySelector('[data-resultados]').replaceChildren();try{const filas=await pedir('/buscar?q='+encodeURIComponent(c.querySelector('input').value.trim())+'&limite=30',{base:'/api/catalogo'});const disponibles=filas.filter(f=>!f.inactivo&&f.existeDepot);estado.textContent=disponibles.length?`${disponibles.length} productos disponibles. Selecciona el código y cliente correctos.`:'No se encontró un producto activo en Depot. Actualiza el catálogo o verifica el código.';for(const f of disponibles){const b=document.createElement('button');b.className='b-sec resultado-catalogo';b.innerHTML=`<b>${esc(f.sku)} · ${esc(f.cliente)}</b><br>${esc(f.descripcion)}`;b.onclick=async()=>{try{await cargarRecursosEtiqueta();abrirEtiqueta({...f,cantidad:1});}catch(e){estado.textContent=e.message;}};c.querySelector('[data-resultados]').append(b);}}catch(e){estado.textContent=e.message;}};
}
