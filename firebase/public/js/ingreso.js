import {pedir} from './local.js?v=20261015-26';
import {operacion,esc,abrirEvidencias} from './evidencias.js?v=20261015-26';
import {pedirDatos as pedirCampos,confirmar} from './modal.js?v=20261015-26';

export async function abrirIngreso(codigo,{continuar=()=>{}}={}) {
  const [recepcion,supervisores]=await Promise.all([
    pedir('/recepciones/'+encodeURIComponent(codigo)),operacion('/supervisores')]);
  let ingreso=await operacion(`/recepciones/${encodeURIComponent(codigo)}/ingreso`);
  const d=document.createElement('dialog');d.className='dialogo-operativo';
  d.innerHTML=`<div class="acciones"><h2 style="flex:1">Ingreso · ${esc(codigo)}</h2><button data-cerrar class="b-sec">Cerrar</button></div>
    <nav class="pasos-ingreso" aria-label="Pasos de recepción"><span>1 · Registro</span><span>2 · Bultos y evidencias</span><span>3 · Packing lists</span></nav>
    <div class="rejilla"><label class="campo"><span>Marca</span><input data-marca placeholder="Geely, Isuzu…"></label>
    <label class="campo"><span>Embarque / documento de transporte</span><input data-embarque></label>
    <label class="campo"><span>Supervisor responsable</span><select data-responsable>${supervisores.map(s=>`<option value="${esc(s.email)}">${esc(s.nombre)} · ${esc(s.email)}</option>`).join('')}</select></label>
    <label class="campo"><span>Protocolo fotográfico</span><select data-protocolo><option value="REGLAMENTARIO">Registro técnico reglamentario</option><option value="GENERAL">Registro operativo general / panorámicas</option></select></label>
    <label class="campo"><span>Total de bultos recibidos</span><input data-cantidad type="number" min="1" max="1000" value="${Number(recepcion.bultos)||1}"></label></div>
    <div class="acciones"><button data-guardar class="b-sec">Guardar datos y bultos</button><button data-fotos class="b-primario">📷 Registrar evidencias</button></div>
    <p class="mini">Cada bulto físico tiene número propio. Un código de caja madre puede repetirse en varios bultos. Las fotos recomendadas no bloquean el avance.</p>
    <div data-unidades></div><div data-avisos role="status"></div>
    <div class="acciones"><button data-continuar class="b-primario">Continuar a packing lists →</button></div>`;
  document.body.append(d);d.showModal();const $=s=>d.querySelector(s);
  for(const k of ['marca','embarque','responsable','protocolo'])if(ingreso[k])$(`[data-${k}]`).value=ingreso[k];
  if(!ingreso.responsable && supervisores.some(s=>s.email===recepcion.creadoPor)) $('[data-responsable]').value=recepcion.creadoPor;
  const ruta=`/recepciones/${encodeURIComponent(codigo)}`;
  async function pintar() {
    ingreso=await operacion(ruta+'/ingreso');
    $('[data-unidades]').innerHTML=ingreso.unidades.map(u=>`<article class="unidad-logistica"><b>${esc(u.tipo)} ${u.numero}</b><span>${esc(u.codigo || 'Código por registrar')}</span>
      <span class="mini">${esc((u.origenes||[]).join(' · '))}${u.padreId ? ' · Dentro de bulto '+esc(ingreso.unidades.find(p=>p.id===u.padreId)?.numero || '') : ''}</span>
      <button class="b-sec" data-editar="${u.id}">Editar código / listas</button>${u.tipo==='BULTO' ? `<button class="b-sec" data-caja="${u.id}">＋ Caja madre</button>` : ''}</article>`).join('');
    $('[data-avisos]').replaceChildren();for(const texto of ingreso.avisos){const p=document.createElement('p');p.className='mini';p.textContent='○ '+texto;$('[data-avisos]').append(p);}
  }
  async function guardar() {
    await operacion(ruta+'/ingreso',{metodo:'PUT',cuerpo:{marca:$('[data-marca]').value,
      embarque:$('[data-embarque]').value,responsable:$('[data-responsable]').value,
      protocolo:$('[data-protocolo]').value}});
    await operacion(ruta+'/bultos',{cuerpo:{cantidad:Number($('[data-cantidad]').value)}});
    await pintar();
  }
  const seguro=fn=>async()=>{try{await fn();}catch(e){$('[data-avisos]').textContent=e.message;}};
  $('[data-guardar]').onclick=seguro(guardar);
  $('[data-fotos]').onclick=seguro(async()=>{await guardar();const fotos=await abrirEvidencias({recepcion:codigo,categoria:'RECEPCION',supervisor:true});fotos.addEventListener('close',()=>pintar());});
  $('[data-unidades]').onclick=seguro(async()=>{});
  $('[data-unidades]').addEventListener('click',async ev=>{
    const b=ev.target.closest('[data-editar],[data-caja]');if(!b)return;
    try{
      const u=ingreso.unidades.find(u=>u.id===(b.dataset.editar || b.dataset.caja));
      const crear=!!b.dataset.caja;
      const campos=await pedirCampos({titulo:crear ? 'Nueva caja madre' : `Unidad ${u.numero}`,
        campos:[{clave:'codigo',etiqueta:'Código de caja madre / etiqueta',valor:crear ? '' : u.codigo},
          {clave:'origenes',etiqueta:'Packing lists vinculados, separados por coma',valor:crear ? '' : (u.origenes||[]).join(',')},
          {clave:'observacion',etiqueta:'Observación',valor:crear ? '' : u.observacion}]});
      if(!campos)return;
      await operacion(ruta+'/unidades',{cuerpo:{id:crear ? undefined : u.id,tipo:crear ? 'CAJA_MADRE' : u.tipo,
        padreId:crear ? u.id : u.padreId,...campos,origenes:campos.origenes.split(',').map(v=>v.trim()).filter(Boolean)}});
      await pintar();
    }catch(e){$('[data-avisos]').textContent=e.message;}
  });
  $('[data-continuar]').onclick=seguro(async()=>{
    await guardar();
    if(ingreso.avisos.length && !await confirmar({titulo:'Continuar con evidencias pendientes',
      texto:'Las recomendaciones quedan registradas. Puedes completar las fotos durante la recepción.',aceptar:'Continuar'}))return;
    await operacion(ruta+'/ingreso',{metodo:'PUT',cuerpo:{paso:'PACKING'}});
    d.close();continuar();
  });
  $('[data-cerrar]').onclick=()=>d.close();d.addEventListener('close',()=>d.remove());
  await pintar();return d;
}
