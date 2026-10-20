import {iniciarAyudas} from './ayudas-operativas.js?v=20261020-60';
import {pedir} from './local.js?v=20261020-60';
import {abrirEntregas} from './entregas-supervisor.js?v=20261020-60';
import {mostrarAviso} from './notificaciones.js?v=20261020-60';
import {abrirEtiqueta} from './etiquetas.js?v=20261020-60';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let avanceActual=null, liberarBarra=()=>{};
export function publicarAvance(datos){
 avanceActual=datos;
 document.dispatchEvent(new CustomEvent('itsanet:avance',{detail:datos}));
}
export function iniciarBarra({usuario,perfil}){
 iniciarAyudas();liberarBarra();document.querySelector('#barraSupervision')?.remove();
 const cabecera=document.querySelector('.envoltorio>header,body>header,.caja>header,.caja>.sub');
 if(!cabecera||!usuario||!perfil)return;
 const supervisor=['SUPERVISOR','ADMIN'].includes(perfil.rol);
 const nav=document.createElement('nav');nav.id='barraSupervision';nav.className='barra-supervision';nav.setAttribute('aria-label','Navegación y herramientas');
 const aqui=new URL(location.href),codigo=aqui.pathname.endsWith('/validar.html')?aqui.searchParams.get('r'):null;
 const enlaces=[['./','Inicio'],...(supervisor?[['./recepciones.html','Recepciones']]:[]),[codigo?'./validar.html?r='+encodeURIComponent(codigo):'./validar.html','Validar recepción'],...(supervisor?[['./kpis.html','Indicadores'],['./usuarios.html','Equipo']]:[]),['./cuenta.html','Mi cuenta y correo'],['./manuales/'+(supervisor?'supervisor':'operario')+'.html','Ayuda · manual interactivo'],...(perfil.rol==='ADMIN'?[['./admin.html','Administración']]:[])];
 nav.innerHTML=`<div class="barra-fila"><details class="nav-menu"><summary>☰ Menú</summary><div class="nav-opciones">${enlaces.map(([href,t])=>`<a href="${esc(href)}"${new URL(href,location.href).pathname===aqui.pathname?' aria-current="page"':''}>${t}</a>`).join('')}</div></details><div class="barra-contexto"><strong>${codigo?'Recepción actual':'Operación ITSANET'}</strong><span>${esc(perfil.rol==='ADMIN'?'Administración':supervisor?'Supervisión':'Operario')}</span></div><details class="barra-utilidades nav-menu"><summary>Herramientas</summary><div class="barra-herramientas nav-opciones"><button class="b-sec" data-etiqueta>▥ Etiqueta por código</button>${codigo&&supervisor?'<button class="b-sec" data-contenedores title="Registrar los contenedores recibidos, rangos de bultos y posición final">Contenedores y bultos</button><button class="b-sec" data-revisar-packing title="Comparar los embarques guardados con las filas originales sin duplicar la recepción">Revisar embarques del Excel</button>':''}${supervisor?'<button class="b-sec" data-catalogo title="Consultar Depot y actualizar el catálogo de productos">↻ Catálogo</button><button class="b-sec" data-pendientes title="Recepciones cerradas con correo pendiente">▣ Entregas <span data-cantidad-pendientes></span></button>':''}</div></details><div class="barra-reloj"><a class="perfil-acceso" href="./cuenta.html" data-avatar title="Mi foto y mi cuenta"></a><time data-reloj title="Hora de Ecuador · reloj del equipo"></time><button class="b-sec" data-tema></button></div></div><div class="avance-encabezado" data-avance hidden><div><strong data-avance-codigo></strong><span data-avance-cifras></span></div><span class="avance-pastel" role="img" aria-label="Avance de referencias verificadas"><b data-avance-porcentaje></b></span></div>`;
 cabecera.after(nav);
 nav.querySelector('[data-revisar-packing]')?.addEventListener('click',async()=>{try{const {revisarPackingGuardado}=await import('./revision-packing.js?v=20261020-60');await revisarPackingGuardado(codigo);}catch(e){aviso(e.message,'err');}});
 nav.querySelector('[data-contenedores]')?.addEventListener('click',async()=>{try{const {editarContenedores}=await import('./contenedores.js?v=20261020-60');await editarContenedores(codigo);}catch(e){aviso(e.message,'err');}});
 nav.querySelector('[data-catalogo]')?.addEventListener('click',()=>abrirCatalogo());
 nav.querySelector('[data-etiqueta]')?.addEventListener('click',()=>etiquetaCatalogo());
 const aviso=(t,tipo,titulo)=>mostrarAviso(document.querySelector('#avisos,#avisos-sesion')||nav,t,tipo,titulo);
 nav.querySelector('[data-pendientes]')?.addEventListener('click',()=>abrirEntregas(aviso,'',{pendientes:true}).catch(e=>aviso(e.message,'err')));
 const pintarAvatar=url=>{const a=nav.querySelector('[data-avatar]');a.replaceChildren();if(url&&/^\/api\/auth\/operadores\/\d+\/foto\?v=[a-f0-9]+$/.test(url)){const img=document.createElement('img');img.src=url;img.alt='Mi foto de perfil';a.append(img);}else a.textContent=(perfil.nombre||usuario.displayName||'U').trim().slice(0,1).toUpperCase();};pintarAvatar(perfil.photoURL||usuario.photoURL);
 const fotoNueva=e=>pintarAvatar(e.detail);document.addEventListener('itsanet:perfil-foto',fotoNueva);
 const pintarPendientes=filas=>{const n=new Set(filas.filter(e=>e.esUltima&&e.recepcionEstado==='CERRADA'&&(['PENDIENTE','REVISION','PROCESANDO'].includes(e.estado)||e.correoManual?.estado==='PREPARADO')).map(e=>e.recepcion)).size;const el=nav.querySelector('[data-cantidad-pendientes]');if(el)el.textContent=n?String(n):'';};
 const alCambiar=e=>pintarPendientes(e.detail);document.addEventListener('itsanet:entregas',alCambiar);
 const pendientes=async()=>{if(!supervisor||document.hidden)return;try{const filas=await pedir('/entregas');if(nav.isConnected)pintarPendientes(filas);}catch{}};pendientes();const timerPendientes=setInterval(pendientes,60000);
 const tema=nav.querySelector('[data-tema]');
 const pintarTema=()=>{const noche=document.documentElement.dataset.theme==='dark';tema.textContent=noche?'☀':'☾';tema.title=noche?'Cambiar a modo día':'Cambiar a modo noche';tema.setAttribute('aria-label',tema.title);tema.setAttribute('aria-pressed',String(noche));};
 tema.onclick=()=>{const valor=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=valor;try{localStorage.setItem('itsanet.tema',valor);}catch{}pintarTema();};pintarTema();
 const reloj=()=>{const ahora=new Date(),t=nav.querySelector('[data-reloj]');t.dateTime=ahora.toISOString();t.textContent=ahora.toLocaleString('es-EC',{timeZone:'America/Guayaquil',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});};reloj();const temporizador=setInterval(reloj,1000);
 const avance=()=>{const a=avanceActual,visible=!!codigo&&a?.codigo?.toUpperCase()===codigo.toUpperCase();nav.querySelector('[data-avance]').hidden=!visible;if(!visible)return;
  nav.querySelector('[data-avance-codigo]').textContent=a.codigo+(a.estado==='CERRADA'?' · Cerrada':'');nav.querySelector('[data-avance-cifras]').textContent=`${a.verificadas}/${a.total} referencias verificadas · ${a.unidades} unidades`+(a.conectado===false?' · Sin conexión: último dato confirmado':'');nav.querySelector('.avance-pastel').style.setProperty('--avance',Math.max(0,Math.min(100,a.avance))+'%');nav.querySelector('.avance-pastel').setAttribute('aria-label',a.avance+'% de referencias verificadas');nav.querySelector('[data-avance-porcentaje]').textContent=a.avance+'%';};
 document.addEventListener('itsanet:avance',avance);avance();
 const cerrarMenu=ev=>{for(const menu of nav.querySelectorAll('details'))if(!menu.contains(ev.target))menu.open=false;};document.addEventListener('click',cerrarMenu);
 nav.addEventListener('keydown',ev=>{if(ev.key==='Escape')nav.querySelectorAll('details').forEach(m=>m.open=false);});
 const medir=()=>document.documentElement.style.setProperty('--alto-barra',nav.offsetHeight+'px');const observador=new ResizeObserver(medir);observador.observe(nav);medir();
 liberarBarra=()=>{clearInterval(temporizador);clearInterval(timerPendientes);document.removeEventListener('itsanet:entregas',alCambiar);document.removeEventListener('itsanet:perfil-foto',fotoNueva);observador.disconnect();document.removeEventListener('itsanet:avance',avance);document.removeEventListener('click',cerrarMenu);document.documentElement.style.removeProperty('--alto-barra');};
}
function dialogo(titulo){const d=document.createElement('dialog');d.className='modal-operativa';d.innerHTML=`<header class="acciones"><h2>${titulo}</h2><button class="b-sec" data-cerrar>Cerrar</button></header><div data-cuerpo></div><p role="status" data-estado></p>`;document.body.append(d);d.showModal();d.querySelector('[data-cerrar]').onclick=()=>d.close();d.addEventListener('close',()=>d.remove());return d;}
async function abrirCatalogo(){
 const d=dialogo('Catálogo de Depot'),c=d.querySelector('[data-cuerpo]'),estado=d.querySelector('[data-estado]');
 c.innerHTML='<p>El catálogo es compartido por todos los supervisores. Una actualización reciente se reutiliza y otra en curso no se repite. La programación automática es opcional en Administración.</p><p>Actualiza los productos desde las conexiones Depot guardadas por ADMIN. Puedes continuar contando con el catálogo actual mientras se consulta.</p><button class="b-primario" data-actualizar>Actualizar catálogo ahora</button>';
 try{const r=await pedir('/estado',{base:'/api/catalogo'});estado.textContent=`${r.productos_en_cache??r.productos??0} productos · última actualización: ${r.actualizado_en?new Date(r.actualizado_en).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}):'sin confirmar'}`;}catch(e){estado.textContent=e.message;}
 c.querySelector('button').onclick=async ev=>{const b=ev.currentTarget;b.disabled=true;d.querySelector('[data-cerrar]').disabled=true;estado.textContent='Consultando Depot y actualizando productos…';try{const r=await pedir('/depot/sincronizar',{base:'/api/catalogo',cuerpo:{}});estado.textContent=`${r.reutilizado?'Se reutilizó el catálogo reciente':'Catálogo actualizado'}: ${r.productos} productos.${r.errores?.length?' Conexiones pendientes: '+r.errores.join(', '):''}`;}catch(e){estado.textContent=e.message;}finally{b.disabled=false;d.querySelector('[data-cerrar]').disabled=false;}};
}
let recursos=null;
function cargarRecursosEtiqueta(){
 if(recursos)return recursos;
 recursos=Promise.all([
  globalThis.JsBarcode?Promise.resolve():new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=new URL('../vendor/JsBarcode.all.min.js?v=20261018-41',import.meta.url).href;script.onload=resolve;script.onerror=()=>{script.remove();reject(new Error('No se pudo cargar el código de barras. Recarga y vuelve a intentar.'));};document.head.append(script);}),
  document.querySelector('link[href*="css/operacion.css"]')?Promise.resolve():new Promise((resolve,reject)=>{const link=document.createElement('link');link.rel='stylesheet';link.href=new URL('../css/operacion.css',import.meta.url).href;link.onload=resolve;link.onerror=()=>{link.remove();reject(new Error('No se pudo cargar el formato de etiquetas.'));};document.head.append(link);})
 ]).catch(e=>{recursos=null;throw e;});return recursos;
}
async function etiquetaCatalogo(){
 const d=dialogo('Imprimir etiqueta desde el catálogo'),c=d.querySelector('[data-cuerpo]'),estado=d.querySelector('[data-estado]');
 c.innerHTML='<form><label class="campo"><span>Código SKU o código de barras</span><input data-codigo required minlength="3" placeholder="Escanea o escribe el código"></label><button class="b-primario">Buscar en catálogo</button></form><div data-resultados></div>';
 c.querySelector('form').onsubmit=async ev=>{ev.preventDefault();estado.textContent='Buscando en el catálogo actualizado…';c.querySelector('[data-resultados]').replaceChildren();try{const filas=await pedir('/buscar?q='+encodeURIComponent(c.querySelector('input').value.trim())+'&limite=30',{base:'/api/catalogo'});const disponibles=filas.filter(f=>!f.inactivo&&f.existeDepot);estado.textContent=disponibles.length?`${disponibles.length} productos disponibles. Selecciona el código y cliente correctos.`:'No se encontró un producto activo en Depot. Actualiza el catálogo o verifica el código.';for(const f of disponibles){const b=document.createElement('button');b.className='b-sec resultado-catalogo';b.innerHTML=`<b>${esc(f.sku)} · ${esc(f.cliente)}</b><br>${esc(f.descripcion)}`;b.onclick=async()=>{try{await cargarRecursosEtiqueta();abrirEtiqueta({...f,cantidad:1});}catch(e){estado.textContent=e.message;}};c.querySelector('[data-resultados]').append(b);}}catch(e){estado.textContent=e.message;}};
}
