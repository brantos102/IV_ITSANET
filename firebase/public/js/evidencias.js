import {pedir} from './local.js?v=20261016-31';
import {comprimir} from './imagen.js?v=20261016-31';
import {confirmar} from './modal.js?v=20261016-31';

export const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const operacion = (ruta, opciones={}) => pedir(ruta,{...opciones,base:'/api/operacion'});
export const TIPOS_EVIDENCIA = {
  EXTERIOR_BULTO:'Vista exterior del bulto', PACKING_INICIAL:'Packing list inicial',
  ABIERTO_CON_PACKING:'Bulto abierto con packing list visible', CAJA_CERRADA:'Caja cerrada',
  ETIQUETA_CAJA:'Etiqueta de caja madre', CAJA_ABIERTA:'Caja abierta',
  ITEM_NOVEDAD:'Detalle del producto con novedad', PANORAMICA:'Vista panorámica', ADICIONAL:'Evidencia adicional',
  DANO_EMBALAJE:'Daño en embalaje / caja madre',
};

/** Lote secuencial sin máximo de imágenes. Cada archivo conserva su resultado al reintentar. */
export async function cargarEvidencias(recepcion, archivos, datos, alAvanzar=()=>{}, cache=new Map()) {
  const urls=[];
  for(let i=0;i<archivos.length;i++) {
    const f=archivos[i];
    const clave=f; // Identidad File: nombre repetido no significa contenido repetido.
    if(!cache.has(clave)) {
      alAvanzar(i,archivos.length);
      const img=await comprimir(f);
      const r=await pedir(`/recepciones/${encodeURIComponent(recepcion)}/archivos/foto`,{
        cuerpo:{...datos,nombre:f.name || 'evidencia.jpg',base64:img.base64,tipo:img.tipo}});
      cache.set(clave,r.url);
    }
    urls.push(cache.get(clave));
    alAvanzar(i+1,archivos.length);
  }
  return urls;
}

