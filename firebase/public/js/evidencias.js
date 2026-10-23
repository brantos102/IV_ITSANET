import {TIPOS_FOTOGRAFIA} from './tipos-foto.js?v=20261023-66';
import {cargarMiniatura,limpiarMiniaturas} from './miniaturas.js?v=20261023-66';
import {elegirDestinoFoto} from './destino-foto.js?v=20261023-66';
import {tomarFotoEnPagina} from './captura-foto.js?v=20261023-66';
import {elegirEmbarqueFotos,contextoFotos} from './fotos-embarques.js?v=20261023-66';
import {organizarFotos} from './organizar-fotos.js?v=20261023-66';
import {verImagen} from './visor-imagen.js?v=20261023-66';
import {manualFotos} from './manual-fotos.js?v=20261023-66';
import {pedir} from './local.js?v=20261023-66';
import {comprimir} from './imagen.js?v=20261023-66';
import {confirmar,pedirDatos,tecladoDialogo} from './modal.js?v=20261023-66';
import {actorFotos,subirFotoProtegida,abrirFotosPendientes} from './fotos-pendientes.js?v=20261023-66';

export const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const operacion = (ruta, opciones={}) => pedir(ruta,{...opciones,base:'/api/operacion'});
export const TIPOS_EVIDENCIA=TIPOS_FOTOGRAFIA;

/** Lote secuencial sin máximo de imágenes. Cada archivo conserva su resultado al reintentar. */
export async function cargarEvidencias(recepcion, archivos, datos, alAvanzar=()=>{}, cache=new Map(),destinos=null) {
  if(!archivos.length)return [];
  if(destinos?.size){const urls=[];for(let i=0;i<archivos.length;i++){const f=archivos[i];urls.push(...await cargarEvidencias(recepcion,[f],{...datos,...(destinos.get(f)||{}),desdeSku:destinos.has(f)?false:datos.desdeSku},()=>{},cache));alAvanzar(i+1,archivos.length);}return urls;}
  const urls=[],actor=await actorFotos(),entrada=JSON.stringify([actor,recepcion,datos]);
  if(cache.contextoFotos?.entrada===entrada)datos=cache.contextoFotos.datos;
  else{datos=await elegirEmbarqueFotos(recepcion,datos);cache.contextoFotos={entrada,datos};}
  const firma=JSON.stringify([actor,recepcion,datos]);
  for(let i=0;i<archivos.length;i++) {
    const f=archivos[i];
    const clave=f; // Identidad File: nombre repetido no significa contenido repetido.
    if(cache.get(clave)?.firma!==firma) {
      alAvanzar(i,archivos.length);
      const texto=['PACKING_INICIAL','ETIQUETA_CAJA','ABIERTO_CON_PACKING'].includes(datos.tipoEvidencia);
      const img=await comprimir(f,texto?{lado:2400,calidad:.85}:['PANORAMICA','PRERECEPCION'].includes(datos.tipoEvidencia)?{lado:2048,calidad:.82}:{});
      let r;
      try{r=await subirFotoProtegida(recepcion,f,img,datos,actor);}
      catch(e){if(e.estado===422)delete cache.contextoFotos;throw e;}
      cache.set(clave,{url:r.url,firma});
    }
    urls.push(cache.get(clave).url);
    alAvanzar(i+1,archivos.length);
  }
  return urls;
}

