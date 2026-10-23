import {pedir,modoLocal} from './local.js?v=20261023-65';
import {escucharCambiosRecepcion} from './cambios-recepcion.js?v=20261023-65';
const texto=v=>String(v??'');
const fecha=v=>v?new Date(v).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}):'sin confirmar';
export function iniciarAvisosOperativos({usuario,perfil,nav,abrirCatalogo}){
 if(!modoLocal()||!usuario||!perfil)return ()=>{};
 const supervisor=['SUPERVISOR','ADMIN'].includes(perfil.rol),recepcion=new URL(location.href).searchParams.get('r')||'';
 const boton=document.createElement('button');boton.type='button';boton.className='b-sec boton-avisos';boton.textContent='Avisos';boton.setAttribute('aria-label','Abrir avisos operativos');
 nav.querySelector('.barra-fila').insertBefore(boton,nav.querySelector('.barra-reloj'));
 const resumen=document.createElement('p');resumen.className='resumen-avisos';resumen.hidden=true;resumen.setAttribute('role','status');nav.append(resumen);
 const catalogo=document.createElement('section');catalogo.className='catalogo-jornada';catalogo.hidden=true;catalogo.setAttribute('role','status');nav.append(catalogo);
 let vivo=true,ocupado=false,pendiente=false,forzarCatalogo=true,ultimoCatalogo=0,datos=null,cargaCatalogo=null,dialogo=null,error='',programado=null,equipo=[],filtrados=null,tipoListado='';
 const coincidencias=()=>{const grupos=new Map();for(const p of equipo){const k=JSON.stringify([p.recepcion,p.sku]);if(!grupos.has(k))grupos.set(k,[]);grupos.get(k).push(p);}return [...grupos.values()].filter(g=>g.length>1);};
 function pintar(){
  const avisos=datos?.avisos||[],nuevos=avisos.filter(a=>!a.leido).length,simultaneos=coincidencias().length,total=nuevos+simultaneos;
  boton.textContent='Avisos'+(total?' ('+total+')':'');boton.classList.toggle('avisos-nuevos',total>0);boton.setAttribute('aria-label',`Abrir avisos operativos: ${nuevos} sin revisar y ${simultaneos} coincidencias de SKU`);
  resumen.hidden=!total;resumen.textContent=total?`${nuevos} aviso(s) por revisar${simultaneos?' · '+simultaneos+' SKU con trabajo simultáneo':''}. Abre Avisos.`:'';
  catalogo.replaceChildren();catalogo.hidden=!supervisor||!cargaCatalogo?.requiereActualizacion;
  if(!catalogo.hidden){const p=document.createElement('p');p.textContent=cargaCatalogo.actualizando?'El catálogo se está actualizando. Puedes continuar con el catálogo disponible.':'Inicio de jornada: actualiza el catálogo de Depot. '+(cargaCatalogo.clientesPendientes.length?'Pendientes: '+cargaCatalogo.clientesPendientes.join(', ')+'.':'No hay una carga completa confirmada para hoy.');const b=document.createElement('button');b.type='button';b.className='b-sec';b.textContent='Revisar catálogo';b.onclick=()=>abrirCatalogo();catalogo.append(p,b);}
  if(dialogo?.open)pintarDialogo();
 }
 function pintarDialogo(){
  const listado=dialogo.querySelector('[data-listado]'),filtro=dialogo.querySelector('[data-filtro]').value;
  const equipoVista=dialogo.querySelector('[data-equipo]');equipoVista.replaceChildren();
  for(const grupo of coincidencias()){const p=document.createElement('p');p.className='sku-coordinacion';p.textContent='Trabajo simultáneo · '+grupo[0].recepcion+' · '+grupo[0].sku+': '+grupo.map(o=>o.nombre+' ('+(o.actividad==='CONTANDO'?'contando':'revisando')+')').join(' · ')+'. Coordinen las unidades y pallets antes de confirmar diferencias.';equipoVista.append(p);}
  dialogo.querySelector('[data-estado]').textContent=error||('Actualizado: '+fecha(datos?.consultadoEn)+(datos?.hayMas?' · Mostrando las novedades más recientes. Consulta cada recepción para revisar el detalle completo.':''));
  dialogo.querySelector('[data-estado]').classList.toggle('err',!!error);listado.replaceChildren();
  const fuente=filtro&&tipoListado===filtro?filtrados:datos;
  const avisos=(fuente?.avisos||[]).filter(a=>!filtro||filtro==='SIN_FOTO'&&a.evidencias.sinEvidencia||a.tipo===filtro);
  dialogo.querySelector('[data-leidos]').disabled=!avisos.some(a=>!a.leido)||!!error;
  for(const a of avisos){
   const card=document.createElement('article');card.className='aviso-operativo'+(a.leido?' aviso-revisado':'');
   const titulo=document.createElement('h3');titulo.textContent=a.tipo+(a.provisional?' provisional':'')+' · '+a.sku;
   const alcance=document.createElement('p');alcance.textContent=a.recepcion+' · '+a.cliente+(a.descripcion?' · '+a.descripcion:'');
   const cantidad=document.createElement('p');cantidad.textContent=(a.cantidad===null?'Unidades por revisar':texto(a.cantidad)+' unidad(es)')+' · Declarado: '+a.esperado+' · Contado: '+a.contado;
   const explicacion=document.createElement('p');explicacion.textContent=a.mensaje;explicacion.className='mini';
   const e=a.evidencias,evidencias=document.createElement('p');evidencias.className=e.sinEvidencia?'evidencia-pendiente':'evidencia-registrada';
   evidencias.textContent=e.sinEvidencia?'Sin imágenes registradas para esta novedad.':`${e.registradas} imagen(es) registrada(s) · ${e.confirmadasDrive} confirmada(s) en Drive · ${e.pendientesDrive} pendiente(s).`;
   const acciones=document.createElement('div');acciones.className='acciones';const enlace=document.createElement('a');enlace.href='./validar.html?r='+encodeURIComponent(a.recepcion);enlace.textContent='Abrir recepción';enlace.className='b-sec';acciones.append(enlace);
   const leido=document.createElement('button');leido.type='button';leido.className='b-sec';leido.textContent=a.leido?'Revisado':'Marcar como revisado';leido.disabled=a.leido||!!error;leido.onclick=()=>marcar([a]);acciones.append(leido);
   card.append(titulo,alcance,cantidad,explicacion,evidencias,acciones);listado.append(card);
  }
  if(!avisos.length){const p=document.createElement('p');p.textContent=!supervisor&&!recepcion?'Abre una recepción para consultar sus avisos.':filtro&&tipoListado!==filtro?'Consultando el filtro en todas las recepciones del alcance…':fuente?.hayMas?'No hay coincidencias en los avisos cargados. Consulta las recepciones para ampliar la revisión.':'No hay novedades que coincidan con este filtro.';listado.append(p);}
 }
 async function marcar(avisos){try{await pedir('/notificaciones/leidas',{base:'/api/operacion',cuerpo:{avisos:avisos.map(({id,revision})=>({id,revision}))}});const marcados=new Map(avisos.map(a=>[a.id,a.revision]));for(const a of [...(datos?.avisos||[]),...(filtrados?.avisos||[])])if(marcados.get(a.id)===a.revision)a.leido=true;pintar();}catch(e){error=e.message;pintar();}}
 async function actualizar(){
  if(!vivo||document.hidden)return;if(ocupado){pendiente=true;return;}ocupado=true;
  const conCatalogo=supervisor&&(forzarCatalogo||Date.now()-ultimoCatalogo>60000);forzarCatalogo=false;
  try{const q=new URLSearchParams({catalogo:String(conCatalogo)});if(!supervisor&&recepcion)q.set('recepcion',recepcion);const r=await pedir('/notificaciones?'+q,{base:'/api/operacion'});if(!vivo)return;datos=r;if(r.catalogo){cargaCatalogo=r.catalogo;ultimoCatalogo=Date.now();}const filtro=dialogo?.querySelector('[data-filtro]').value||'';if(filtro){q.set('catalogo','false');q.set('tipo',filtro);const f=await pedir('/notificaciones?'+q,{base:'/api/operacion'});if(!vivo)return;filtrados=f;tipoListado=filtro;}error='';boton.removeAttribute('title');pintar();}
  catch(e){error='No se pudieron actualizar los avisos. Se conserva la última consulta. '+e.message;boton.title=error;if(dialogo?.open)pintarDialogo();}
  finally{ocupado=false;if(pendiente&&vivo){pendiente=false;programado=setTimeout(actualizar,300);}}
 }
 function programar(e){if(supervisor&&perfil.permisos?.verEquipo&&Array.isArray(e?.detail?.equipoSku)){equipo=e.detail.equipoSku;pintar();}if(e?.type==='itsanet:catalogo-actualizado'||e?.detail?.secciones?.includes('catalogo')){forzarCatalogo=true;ultimoCatalogo=0;}clearTimeout(programado);programado=setTimeout(actualizar,300);}
 function abrir(){
  if(dialogo?.open){dialogo.focus();return;}
  dialogo=document.createElement('dialog');dialogo.className='modal-operativa avisos-operativos';dialogo.innerHTML='<header class="acciones"><h2>Avisos de la operación</h2><button type="button" class="b-sec" data-cerrar>Cerrar</button></header><p class="mini">Las diferencias de una recepción abierta son provisionales. Revisa el conteo antes de confirmar faltantes o sobrantes. Marcar un aviso como revisado no modifica cantidades ni elimina la novedad.</p><div data-equipo role="status"></div><div class="acciones"><label class="campo"><span>Mostrar</span><select data-filtro><option value="">Todas las novedades</option><option value="PNC">Producto no conforme · PNC</option><option value="FALTANTE">Faltantes</option><option value="SOBRANTE">Sobrantes</option><option value="ADICIONAL">Adicionales fuera del packing list</option><option value="SIN_FOTO">Sin imágenes de la novedad</option></select></label><button type="button" class="b-sec" data-actualizar>Actualizar</button><button type="button" class="b-sec" data-leidos>Marcar esta vista como revisada</button></div><p role="status" data-estado></p><div data-listado></div>';
  document.body.append(dialogo);dialogo.showModal();dialogo.querySelector('[data-cerrar]').onclick=()=>dialogo.close();dialogo.querySelector('[data-filtro]').onchange=()=>{pintarDialogo();actualizar();};
  dialogo.querySelector('[data-actualizar]').onclick=()=>{forzarCatalogo=true;actualizar();};dialogo.querySelector('[data-leidos]').onclick=()=>{const f=dialogo.querySelector('[data-filtro]').value,fuente=f&&tipoListado===f?filtrados:datos;marcar((fuente?.avisos||[]).filter(a=>!a.leido&&(!f||f==='SIN_FOTO'&&a.evidencias.sinEvidencia||a.tipo===f)));};
  dialogo.addEventListener('close',()=>{dialogo.remove();dialogo=null;},{once:true});pintarDialogo();actualizar();
 }
 boton.onclick=abrir;const timer=setInterval(actualizar,15000),detenerCambios=supervisor||recepcion?escucharCambiosRecepcion(supervisor?'':recepcion,()=>{}):()=>{};
 document.addEventListener('itsanet:operacion-actualizada',programar);document.addEventListener('itsanet:catalogo-actualizado',programar);document.addEventListener('visibilitychange',programar);actualizar();
 return ()=>{vivo=false;detenerCambios();clearInterval(timer);clearTimeout(programado);document.removeEventListener('itsanet:operacion-actualizada',programar);document.removeEventListener('itsanet:catalogo-actualizado',programar);document.removeEventListener('visibilitychange',programar);if(dialogo?.open)dialogo.close();boton.remove();resumen.remove();catalogo.remove();};
}