export async function abrirEvidencias({recepcion,sku='',categoria='GENERAL',supervisor=false}) {
  const ingreso=await operacion(`/recepciones/${encodeURIComponent(recepcion)}/ingreso`);
  const d=document.createElement('dialog');d.className='dialogo-operativo';
  d.innerHTML=`<div class="acciones"><h2 style="flex:1">${sku ? 'Evidencias · '+esc(sku) : 'Evidencias de recepción'}</h2><button data-cerrar class="b-sec">Cerrar</button></div>
    <label class="campo"><span>Foto de</span><select data-tipo>${Object.entries(TIPOS_EVIDENCIA).map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join('')}</select></label>
    <details><summary>Clasificación y vínculos · ${esc(categoria)}</summary><div class="rejilla"><label class="campo"><span>Protocolo</span><select data-protocolo><option value="REGLAMENTARIO">Reglamentario</option><option value="GENERAL">General</option></select></label>
    <label class="campo"><span>Clasificación</span><select data-categoria>${['RECEPCION','FALTANTE','SOBRANTE','PNC','GENERAL'].map(c=>`<option>${c}</option>`).join('')}</select></label>
    <label class="campo"><span>Bulto / caja madre</span><select data-unidad><option value="">Sin unidad específica</option>${ingreso.unidades.map(u=>`<option value="${u.id}">${esc(u.tipo)} ${u.numero} · ${esc(u.codigo || 'sin código')}</option>`).join('')}</select></label>
    <label class="campo"><span>Packing list vinculado</span><input data-origen placeholder="PRINCIPAL o embarque"></label></div>
    <p class="mini" data-recomendacion></p></details><div class="acciones"><button data-camara class="b-primario">📷 Cámara del equipo</button><a class="b-sec" data-camara-windows href="microsoft.windows.camera:" hidden>Cámara de Windows</a><button data-galeria class="b-sec">＋ Galería</button><button data-subir class="b-sec">Guardar imágenes</button></div>
    <input data-captura type="file" accept="image/*" capture="environment" hidden><input data-archivos type="file" accept="image/*" multiple hidden>
    <div data-seleccion></div><p data-estado role="status"></p><div data-carpetas></div><div data-imagenes class="galeria-imagenes"></div><button data-mas class="b-sec">Ver más</button>`;
  document.body.append(d); d.showModal();
  const $=s=>d.querySelector(s);let elegidas=[],cache=new Map(),offset=0,ocupado=false;
  const esWindows=/Win/i.test(navigator.userAgentData?.platform || navigator.platform || '');
  $('[data-camara]').hidden=esWindows;$('[data-camara-windows]').hidden=!esWindows;
  $('[data-camara-windows]').onclick=ev=>{if(ocupado){ev.preventDefault();return;}$('[data-estado]').textContent='Toma la foto en Cámara de Windows. Regresa y toca Galería para adjuntarla a esta evidencia.';};
  if(supervisor){const a=document.createElement('a');a.href=`/api/operacion/recepciones/${encodeURIComponent(recepcion)}/evidencias.xlsx`;a.className='b-sec';a.textContent='Excel de trazabilidad';d.querySelector('.acciones').append(a);}
  $('[data-categoria]').value=categoria;
  $('[data-tipo]').value=sku ? 'ITEM_NOVEDAD' : 'EXTERIOR_BULTO';
  // Recibir sin fotos no impide adjuntar posteriormente evidencia de una novedad.
  $('[data-protocolo]').value=ingreso.protocolo==='SIN_FOTOS' ? 'GENERAL' : ingreso.protocolo || 'REGLAMENTARIO';
  const recomendar=()=>{$('[data-recomendacion]').textContent=$('[data-protocolo]').value==='GENERAL'
    ? 'Registro libre: fotos panorámicas o del detalle que necesites.'
    : sku ? 'Recomendado: caja cerrada, etiqueta de caja madre, caja abierta y detalle de la novedad.'
    : `Recomendado por bulto: ${ingreso.recomendaciones.exterioresMin} exteriores (objetivo ${ingreso.recomendaciones.exterioresObjetivo}) y ${ingreso.recomendaciones.abiertosMin} abierto con lista visible. Packing inicial: ${ingreso.recomendaciones.packingMin}.`;};
  recomendar();$('[data-protocolo]').onchange=recomendar;
  for(const selector of ['[data-protocolo]','[data-categoria]','[data-tipo]','[data-unidad]','[data-origen]']) {
    $(selector).addEventListener('change',()=>{cache=new Map();});
  }
  const pintar=()=>{$('[data-seleccion]').replaceChildren();elegidas.forEach((f,i)=>{
    const b=document.createElement('button');b.className='chip';b.textContent=`${i+1} · ${f.name} ✕`;b.disabled=ocupado;
    b.onclick=()=>{elegidas.splice(i,1);pintar();};$('[data-seleccion]').append(b);
  });};
  for(const [boton,input] of [['camara','captura'],['galeria','archivos']]) {
    $(`[data-${boton}]`).onclick=()=>$(`[data-${input}]`).click();
    $(`[data-${input}]`).onchange=ev=>{elegidas.push(...ev.target.files);ev.target.value='';pintar();};
  }
  async function cargar(reset=true) {
    if(reset){offset=0;$('[data-imagenes]').replaceChildren();}
    const r=await pedir(`/recepciones/${encodeURIComponent(recepcion)}/imagenes?sku=${encodeURIComponent(sku)}&contexto=true&offset=${offset}&limite=24`);
    for(const [i,f] of r.archivos.entries()) {
      const card=document.createElement('article');
      const a=document.createElement('a');a.href=f.driveUrl || f.url;a.target='_blank';a.rel='noopener';
      const img=document.createElement('img');img.src=f.url;img.loading='lazy';img.alt=f.nombre;a.append(img);card.append(a);
      const p=document.createElement('p');p.className='mini';p.textContent=`${offset+i+1}/${r.total} · ${f.nombre} · ${f.almacen}`;card.append(p);
      const tags=document.createElement('p');tags.className='mini';tags.textContent=(f.evidencias || []).map(e=>`${e.categoria} · ${TIPOS_EVIDENCIA[e.tipo] || e.tipo}${e.origen ? ' · '+e.origen : ''}`).join(' / ');card.append(tags);
      img.onerror=()=>{img.hidden=true;a.textContent='Abrir imagen en Drive (requiere permiso de Google)';};
      if(supervisor){const b=document.createElement('button');b.className='b-peligro';b.textContent='Retirar evidencia';b.onclick=async()=>{
        if(!await confirmar({titulo:'¿Retirar esta evidencia?',texto:'Se retira la imagen de todos sus vínculos con ítems y bultos. Se conserva la auditoría. La copia de Drive pasa a la papelera cuando haya conexión.',aceptar:'Retirar'}))return;
        try{await operacion('/evidencias/'+f.id,{metodo:'DELETE'});await cargar();}catch(e){$('[data-estado]').textContent=e.message;}
      };card.append(b);}
      $('[data-imagenes]').append(card);
    }
    offset+=r.archivos.length;$('[data-mas]').hidden=offset>=r.total;
    try { const estado=await operacion(`/recepciones/${encodeURIComponent(recepcion)}/drive`);
      $('[data-carpetas]').replaceChildren();for(const url of estado.carpetas || []){
        if(!/^https:\/\/drive\.google\.com\//.test(url))continue;
        const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener';a.textContent='Abrir carpeta en Drive';a.className='b-sec';$('[data-carpetas]').append(a);
      }
    }catch{/* El operario ve sus imágenes; las carpetas y la cola son de supervisión. */}
  }
  $('[data-subir]').onclick=async()=>{
    if(!elegidas.length || ocupado)return;ocupado=true;pintar();
    $('[data-subir]').disabled=true;$('[data-cerrar]').disabled=true;
    const controles=[...d.querySelectorAll('select,input,[data-camara],[data-galeria]')];
    controles.forEach(e=>e.disabled=true);
    try{
      const urls=await cargarEvidencias(recepcion,elegidas,{sku,categoria:$('[data-categoria]').value,
        tipoEvidencia:$('[data-tipo]').value,protocolo:$('[data-protocolo]').value,
        unidadId:$('[data-unidad]').value,origen:$('[data-origen]').value},
        (n,t)=>{$('[data-estado]').textContent=`Guardando ${n} de ${t}…`;},cache);
      elegidas=[];cache=new Map();await cargar();
      $('[data-estado]').textContent=`${new Set(urls).size} imágenes únicas guardadas; copia a Drive en segundo plano.`;
    }catch(e){$('[data-estado]').textContent=e.message+' Puedes reintentar: las imágenes confirmadas no se repiten.';}
    finally{ocupado=false;pintar();controles.forEach(e=>e.disabled=false);$('[data-subir]').disabled=false;$('[data-cerrar]').disabled=false;}
  };
  $('[data-mas]').onclick=()=>cargar(false).catch(e=>{$('[data-estado]').textContent=e.message;});
  $('[data-cerrar]').onclick=()=>d.close();
  d.addEventListener('cancel',ev=>{if(ocupado)ev.preventDefault();});d.addEventListener('close',()=>d.remove());
  try{await cargar();}catch(e){$('[data-estado]').textContent=e.message;}return d;
}
