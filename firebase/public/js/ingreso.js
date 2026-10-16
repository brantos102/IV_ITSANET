import {pedir} from './local.js?v=20261016-30';
import {operacion,esc,cargarEvidencias,TIPOS_EVIDENCIA} from './evidencias.js?v=20261016-30';
import {pedirDatos as pedirCampos,confirmar} from './modal.js?v=20261016-30';
import {abrirCamara,errorDeCamara} from './camara.js?v=20261016-30';
import {interpretarEtiquetaMadre,fotografiarVideo} from './bultos.js?v=20261016-30';

/** Un bulto por pantalla. Fotos anexadas, cambios de unidad con versión. */
export async function abrirIngreso(codigo,{continuar=()=>{}}={}) {
  const ruta=`/recepciones/${encodeURIComponent(codigo)}`;
  let [recepcion,ingreso]=await Promise.all([pedir(ruta),operacion(ruta+'/ingreso')]);
  let indice=0,u=null,cerrarCamara=null,camaraSesion=0,ocupado=false,leyendo=false,pendientes=[],cache=new Map(),conflicto=false;
  const d=document.createElement('dialog');d.className='dialogo-operativo ingreso-guiado';
  d.innerHTML=`<header class="ingreso-cabecera"><div><strong>Recepción</strong><p class="mini codigo-recepcion">${esc(codigo)}</p></div><button data-cerrar class="b-sec">Cerrar</button></header><div data-cuerpo></div><p data-estado role="status" aria-live="polite"></p>`;
  document.body.append(d);d.showModal();const $=s=>d.querySelector(s);
  let versiones=new Map(),camaraPendiente=null;
  const estado=t=>{$('[data-estado]').textContent=t;};
  const bultos=()=>ingreso.unidades.filter(x=>x.tipo==='BULTO');
  const viewport=()=>{if(window.visualViewport)d.style.maxHeight=Math.max(180,window.visualViewport.height-20)+'px';};
  viewport();window.visualViewport?.addEventListener('resize',viewport);
  const apagar=()=>{camaraSesion++;cerrarCamara?.();cerrarCamara=null;};
  const manejarError=e=>{estado(e.message);if(e.estado===409){conflicto=true;if($('[data-recargar]'))$('[data-recargar]').hidden=false;}};
  const seguro=fn=>async()=>{if(ocupado)return;ocupado=true;d.dataset.ocupado='1';
    try{await fn();}catch(e){manejarError(e);}finally{ocupado=false;delete d.dataset.ocupado;}};
  async function refrescar(){ingreso=await operacion(ruta+'/ingreso');recepcion=await pedir(ruta);}
  async function guardarUnidad(cambios){
    ingreso=await operacion(ruta+'/unidades',{cuerpo:{id:u.id,tipo:u.tipo,version:u.version,...cambios}});
    u=ingreso.unidades.find(x=>x.id===u.id);versiones.set(u.id,u.version);return u;
  }
  async function guardarInicio(){
    const marca=$('[data-marca]').value.trim(),protocolo=$('[data-protocolo]').value;
    if(marca!==(ingreso.marca || '') || protocolo!==ingreso.protocolo || !ingreso.version)
      ingreso=await operacion(ruta+'/ingreso',{metodo:'PUT',cuerpo:{marca,protocolo,version:ingreso.version}});
    if(protocolo!=='SIN_FOTOS' && !bultos().length)ingreso=await operacion(ruta+'/bultos',{cuerpo:{cantidad:Math.max(1,Number(recepcion.bultos)||1)}});
  }
  async function continuarPacking(){
    await guardarInicio();
    await operacion(ruta+'/ingreso',{metodo:'PUT',cuerpo:{paso:'PACKING',version:ingreso.version}});
    d.close();continuar();
  }
  function inicio(){
    apagar();u=null;conflicto=false;estado('');
    const bs=bultos(),completos=bs.filter(b=>b.concluido).length;
    $('[data-cuerpo]').innerHTML=`<div class="ingreso-resumen"><b>${completos} de ${bs.length || recepcion.bultos || 1} bultos registrados</b><button class="b-sec" data-total>Corregir total</button></div>
      <div class="rejilla ingreso-opciones"><label class="campo"><span>Marca</span><input data-marca placeholder="Isuzu, Geely…" value="${esc(ingreso.marca || '')}"></label>
      <label class="campo"><span>Protocolo de fotos</span><select data-protocolo><option value="REGLAMENTARIO">Reglamentario</option><option value="GENERAL">Cotidiano / panorámicas</option><option value="SIN_FOTOS">Sin registro fotográfico</option></select></label></div>
      <p class="mini" data-sin-fotos hidden>La decisión del supervisor queda registrada. Continúa al packing list sin tomar fotos.</p>
      <button class="b-primario ingreso-principal" data-empezar>${completos ? 'Continuar bultos' : 'Empezar primer bulto'} · escanear y fotografiar</button>
      <details class="ingreso-lista"><summary>Revisar bultos (${bs.length})</summary>${bs.map((b,i)=>`<button class="b-sec" data-ir="${i}">Bulto ${b.numero} · ${esc(b.codigo || 'sin etiqueta')} · ${b.concluido?'Registrado':'Pendiente'}</button>`).join('')}</details>
      <button class="b-sec" data-recargar hidden>Revisar cambios del otro supervisor</button><footer class="ingreso-pie"><button class="b-sec" data-packing>Continuar a packing lists →</button></footer>`;
    $('[data-protocolo]').value=ingreso.protocolo || 'REGLAMENTARIO';
    const pintarProtocolo=()=>{const sinFotos=$('[data-protocolo]').value==='SIN_FOTOS';
      $('[data-sin-fotos]').hidden=!sinFotos;
      $('[data-empezar]').textContent=sinFotos ? 'Continuar sin fotos → packing list' : `${completos ? 'Continuar bultos' : 'Empezar primer bulto'} · escanear y fotografiar`;
      $('.ingreso-lista').hidden=sinFotos;
    };
    $('[data-protocolo]').onchange=pintarProtocolo;pintarProtocolo();
    $('[data-recargar]').onclick=seguro(async()=>{const marca=$('[data-marca]').value,protocolo=$('[data-protocolo]').value,anterior=ingreso;
      await refrescar();inicio();if(marca!==(anterior.marca || ''))$('[data-marca]').value=marca;if(protocolo!==anterior.protocolo)$('[data-protocolo]').value=protocolo;
      pintarProtocolo();estado('Ingreso actualizado. Revisa marca y protocolo antes de guardar.');});
    $('[data-empezar]').onclick=seguro(async()=>{if($('[data-protocolo]').value==='SIN_FOTOS'){await continuarPacking();return;}await guardarInicio();indice=Math.max(0,bultos().findIndex(b=>!b.concluido));await mostrarBulto();});
    $('[data-total]').onclick=seguro(async()=>{const v=await pedirCampos({titulo:'Total de bultos',campos:[{clave:'cantidad',etiqueta:'Bultos recibidos',tipo:'number',valor:recepcion.bultos || bs.length || 1,obligatorio:true}]});if(!v)return;
      ingreso=await operacion(ruta+'/bultos',{cuerpo:{cantidad:Number(v.cantidad),cantidadAnterior:recepcion.bultos}});await refrescar();inicio();});
    $('[data-packing]').onclick=seguro(continuarPacking);
    $('[data-cuerpo]').querySelectorAll('[data-ir]').forEach(b=>b.onclick=seguro(async()=>{await guardarInicio();indice=Number(b.dataset.ir);await mostrarBulto();}));
  }
  async function encender(){
    if(cerrarCamara || camaraPendiente===camaraSesion)return;
    const sesion=++camaraSesion,video=$('[data-video]');camaraPendiente=sesion;
    try{
      const cerrar=await abrirCamara(video,raw=>{
        if(ocupado || conflicto || !leyendo || !d.open || sesion!==camaraSesion)return;
        leyendo=false;seguro(async()=>{const etiqueta=interpretarEtiquetaMadre(raw);
          await guardarUnidad({...etiqueta,pallet:etiqueta.pallet || (u.codigo===etiqueta.codigo ? u.pallet : '')});
          pintarEtiqueta();estado('Etiqueta registrada. Puedes tomar las fotos.');
        })().finally(()=>{if(!u?.codigo)leyendo=true;});
      },{puedeLeer:()=>leyendo && !ocupado && !conflicto});
      if(sesion!==camaraSesion || !d.open){cerrar();return;}
      cerrarCamara=cerrar;$('[data-activar]').hidden=true;$('[data-error-camara]').hidden=true;video.parentElement.classList.remove('sin-camara');
    }catch(e){if(sesion===camaraSesion){const mensaje=errorDeCamara(e);
      estado(mensaje);$('[data-error-camara]').textContent=mensaje;$('[data-error-camara]').hidden=false;video.parentElement.classList.add('sin-camara');$('[data-activar]').hidden=false;}}
    finally{if(camaraPendiente===sesion)camaraPendiente=null;}
  }
  function pintarEtiqueta(){
    $('[data-etiqueta]').textContent=u.codigo ? `Etiqueta: ${u.codigo}${u.pallet ? ' · Pallet: '+u.pallet : ''}` : 'Escanea la etiqueta madre';
    $('[data-tomar]').textContent='📷 Tomar foto';
    $('[data-pallet]').value=u.pallet || '';
  }
  function pintarCantidad(){
    const ids=new Set([u.id,...ingreso.unidades.filter(x=>x.padreId===u.id).map(x=>x.id)]);
    const fotos=new Set(ingreso.evidencias.filter(e=>ids.has(e.unidadId)).map(e=>e.archivoId)).size;
    $('[data-cantidad-fotos]').textContent=`${fotos} foto${fotos===1?'':'s'} guardada${fotos===1?'':'s'}`;
    $('[data-reintentar]').hidden=!pendientes.length;
    for(const selector of ['[data-tipo]','[data-unidad-foto]','[data-origen]'])$(selector).disabled=!!pendientes.length;
  }
  async function subir(){
    if(!pendientes.length)return;
    const unidad=$('[data-unidad-foto]').value || u.id;
    pintarCantidad();
    await cargarEvidencias(codigo,pendientes,{unidadId:unidad,unidadVersion:versiones.get(unidad),
      categoria:'RECEPCION',tipoEvidencia:$('[data-tipo]').value,protocolo:ingreso.protocolo || 'REGLAMENTARIO',
      origen:$('[data-origen]').value.trim()},(n,t)=>estado(`Guardando foto ${n} de ${t}…`),cache);
    pendientes=[];cache=new Map();ingreso=await operacion(ruta+'/ingreso');
    pintarCantidad();estado('Fotos guardadas.');
  }
  async function galeria(){
    const r=await pedir(`${ruta}/imagenes?unidadId=${encodeURIComponent(u.id)}&limite=100`);
    $('[data-galeria]').replaceChildren();
    for(const f of r.archivos){const a=document.createElement('a');a.href=f.driveUrl || f.url;a.target='_blank';a.rel='noopener';
      const img=document.createElement('img');img.src=f.url;img.alt='Evidencia del bulto '+u.numero;img.loading='lazy';a.append(img);$('[data-galeria]').append(a);}
    $('[data-galeria-nota]').textContent=r.total>100 ? `Se muestran las últimas 100 de ${r.total}. Todas se conservan en la galería de recepción.` : `${r.total} imágenes de este bulto y sus cajas.`;
  }
  async function mostrarBulto(){
    apagar();pendientes=[];cache=new Map();conflicto=false;
    await refrescar();if(ingreso.protocolo==='SIN_FOTOS'){inicio();return;}u=bultos()[indice];if(!u){inicio();return;}
    leyendo=!u.codigo;versiones=new Map(ingreso.unidades.map(x=>[x.id,x.version]));
    const hijos=ingreso.unidades.filter(x=>x.padreId===u.id);
    $('[data-cuerpo]').innerHTML=`<div class="ingreso-resumen"><h2>Bulto ${u.numero} de ${bultos().length}</h2><button class="b-sec" data-resumen>Resumen</button></div>
      <p data-etiqueta class="etiqueta-madre"></p><div class="camara-bulto"><video data-video playsinline muted></video><p data-error-camara class="mini" hidden></p><button class="b-sec" data-activar>Activar cámara</button></div>
      <div class="acciones ingreso-herramientas"><button class="b-sec" data-escanear>↻ Escanear etiqueta</button><button class="b-sec" data-manual>Escribir código</button></div>
      <label class="campo"><span>Fotos de</span><select data-tipo>${['EXTERIOR_BULTO','ABIERTO_CON_PACKING','ETIQUETA_CAJA','DANO_EMBALAJE','PACKING_INICIAL','PANORAMICA','ADICIONAL'].map(k=>`<option value="${k}">${esc(TIPOS_EVIDENCIA[k])}</option>`).join('')}</select></label>
      <div class="acciones ingreso-herramientas"><button class="b-primario" data-tomar>📷 Tomar foto</button><button class="b-sec" data-archivos>＋ Galería</button><button class="b-sec" data-reintentar hidden>Reintentar fotos</button></div><input type="file" data-ficheros accept="image/*" multiple hidden>
      <p class="mini" data-cantidad-fotos></p><details data-fotos-guardadas><summary>Ver fotos del bulto</summary><div data-galeria class="fotos-bulto"></div><p data-galeria-nota class="mini"></p></details>
      <details class="nota-bulto"><summary>＋ Observación opcional</summary><textarea data-nota rows="2" maxlength="300" placeholder="Estado del embalaje o novedad…">${esc(u.observacion || '')}</textarea></details>
      <details><summary>Guía de fotos</summary><p class="mini">${ingreso.protocolo==='GENERAL' ? `${ingreso.recomendaciones.panoramicasMin} panorámicas recomendadas por recepción.` : `${ingreso.recomendaciones.exterioresMin} exteriores por bulto (objetivo ${ingreso.recomendaciones.exterioresObjetivo}), ${ingreso.recomendaciones.abiertosMin} abierto con lista visible y ${ingreso.recomendaciones.packingMin} packing inicial por recepción.`} Sin máximo de imágenes.</p></details>
      <details><summary>Caja interior, pallet o lista (opcional)</summary><label class="campo"><span>Packing list</span><input data-origen value="${esc((u.origenes || recepcion.origenes || [])[0] || 'PRINCIPAL')}"></label>
      <label class="campo"><span>Ubicación / pallet</span><input data-pallet value="${esc(u.pallet || '')}"></label>
      <label class="campo"><span>Unidad de las fotos</span><select data-unidad-foto><option value="${u.id}">Bulto ${u.numero}</option>${hijos.map(h=>`<option value="${h.id}">Caja ${h.numero} · ${esc(h.codigo)}</option>`).join('')}</select></label><button class="b-sec" data-caja>＋ Caja interior</button><button class="b-sec" data-editar-unidad>Editar unidad seleccionada</button></details>
      <button class="b-sec" data-recargar hidden>Revisar cambios del otro supervisor</button>
      <footer class="ingreso-pie"><button class="b-primario" data-siguiente>${indice<bultos().length-1 ? 'Guardar y siguiente bulto →' : 'Guardar y terminar bultos ✓'}</button></footer>`;
    $('[data-tipo]').value=ingreso.protocolo==='GENERAL' ? 'PANORAMICA' : 'EXTERIOR_BULTO';
    pintarEtiqueta();pintarCantidad();estado('');
    $('[data-activar]').onclick=seguro(encender);
    $('[data-escanear]').onclick=seguro(async()=>{leyendo=true;estado('Enfoca el código de la etiqueta madre.');await encender();});
    $('[data-manual]').onclick=seguro(async()=>{leyendo=false;const v=await pedirCampos({titulo:'Etiqueta madre',campos:[{clave:'codigo',etiqueta:'Código madre',valor:u.codigo,obligatorio:true}]});
      if(!v){leyendo=!u.codigo;return;}const e=interpretarEtiquetaMadre(v.codigo);await guardarUnidad({...e,pallet:e.pallet || (u.codigo===e.codigo ? u.pallet : '')});pintarEtiqueta();});
    $('[data-tomar]').onclick=seguro(async()=>{if(conflicto)throw new Error('Revisa los cambios antes de adjuntar fotos.');
      if(!cerrarCamara){await encender();return;}leyendo=false;pendientes.push(await fotografiarVideo($('[data-video]')));try{await subir();}finally{pintarCantidad();if(!u.codigo)leyendo=true;}});
    $('[data-archivos]').onclick=()=>{if(!ocupado && !conflicto)$('[data-ficheros]').click();};
    $('[data-ficheros]').onchange=seguro(async()=>{const files=$('[data-ficheros]').files;pendientes.push(...files);$('[data-ficheros]').value='';try{await subir();}finally{pintarCantidad();}});
    $('[data-reintentar]').onclick=seguro(async()=>{if(conflicto)throw new Error('Revisa los cambios antes de reintentar.');await subir();});
    $('[data-fotos-guardadas]').addEventListener('toggle',ev=>{if(ev.target.open)galeria().catch(manejarError);});
    const terminar=async()=>{if(conflicto)throw new Error('Revisa los cambios antes de guardar.');await subir();
      await guardarUnidad({observacion:$('[data-nota]').value,pallet:$('[data-pallet]').value,
        origenes:[...new Set([...(u.origenes || []),$('[data-origen]').value.trim()].filter(Boolean))],concluido:true});};
    $('[data-siguiente]').onclick=seguro(async()=>{await terminar();indice++;if(indice>=bultos().length)inicio();else await mostrarBulto();});
    $('[data-resumen]').onclick=seguro(async()=>{await subir();await guardarUnidad({observacion:$('[data-nota]').value,pallet:$('[data-pallet]').value});inicio();});
    $('[data-caja]').onclick=seguro(async()=>{const v=await pedirCampos({titulo:'Caja interior de bulto '+u.numero,campos:[{clave:'codigo',etiqueta:'Código de caja madre',obligatorio:true}]});if(!v)return;
      const antes=new Set(ingreso.unidades.map(x=>x.id));ingreso=await operacion(ruta+'/unidades',{cuerpo:{tipo:'CAJA_MADRE',padreId:u.id,codigo:v.codigo,origenes:[$('[data-origen]').value.trim()].filter(Boolean)}});
      const h=ingreso.unidades.find(x=>!antes.has(x.id));versiones.set(h.id,h.version);const o=document.createElement('option');o.value=h.id;o.textContent='Caja '+h.numero+' · '+h.codigo;$('[data-unidad-foto]').append(o);$('[data-unidad-foto]').value=h.id;});
    $('[data-editar-unidad]').onclick=seguro(async()=>{const seleccion=$('[data-unidad-foto]').value,unidad=seleccion===u.id ? u : ingreso.unidades.find(x=>x.id===seleccion);
      const v=await pedirCampos({titulo:'Código y listas de la unidad',campos:[{clave:'codigo',etiqueta:'Código madre',valor:unidad.codigo},{clave:'origenes',etiqueta:'Listas vinculadas, separadas por coma',valor:(unidad.origenes || []).join(',')}]});if(!v)return;
      ingreso=await operacion(ruta+'/unidades',{cuerpo:{id:unidad.id,tipo:unidad.tipo,version:versiones.get(unidad.id),codigo:v.codigo,origenes:v.origenes.split(',').map(s=>s.trim()).filter(Boolean)}});
      const nueva=ingreso.unidades.find(x=>x.id===unidad.id);versiones.set(nueva.id,nueva.version);
      if(nueva.id===u.id){u=nueva;$('[data-etiqueta]').textContent='Etiqueta: '+u.codigo+(u.pallet ? ' · Pallet: '+u.pallet : '');}
      else $('[data-unidad-foto]').selectedOptions[0].textContent='Caja '+nueva.numero+' · '+nueva.codigo;
    });
    $('[data-recargar]').onclick=seguro(async()=>{const nota=$('[data-nota]').value,pallet=$('[data-pallet]').value,anterior=u;
      await refrescar();u=ingreso.unidades.find(x=>x.id===u.id);conflicto=false;leyendo=false;versiones=new Map(ingreso.unidades.map(x=>[x.id,x.version]));pintarEtiqueta();$('[data-recargar]').hidden=true;
      if(nota===(anterior.observacion || ''))$('[data-nota]').value=u.observacion || '';
      if(pallet!==(anterior.pallet || ''))$('[data-pallet]').value=pallet;
      estado(`Último registro: ${u.actualizadoPor || 'otro supervisor'}. Observación guardada: ${u.observacion || '—'}. Revisa tus datos antes de guardar.`);pintarCantidad();});
    void encender();
  }
  async function cerrar(){if(ocupado)return;
    if(u && !conflicto){try{ocupado=true;await subir();await guardarUnidad({observacion:$('[data-nota]').value,pallet:$('[data-pallet]').value});}catch(e){manejarError(e);return;}finally{ocupado=false;}}
    if(conflicto && !await confirmar({titulo:'Salir sin sobrescribir cambios',texto:`Las fotos ya guardadas permanecen. Se descartarán la observación local sin guardar${pendientes.length ? ' y '+pendientes.length+' foto(s) pendientes de guardar' : ''}.`,aceptar:'Salir'}))return;
    d.close();
  }
  $('[data-cerrar]').onclick=cerrar;
  d.addEventListener('cancel',ev=>{ev.preventDefault();cerrar();});
  d.addEventListener('close',()=>{apagar();window.visualViewport?.removeEventListener('resize',viewport);d.remove();});
  inicio();return d;
}