export async function abrirEvidencias({recepcion,sku='',categoria='GENERAL',tipo='',supervisor=false,origen='',pallet=''}) {
  const [ingreso,rec,contexto]=await Promise.all([operacion(`/recepciones/${encodeURIComponent(recepcion)}/ingreso`),pedir(`/recepciones/${encodeURIComponent(recepcion)}`),contextoFotos(recepcion,{sku,origen})]);
  const final=tipo==='ESTADO_FINAL',panoramica=['PANORAMICA','PRERECEPCION'].includes(tipo)&&!sku&&categoria==='RECEPCION';
  if(sku&&categoria==='GENERAL')categoria='VALIDACION';
  if(final){sku='';categoria='RECEPCION';}
  const destinos=new Map();
  let producto=null;
  if(sku){producto=await pedir(`/recepciones/${encodeURIComponent(recepcion)}/estado-sku/${encodeURIComponent(sku)}`);
    if(!producto)throw Error('No se encontró este SKU en la recepción. Actualiza antes de cargar sus fotos.');
    categoria=producto.tienePnc?'PNC':producto.estado==='SOBRANTE'||producto.enPackingList===false?'SOBRANTE':['FALTANTE','NO_ENCONTRADO'].includes(producto.estado)?'FALTANTE':'VALIDACION';
    tipo=categoria==='VALIDACION'?'ADICIONAL':'ITEM_NOVEDAD';
  }
  const d=document.createElement('dialog');d.className='dialogo-operativo evidencias-dialogo';
  d.innerHTML=`<div class="acciones"><h2 style="flex:1">${final?'Estado final de la mercadería':panoramica?(tipo==='PRERECEPCION'?'Prerecepción · descarga del contenedor':'Panorámicas de la recepción'):sku ? 'Evidencias · '+esc(sku) : 'Evidencias de recepción'}</h2><button data-cerrar class="b-sec">Cerrar</button></div>
    <label class="campo"><span>Pallet de la fotografía · opcional</span><input data-pallet-evidencia maxlength="40" placeholder="Ej.: B04"></label><label class="campo"><span>Embarque de estas fotos</span><select data-embarque-fotos>${contexto.candidatos.length>1?'<option value="__ELEGIR__">Selecciona el embarque o fotos compartidas</option>':''}${contexto.candidatos.map(e=>`<option value="${esc(e)}">${esc(e)}</option>`).join('')}<option value="">${contexto.embarques.length?'Compartidas entre embarques · carpeta COMPARTIDAS':'Recepción sin embarque informado'}</option></select></label><p class="foto-ruta" data-ruta-destino role="status"></p><label class="campo"><span>Foto de</span><select data-tipo>${Object.entries(TIPOS_EVIDENCIA).map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join('')}</select></label>
    <details><summary>Clasificación y vínculos · ${esc(categoria)}</summary><div class="rejilla"><label class="campo"><span>Protocolo</span><select data-protocolo><option value="REGLAMENTARIO">Reglamentario</option><option value="GENERAL">General</option></select></label>
    <label class="campo"><span>Clasificación</span><select data-categoria>${['RECEPCION','VALIDACION','FALTANTE','SOBRANTE','PNC','GENERAL'].map(c=>`<option>${c}</option>`).join('')}</select></label>
    <label class="campo"><span>Bulto / caja madre</span><select data-unidad><option value="">Sin unidad específica</option>${ingreso.unidades.map(u=>`<option value="${u.id}">${esc(u.tipo)} ${u.numero} · ${esc(u.codigo || 'sin código')}</option>`).join('')}</select></label>
    <label class="campo"><span>Packing list vinculado</span><input data-origen placeholder="PRINCIPAL o nombre de la lista"></label></div>
    <p class="mini" data-recomendacion></p></details><div class="acciones"><button data-camara class="b-primario">📷 Cámara del equipo</button><a class="b-sec" data-camara-windows href="microsoft.windows.camera:" hidden>Cámara de Windows</a><button data-galeria class="b-sec">Elegir de la galería</button><button data-subir class="b-sec">Guardar fotos seleccionadas</button></div>
    <input data-captura type="file" accept="image/*" capture="environment" hidden><input data-archivos type="file" accept="image/*" multiple hidden>
    <div data-seleccion></div><p data-estado role="status"></p>
    <section class="fotos-progreso" data-progreso-fotos><h3>Estado de las fotografías</h3><p data-estado-drive role="status" aria-live="polite">Consultando copias…</p><progress data-progreso-drive value="0" max="1" aria-label="Fotografías confirmadas en Drive"></progress><p data-alerta-drive role="alert"></p><div data-pendientes-drive></div><p class="mini" data-reloj-drive>Actualización automática cada 3 segundos.</p></section><div class="acciones"><button class="b-sec" data-temporales>Recuperar fotos de este equipo</button><button class="b-sec" data-actualizar>Actualizar ahora</button><button class="b-sec" data-reintentar ${supervisor?'':'hidden'}>Reintentar copias pendientes</button></div>
    <div data-carpetas></div><div class="rejilla"><label class="campo"><span>Filtrar fotografías por clasificación</span><select data-filtro-categoria><option value="">Todas</option>${['RECEPCION','VALIDACION','FALTANTE','SOBRANTE','PNC','GENERAL'].map(c=>`<option>${c}</option>`).join('')}</select></label><label class="campo"><span>SKU de las fotografías</span><input data-filtro-sku value="${esc(sku)}" placeholder="Todos los códigos"></label><button data-filtrar class="b-sec">Aplicar filtro</button></div><p data-resumen-galeria class="mini" role="status"></p><div data-imagenes class="galeria-imagenes"></div><button data-mas class="b-sec">Ver más</button>`;
  document.body.append(d); d.showModal();d.querySelector('h2').parentElement.after(manualFotos(ingreso));
  const $=s=>d.querySelector(s);$('[data-pallet-evidencia]').value=pallet;let elegidas=[],cache=new Map(),offset=0,ocupado=false,consultando=false,consultandoDrive=false,revisionDrive='',filtroPendiente=false,resumenSku=null;
  $('[data-pallet-evidencia]').closest('label').hidden=final||panoramica;
  d.firstElementChild.classList.add('modal-cabecera');
  const captura=document.createElement('section');captura.className='fotos-captura';captura.tabIndex=0;captura.setAttribute('aria-label','Arrastra fotografías aquí');captura.innerHTML='<h3>1. Agregar fotografías</h3><p class="mini">Elige el embarque y el tipo. Selecciona tus fotos, revisa sus miniaturas y pulsa Guardar. La copia a Drive se confirma arriba.</p>';
  $('[data-tipo]').closest('label').before(captura);
  for(const el of [...d.children]){if(el===captura)continue;if(el.matches('[data-ruta-destino]')||el.contains($('[data-embarque-fotos]'))||el.contains($('[data-pallet-evidencia]'))||el.contains($('[data-tipo]'))||el.tagName==='DETAILS'&&!el.classList.contains('manual-fotos')||el.contains($('[data-camara]'))||el.matches('[data-captura],[data-archivos],[data-seleccion],[data-estado]'))captura.append(el);}
  const guardadas=document.createElement('h3');guardadas.textContent='2. Fotografías registradas';$('[data-progreso-fotos]').after(guardadas);
  d.querySelector('.modal-cabecera').after($('[data-progreso-fotos]'));
  const herramientas=document.createElement('details');herramientas.className='fotos-herramientas';herramientas.innerHTML='<summary>Recuperación y organización</summary>';$('[data-temporales]').parentElement.before(herramientas);herramientas.append($('[data-temporales]').parentElement);
  let vistas=[];const liberarVistas=()=>{vistas.forEach(u=>URL.revokeObjectURL(u));vistas=[];};
  tecladoDialogo(d,{accion:null,campos:'[data-origen]'});
  const esWindows=/Win/i.test(navigator.userAgentData?.platform || navigator.platform || '');
  $('[data-camara]').hidden=esWindows;$('[data-camara-windows]').hidden=!esWindows;
  $('[data-camara-windows]').onclick=ev=>{if(ocupado){ev.preventDefault();return;}$('[data-estado]').textContent='Toma la foto en Cámara de Windows. Regresa y toca Galería para adjuntarla a esta evidencia.';};
  if(supervisor){const organizar=document.createElement('button');organizar.className='b-sec';organizar.textContent='Actualizar carpetas por embarque';organizar.onclick=()=>{if(!ocupado)organizarFotos(recepcion,()=>cargar()).catch(e=>$('[data-estado]').textContent=e.message);};$('[data-temporales]').parentElement.append(organizar);const a=document.createElement('a');a.href=`/api/operacion/recepciones/${encodeURIComponent(recepcion)}/evidencias.xlsx`;a.className='b-sec';a.textContent='▦';a.title='Descargar Excel de trazabilidad de fotos: SKU, tipo, autor y carpeta Drive';a.setAttribute('aria-label',a.title);a.style.cssText='flex:0 0 42px;min-width:42px;width:42px;display:grid;place-items:center';d.querySelector('.acciones').append(a);}
  $('[data-embarque-fotos]').value=contexto.sugerido||(contexto.candidatos.length>1?'__ELEGIR__':'');
  $('[data-categoria]').value=categoria;
  $('[data-origen]').value=(rec.origenes||[]).includes(origen)?origen:'';
  $('[data-tipo]').value=tipo || (sku ? 'ITEM_NOVEDAD' : 'EXTERIOR_BULTO');
  if(sku){
    $('[data-tipo]').closest('label').hidden=true;$('[data-categoria]').closest('details').hidden=true;
    const destino=document.createElement('p');destino.className='mini';destino.textContent=`${producto.descripcion||''} · Fotos en ${categoria==='VALIDACION'?sku:categoria+'/'+sku}. Las fotos nuevas toman el estado actual; las anteriores conservan su clasificación histórica.`;
    d.querySelector('h2').parentElement.after(destino);$('[data-recomendacion]').hidden=true;
    $('[data-protocolo]').value='GENERAL';
    const todas=document.createElement('button');todas.className='b-sec';todas.textContent='Ver fotos de la recepción completa';todas.onclick=()=>{d.close();abrirEvidencias({recepcion,supervisor}).catch(e=>console.error(e.message));};$('[data-estado-drive]').after(todas);
  }
  if(sku||final){
    const filtros=$('[data-filtro-sku]').closest('.rejilla'),detalles=document.createElement('details');
    detalles.innerHTML='<summary>Filtrar fotos</summary>';filtros.before(detalles);detalles.append(filtros);
    $('[data-filtro-sku]').closest('label').hidden=true;
  }
  $('[data-subir]').disabled=true;
  if(rec.estado==='CERRADA'&&!final){for(const selector of ['[data-camara]','[data-camara-windows]','[data-galeria]','[data-subir]'])$(selector).hidden=true;$('[data-tipo]').disabled=true;}
  if(final){$('[data-tipo]').disabled=true;$('[data-categoria]').disabled=true;$('[data-estado]').textContent=rec.estado==='CERRADA'?'Evidencia posterior al cierre: conserva autor y fecha; los informes emitidos permanecen iguales.':'Fotografía cómo queda la mercadería al terminar. Las imágenes se vinculan a esta recepción.';}
  if(panoramica){$('[data-tipo]').disabled=true;$('[data-categoria]').disabled=true;$('[data-unidad]').value='';$('[data-unidad]').disabled=true;$('[data-estado]').textContent='Estas fotos documentan la recepción completa y se guardan como '+tipo+', sin vincularlas al primer bulto.';}
  // Recibir sin fotos no impide adjuntar posteriormente evidencia de una novedad.
  $('[data-protocolo]').value=ingreso.protocolo==='SIN_FOTOS' ? 'GENERAL' : ingreso.protocolo || 'REGLAMENTARIO';
  const mostrarDestino=()=>{const t=$('[data-tipo]').value,c=$('[data-categoria]').value,emb=$('[data-embarque-fotos]').value;const carpeta=sku?({'SOBRANTE':'SOBRANTES','FALTANTE':'FALTANTES','PNC':'PNC'}[c]||'PRODUCTOS'):({'PRERECEPCION':'PRE-INGRESO','ESTADO_FINAL':'FOTOS-FINALES','PANORAMICA':'PANORAMICAS'}[t]||($('[data-unidad]').value?'BULTOS':'OTRAS-EVIDENCIAS'));$('[data-ruta-destino]').textContent='Destino del lote: '+recepcion+(contexto.embarques.length?' / '+(emb==='__ELEGIR__'?'Selecciona un embarque':emb||'COMPARTIDAS'):'')+' / '+carpeta+(sku?' / '+sku:'')+'. Puedes cambiar el destino de cada foto debajo.';};
  mostrarDestino();for(const selector of ['[data-embarque-fotos]','[data-tipo]','[data-categoria]','[data-unidad]'])$(selector).addEventListener('change',mostrarDestino);
  const recomendar=()=>{$('[data-recomendacion]').textContent=$('[data-protocolo]').value==='GENERAL'
    ? 'Registro libre: fotos panorámicas o del detalle que necesites.'
    : sku ? 'Recomendado: caja cerrada, etiqueta de caja madre, caja abierta y detalle de la novedad.'
    : `Recomendado por bulto: ${ingreso.recomendaciones.exterioresMin} exteriores (objetivo ${ingreso.recomendaciones.exterioresObjetivo}) y ${ingreso.recomendaciones.abiertosMin} abierto con lista visible. Packing inicial: ${ingreso.recomendaciones.packingMin}.`;};
  recomendar();$('[data-protocolo]').onchange=recomendar;
  for(const selector of ['[data-embarque-fotos]','[data-protocolo]','[data-categoria]','[data-tipo]','[data-unidad]','[data-origen]']) {
    $(selector).addEventListener('change',()=>{cache=new Map();});
  }
  const pintar=()=>{$('[data-subir]').disabled=ocupado||!elegidas.length;liberarVistas();$('[data-seleccion]').replaceChildren();elegidas.forEach((f,i)=>{
    const card=document.createElement('figure'),img=document.createElement('img'),b=document.createElement('button');img.src=URL.createObjectURL(f);vistas.push(img.src);img.alt=f.name;
    b.className='b-sec';b.textContent=`Quitar foto ${i+1}`;b.title=f.name;b.disabled=ocupado;
    const nombre=document.createElement('figcaption');nombre.textContent=f.name;const destino=document.createElement('button');destino.type='button';destino.className='b-sec';destino.disabled=ocupado;const destinoActual=destinos.get(f);destino.textContent=destinoActual?'Destino: '+(destinoActual.embarqueFoto||'Compartidas')+' / '+(TIPOS_EVIDENCIA[destinoActual.tipoEvidencia]||destinoActual.categoria)+(destinoActual.sku?' / '+destinoActual.sku:''):'Revisar imagen y elegir carpeta';destino.onclick=async()=>{const valor=await elegirDestinoFoto(recepcion,destinos.get(f)||{sku,origen,categoria,tipoEvidencia:$('[data-tipo]').value},f.name,f);if(valor){destinos.set(f,valor);pintar();}};card.append(img,nombre,destino,b);
    b.onclick=()=>{destinos.delete(f);elegidas.splice(i,1);pintar();};$('[data-seleccion]').append(card);
  });};
  captura.addEventListener('dragover',ev=>{if(ocupado)return;ev.preventDefault();captura.classList.add('zona-arrastre-activa');});
  captura.addEventListener('dragleave',()=>captura.classList.remove('zona-arrastre-activa'));
  captura.addEventListener('drop',ev=>{ev.preventDefault();captura.classList.remove('zona-arrastre-activa');if(ocupado||rec.estado==='CERRADA'&&!final)return;const fs=[...ev.dataTransfer.files].filter(f=>f.type.startsWith('image/'));elegidas.push(...fs);pintar();});
  for(const [boton,input] of [['camara','captura'],['galeria','archivos']]) {
    $(`[data-${boton}]`).onclick=async()=>{if(ocupado)return;if(boton==='galeria')return $(`[data-${input}]`).click();const foto=await tomarFotoEnPagina({titulo:sku?'Foto del producto · '+sku:'Foto de recepción',alUsarNativa:()=>$(`[data-${input}]`).click()});if(foto){elegidas.push(foto);pintar();}};
    $(`[data-${input}]`).onchange=ev=>{elegidas.push(...ev.target.files);ev.target.value='';pintar();};
  }
  async function cargar(reset=true) {
    if(!d.open)return;
    if(consultando){filtroPendiente=filtroPendiente||reset;return;}
    consultando=true;
    try {
    if(reset){offset=0;limpiarMiniaturas($('[data-imagenes]'));$('[data-imagenes]').replaceChildren();}
    const r=await pedir(`/recepciones/${encodeURIComponent(recepcion)}/imagenes?sku=${encodeURIComponent($('[data-filtro-sku]').value.trim())}&contexto=false&categoriaEvidencia=${encodeURIComponent($('[data-filtro-categoria]').value)}&offset=${offset}&limite=24${final?'&tipoEvidencia=ESTADO_FINAL':panoramica?'&tipoEvidencia='+encodeURIComponent(tipo):''}`);
    resumenSku=r.sincronizacion;
    for(const [i,f] of r.archivos.entries()) {
      if(final && !(f.evidencias || []).some(e=>e.tipo==='ESTADO_FINAL'))continue;
      const card=document.createElement('article');card.dataset.archivoId=f.id;
      const a=document.createElement('a');a.href=f.driveUrl || f.url;a.target='_blank';a.rel='noopener';
      const img=document.createElement('img');cargarMiniatura(img,f.url);img.loading='lazy';img.alt=f.nombre;a.append(img);a.onclick=ev=>{if(ev.ctrlKey||ev.metaKey)return;ev.preventDefault();verImagen(f);};card.append(a);
      const p=document.createElement('p');p.className='mini';p.textContent=`${offset+i+1}/${r.total} · ${f.nombre}`;card.append(p);const estadoFoto=document.createElement('p');estadoFoto.dataset.estadoFoto='';estadoFoto.className='foto-estado';estadoFoto.textContent=f.almacen==='DRIVE'?'Copia en Drive registrada':'Guardada en servidor · esperando copia a Drive';card.append(estadoFoto);
      const registro=document.createElement('p');registro.className='mini';registro.textContent=`Registro ${f.secuencia?'#'+String(f.secuencia).padStart(5,'0')+' · ':''}${f.registradaPor||''} · ${f.creadoEn?new Date(f.creadoEn).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}):''}`;card.append(registro);
      const tags=document.createElement('p');tags.className='mini';tags.textContent=(f.evidencias || []).map(e=>`${e.pallet?'Pallet '+e.pallet+' · ':''}${e.categoria}${sku&&e.sku===sku&&e.categoria!==categoria?' · Histórica':''}${e.sku?' · '+e.sku:''} · ${TIPOS_EVIDENCIA[e.tipo] || e.tipo}${e.origen ? ' · Packing list '+e.origen : ''}${e.embarque?' · Embarque '+e.embarque:' · General / sin embarque asignado'}`).join(' / ');card.append(tags);for(const e of f.evidencias||[]){if(e.rutaEsperada?.length){const ruta=document.createElement('p');ruta.className='foto-ruta mini';ruta.textContent='Carpeta: '+recepcion+' / '+e.rutaEsperada.join(' / ')+' · '+(e.estadoCarpeta==='SINCRONIZADA'?'Confirmada':'Pendiente de organizar');card.append(ruta);}}
      const filtroSku=$('[data-filtro-sku]').value.trim().toUpperCase(),filtroCategoria=$('[data-filtro-categoria]').value,vistos=new Set();
      for(const e of f.evidencias||[]){if(!e.carpetaDrive || filtroSku&&e.sku!==filtroSku || filtroCategoria&&e.categoria!==filtroCategoria || vistos.has(e.carpetaDrive) || !/^https:\/\/drive\.google\.com\//.test(e.carpetaDrive))continue;
        vistos.add(e.carpetaDrive);const link=document.createElement('a');link.href=e.carpetaDrive;link.target='_blank';link.rel='noopener';link.textContent=`Carpeta ${e.sku} · ${e.categoria}`;link.className='b-sec';card.append(link);}
      img.onerror=()=>{img.hidden=true;a.textContent=f.driveUrl?'✓ Foto guardada en Drive · Abrir original':'Foto guardada · Abrir vista completa';};
      if(supervisor&&rec.estado!=='CERRADA'){
        const editar=document.createElement('button');editar.className='b-sec';editar.textContent='Editar vínculo';editar.onclick=async()=>{
          const es=f.evidencias||[];if(!es.length)return;
          let e=es[0];if(es.length>1){const v=await pedirDatos({titulo:'Vínculo que deseas corregir',campos:[{clave:'id',etiqueta:'SKU / clasificación',tipo:'lista',valor:e.id,opciones:es.map(x=>({valor:x.id,titulo:(x.sku||'Recepción')+' · '+x.categoria+' · '+(x.origen||'Sin embarque')}))}]});if(!v)return;e=es.find(x=>x.id===v.id);}
          const v=await elegirDestinoFoto(recepcion,{sku:e.sku||'',categoria:e.categoria,tipoEvidencia:e.tipo,origen:e.origen||'',unidadId:e.unidadId||'',embarqueFoto:e.embarque??''},f.nombre,f.url);if(!v)return;
          editar.disabled=true;try{const r=await operacion('/evidencias/'+f.id,{metodo:'PUT',cuerpo:{...v,evidenciaId:e.id,unidadId:v.unidadId||'',protocolo:e.protocolo||'GENERAL'}});$('[data-estado]').textContent=r.mensaje;await cargar();}catch(err){$('[data-estado]').textContent=err.message;}finally{editar.disabled=false;}
        };card.append(editar);
      }
      if(supervisor && rec.estado!=='CERRADA'){const b=document.createElement('button');b.className='b-peligro';b.textContent='Retirar evidencia';b.onclick=async()=>{
        if(!await confirmar({titulo:'¿Retirar esta evidencia?',texto:'Se retira la imagen de todos sus vínculos con ítems y bultos. Se conserva la auditoría. La copia de Drive pasa a la papelera cuando haya conexión.',aceptar:'Retirar'}))return;
        try{await operacion('/evidencias/'+f.id,{metodo:'DELETE'});await cargar();}catch(e){$('[data-estado]').textContent=e.message;}
      };card.append(b);}
      $('[data-imagenes]').append(card);
    }
    offset+=r.archivos.length;$('[data-mas]').hidden=offset>=r.total;
    $('[data-resumen-galeria]').textContent=`${r.total} fotos ${final?'del estado final':sku?'de este SKU':'en esta selección'} · ${offset} mostradas`;
    await actualizarDrive();
    } finally {consultando=false;if(filtroPendiente&&d.open){filtroPendiente=false;await cargar();}}
  }
  async function actualizarDrive(refrescar=false) {
    if(!d.open || consultandoDrive)return;
    consultandoDrive=true;let refrescarGaleria=false;
    try { const estado=await operacion(`/recepciones/${encodeURIComponent(recepcion)}/drive`);
      if(!d.open)return;
      const revision=JSON.stringify([estado.sincronizacion,estado.carpetas,estado.archivos]);
      const cambio=revisionDrive && revisionDrive!==revision;revisionDrive=revision;
      const idsSku=new Set([...$('[data-imagenes]').querySelectorAll('[data-archivo-id]')].map(e=>e.dataset.archivoId));
      const archivos=sku?(estado.archivos||[]).filter(f=>idsSku.has(f.id)):(estado.archivos||[]);
      const s=sku?{guardadas:archivos.length,copiadas:archivos.filter(f=>f.estado==='COPIADA'&&f.ubicaciones.every(u=>u.estado==='SINCRONIZADA')).length,procesando:archivos.filter(f=>f.estado==='PROCESANDO').length,requierenAyuda:archivos.filter(f=>f.error).length}:estado.sincronizacion;
      if(sku)s.pendientes=s.guardadas-s.copiadas;
      if(s){$('[data-estado-drive]').textContent=`${sku?'SKU '+sku:'Recepción completa'}: ${s.guardadas} fotos guardadas · ${s.copiadas} confirmadas en Drive · ${s.pendientes} pendientes (${s.procesando} en proceso).`+
        (s.requierenAyuda?' Hay incidencias; revisa los archivos pendientes y solicita al supervisor comprobar la conexión de almacenamiento.':'');
        $('[data-reintentar]').hidden=!supervisor||!s.pendientes;
        $('[data-progreso-drive]').max=Math.max(1,s.guardadas);$('[data-progreso-drive]').value=s.copiadas;
        const aviso=s.pendientes?`${s.pendientes} foto(s) aún no están listas para el correo. ${s.requierenAyuda?'Hay errores: revisa el detalle de cada archivo.':'La copia continúa en segundo plano; puedes seguir registrando.'}`:'Todas las fotos de esta vista están confirmadas y organizadas en Drive.';
        if($('[data-alerta-drive]').textContent!==aviso)$('[data-alerta-drive]').textContent=aviso;
        $('[data-progreso-fotos]').classList.toggle('fotos-con-pendientes',!!s.pendientes);
        if(s.requierenAyuda)herramientas.open=true;
      }
      const etapas={VERIFICANDO:'Comprobando acceso',COPIANDO:'Subiendo a Drive',ORGANIZANDO:'Organizando carpeta',COPIADA:'Confirmada en Drive',PENDIENTE:'En espera',REVISION:'Necesita revisión',ERROR:'Copia pendiente por error'};
      $('[data-pendientes-drive]').replaceChildren();
      for(const f of archivos){
        const organizada=f.estado==='COPIADA'&&f.ubicaciones.every(u=>u.estado==='SINCRONIZADA');
        const texto=organizada?'✓ Confirmada en Drive':(etapas[f.proceso?.etapa]||etapas[f.estado]||f.estado)+(f.intentos?' · intento '+f.intentos:'');
        const card=[...$('[data-imagenes]').querySelectorAll('[data-archivo-id]')].find(e=>e.dataset.archivoId===f.id);
        if(card){card.querySelector('[data-estado-foto]').textContent=texto;if(organizada){const a=card.querySelector('a');if(a&&f.enlace)a.href=f.enlace;}}
        if(!organizada){const fila=document.createElement('p');fila.className='mini';fila.textContent=f.nombre+' · '+texto+(f.error?' · '+f.error:'')+(f.proximoIntento?' · reintento '+new Date(f.proximoIntento).toLocaleTimeString('es-EC',{timeZone:'America/Guayaquil'}):'');$('[data-pendientes-drive]').append(fila);}
      }
      $('[data-reloj-drive]').textContent='Estado actualizado: '+new Date().toLocaleTimeString('es-EC',{timeZone:'America/Guayaquil'})+' · revisión automática cada 3 s';
      if(!sku&&estado.carpetasRecepcion?.estado==='PENDIENTE')$('[data-estado-drive]').textContent+=' Carpetas de recepción pendientes de preparar; verifica la conexión del responsable.';
      $('[data-carpetas]').replaceChildren();for(const url of new Set(sku?[]:(estado.carpetas || []))){
        if(!/^https:\/\/drive\.google\.com\//.test(url))continue;
        const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener';a.textContent='Abrir carpeta de la recepción';a.className='b-sec';$('[data-carpetas]').append(a);
      }
      refrescarGaleria=false; // Los estados se actualizan sin reconstruir imágenes ni perder filtros.
    }catch(e){$('[data-alerta-drive]').textContent='No se pudo actualizar el estado: '+e.message+'. Las imágenes registradas se conservan.';$('[data-progreso-fotos]').classList.add('fotos-con-pendientes');}
    finally{consultandoDrive=false;}
    if(refrescarGaleria)await cargar();
  }
  $('[data-subir]').onclick=async()=>{
    if(!elegidas.length || ocupado)return;if($('[data-embarque-fotos]').value==='__ELEGIR__'&&elegidas.some(f=>!destinos.has(f))){$('[data-estado]').textContent='Selecciona el embarque del lote o revisa el destino de cada fotografía antes de guardar.';return;}ocupado=true;pintar();
    $('[data-subir]').disabled=true;$('[data-cerrar]').disabled=true;
    const controles=[...d.querySelectorAll('select,input,[data-camara],[data-galeria]')];
    controles.forEach(e=>e.disabled=true);
    try{
      const urls=await cargarEvidencias(recepcion,elegidas,{sku,desdeSku:!!sku,...($('[data-embarque-fotos]').value!=='__ELEGIR__'?{embarqueFoto:$('[data-embarque-fotos]').value}:{}),palletEvidencia:$('[data-pallet-evidencia]').value.trim().toUpperCase(),categoria:$('[data-categoria]').value,
        tipoEvidencia:$('[data-tipo]').value,protocolo:$('[data-protocolo]').value,
        unidadId:$('[data-unidad]').value,origen:$('[data-origen]').value},
        (n,t)=>{$('[data-estado]').textContent=`Guardando ${n} de ${t}…`;},cache,destinos);
      d.fotosGuardadas=[...new Set([...(d.fotosGuardadas||[]),...urls.map(u=>u.split('/').pop())])];
      elegidas=[];destinos.clear();cache=new Map();await cargar();
      $('[data-estado]').textContent=`${new Set(urls).size} imágenes únicas guardadas; copia a Drive en segundo plano.`;
    }catch(e){$('[data-estado]').textContent=e.message+' Puedes reintentar: las imágenes confirmadas no se repiten.';}
    finally{ocupado=false;pintar();controles.forEach(e=>e.disabled=false);if(final||panoramica){$('[data-tipo]').disabled=true;$('[data-categoria]').disabled=true;}if(panoramica)$('[data-unidad]').disabled=true;$('[data-subir]').disabled=!elegidas.length;$('[data-cerrar]').disabled=false;}
  };
  $('[data-filtrar]').onclick=()=>cargar().catch(e=>{$('[data-estado]').textContent=e.message;});
  $('[data-filtro-sku]').addEventListener('keydown',ev=>{if(ev.key==='Enter'&&!ev.isComposing&&!ev.repeat){ev.preventDefault();$('[data-filtrar]').click();}});
  $('[data-filtro-categoria]').onchange=()=>cargar().catch(e=>{$('[data-estado]').textContent=e.message;});
  $('[data-mas]').onclick=()=>cargar(false).catch(e=>{$('[data-estado]').textContent=e.message;});
  $('[data-actualizar]').onclick=()=>{if(!ocupado)cargar().catch(e=>{$('[data-estado]').textContent=e.message;});};
  $('[data-reintentar]').onclick=async()=>{
    if(ocupado)return;const b=$('[data-reintentar]');b.disabled=true;
    try{const r=await operacion(`/recepciones/${encodeURIComponent(recepcion)}/drive/reintentar`,{cuerpo:{}});$('[data-estado]').textContent=r.mensaje;await cargar();}
    catch(e){$('[data-estado]').textContent=e.message;}finally{b.disabled=false;}
  };
  $('[data-temporales]').onclick=()=>{if(!ocupado)abrirFotosPendientes(recepcion,{alGuardar:()=>cargar()}).catch(e=>{$('[data-estado]').textContent=e.message;});};
  async function cerrar(){if(ocupado)return;if(elegidas.length){if(!await confirmar({titulo:'Hay fotografías sin guardar',texto:'Guarda las imágenes antes de cerrar. Si el envío falla, se conservará la copia temporal cuando el navegador tenga almacenamiento disponible.',aceptar:'Guardar fotos seleccionadas y cerrar',cancelar:'Seguir revisando'}))return;await $('[data-subir]').onclick();if(elegidas.length)return;}d.close();}
  $('[data-cerrar]').onclick=cerrar;
  const temporizador=setInterval(()=>{if(d.open&&!document.hidden&&!consultando)
    actualizarDrive(true).catch(e=>{if(d.open)$('[data-estado-drive]').textContent=e.message;});},3000);
  const antesDeSalir=ev=>{if(ocupado||elegidas.length){ev.preventDefault();ev.returnValue='';}};window.addEventListener('beforeunload',antesDeSalir);
  d.addEventListener('cancel',ev=>{ev.preventDefault();cerrar();});d.addEventListener('close',()=>{window.removeEventListener('beforeunload',antesDeSalir);liberarVistas();clearInterval(temporizador);limpiarMiniaturas(d);d.remove();});
  try{await cargar();}catch(e){$('[data-estado]').textContent=e.message;}return d;
}
