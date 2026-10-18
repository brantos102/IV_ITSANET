import {verImagen} from './visor-imagen.js?v=20261018-46';
import {abrirCorreo} from './correo-redactado.js?v=20261018-46';
import {pedir} from './local.js?v=20261018-46';
import {pedirDatos,confirmar} from './modal.js?v=20261018-46';
import {declararEnviadoManual,cambiarArchivoHistorial} from './gestion-entregas.js?v=20261018-46';

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fecha = e => new Date(e.creadoEn).toLocaleString('es-EC', {timeZone:'America/Guayaquil'});
const referencia = e => e.informe?.numero ? 'R'+String(e.informe.numero).padStart(4,'0') : e.id.slice(0,8);
const enlace = (url, titulo) => /^https:\/\/(drive|docs)\.google\.com\//.test(url || '')
  ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(titulo)}</a>` : '';
const operacion = (ruta, opciones={}) => pedir(ruta, {...opciones, base:'/api/operacion'});

export async function revisarDrive(codigo, aviso, operativo=false) {
  const d = document.createElement('dialog'); d.className='modal';
  d.innerHTML=`<h3>Fotos y carpetas · ${esc(codigo)}</h3><div data-estado role="status">Consultando fotos…</div>
    <details open><summary>Archivos y carpetas en tiempo real</summary><input data-filtro-archivos placeholder="Filtrar por SKU, nombre o carpeta" aria-label="Filtrar archivos"><div data-tabla-archivos class="tabla-env"></div></details><p data-resultado role="status"></p><div class="modal-acciones"><button class="b-sec" data-actualizar>Actualizar</button>
    <button class="b-primario" data-preparar>${operativo?'Reintentar fotos pendientes':'Verificar y crear carpetas'}</button><button class="b-sec" data-mi-cuenta>Copiar pendientes desde mi cuenta</button><button class="b-sec" data-cerrar>Cerrar</button></div>`;
  document.body.append(d); d.showModal();
  const ruta='/recepciones/'+encodeURIComponent(codigo)+'/drive'; let ocupado=false;
  const actualizar = async () => {
    if(ocupado || !d.open)return; ocupado=true;
    try {
      const r=await operacion(ruta), s=r.sincronizacion, destino=r.destino || r.destinoOperativo || {};
      d.querySelector('[data-estado]').innerHTML=`<p><b>${s.copiadas} de ${s.guardadas} fotos confirmadas en Drive</b> · ${s.pendientes} pendientes · ${s.procesando} en proceso.</p>
        <p>Cuenta responsable: <b>${esc(destino.supervisor || 'Sin configurar')}</b><br>Ruta: ${esc([destino.cliente,destino.marca,codigo].filter(Boolean).join(' / '))}</p>
        <p>${destino.carpetaRaiz ? enlace('https://drive.google.com/drive/folders/'+destino.carpetaRaiz,'Abrir carpeta raíz configurada') : 'Carpeta raíz: se usa CARPETA_EVIDENCIAS del puente Google.'}</p>
        ${(r.carpetas || []).map(u=>`<p>${enlace(u,'Abrir carpeta de la recepción')}</p>`).join('')}
        ${r.avisos?.length ? `<div class="mini">${r.avisos.map(a=>`<p>${esc(a)}</p>`).join('')}<p>Si falla la clave, guarda la misma SERVIDOR_HMAC en el puente de esta cuenta y vuelve a verificar. No hace falta generar otra clave.</p></div>` : ''}
        <details><summary>Ubicación de cada foto (${r.archivos?.length || 0})</summary>${(r.archivos || []).map(a=>`<p><b>${esc(a.nombre)}</b> · ${esc(a.estado)}<br>${esc((a.ruta || []).join(' / '))}<br>${enlace(a.enlace,'Abrir foto')} ${enlace(a.carpeta,'Abrir carpeta')}${a.error?`<br>${esc(a.error)}`:''}</p>`).join('')}</details>`;
      const pintarArchivos=()=>{const filtro=d.querySelector('[data-filtro-archivos]').value.trim().toUpperCase();const filas=(r.archivos||[]).filter(a=>(a.nombre+' '+(a.ruta||[]).join(' / ')).toUpperCase().includes(filtro));d.querySelector('[data-tabla-archivos]').innerHTML='<table><thead><tr><th>Foto</th><th>SKU / tipo</th><th>Estado</th><th>Ruta de carpeta</th><th>Acciones</th></tr></thead><tbody>'+filas.map(a=>`<tr><td>${esc(a.nombre)}</td><td>${esc(a.sku||'Recepción')}<br>${esc(a.tipo||'')}</td><td>${esc(a.estado)}</td><td>${esc([destino.cliente,destino.marca,codigo,...(a.ruta||[])].filter(Boolean).join(' / '))}${a.error?'<p>'+esc(a.error)+'</p>':''}</td><td><button class="b-sec" data-ver-foto="${esc(a.id)}">Vista previa</button>${enlace(a.carpeta,'Carpeta confirmada')} ${enlace(a.enlace,'Original')}</td></tr>`).join('')+'</tbody></table>';d.querySelectorAll('[data-ver-foto]').forEach(b=>b.onclick=()=>{const a=filas.find(a=>a.id===b.dataset.verFoto);verImagen({url:'/api/app/archivos/'+a.id,nombre:a.nombre,driveUrl:a.enlace});});};d.querySelector('[data-filtro-archivos]').oninput=pintarArchivos;pintarArchivos();
    } catch(e){d.querySelector('[data-resultado]').textContent=e.message;}
    finally{ocupado=false;}
  };
  d.querySelector('[data-preparar]').onclick=async ev=>{
    const b=ev.currentTarget; b.disabled=true;
    try{const r=await operacion(ruta+(operativo?'/reintentar':'/preparar'),{cuerpo:{}});
      d.querySelector('[data-resultado]').innerHTML=`${enlace(r.carpeta,'Abrir carpeta confirmada')}<p>${esc(r.mensaje)} ${r.programadas} foto(s) programadas.</p>`;
      await actualizar();
    }catch(e){d.querySelector('[data-resultado]').textContent=e.message;aviso(e.message,'err');}finally{b.disabled=false;}
  };
  d.querySelector('[data-mi-cuenta]').onclick=async ev=>{
    const b=ev.currentTarget;
    if(!await confirmar({titulo:'Copiar fotos desde tu conexión Google',texto:'Se usará tu cuenta autorizada para las fotos pendientes de esta recepción. Debe tener acceso a la carpeta matriz. Los informes se conservan y aún no se envía correo.',aceptar:'Verificar y copiar'}))return;
    b.disabled=true;
    try{const r=await operacion(ruta+'/desde-mi-cuenta',{cuerpo:{}});d.querySelector('[data-resultado]').textContent=r.mensaje;await actualizar();}
    catch(e){d.querySelector('[data-resultado]').textContent=e.message;}finally{b.disabled=false;}
  };
  d.querySelector('[data-actualizar]').onclick=actualizar;
  d.querySelector('[data-cerrar]').onclick=()=>d.close();
  const intervalo=setInterval(actualizar,5000);
  d.addEventListener('close',()=>{clearInterval(intervalo);d.remove();},{once:true});
  await actualizar();
}

export function pintarEntregas(contenedor, entregas, {aviso, actualizar, operativo=false}) {
  contenedor.replaceChildren();
  if(!entregas.length){contenedor.textContent='Todavía no hay entregas registradas.';return;}
  const grupos=new Map();
  for(const e of entregas){if(!grupos.has(e.recepcion))grupos.set(e.recepcion,[]);grupos.get(e.recepcion).push(e);}
  const boton=(fila,texto,accion,clase='b-sec')=>{
    const b=document.createElement('button');b.type='button';b.className=clase;b.textContent=texto;
    b.onclick=async()=>{b.disabled=true;try{await accion();}catch(e){aviso(e.message,'err');}finally{b.disabled=false;}};fila.append(b);
  };
  for(const [codigo,grupo] of grupos){
    const seccion=document.createElement('section');seccion.className='panel';
    const titulo=document.createElement('h3');titulo.textContent=codigo;seccion.append(titulo);
    // El servidor ordena por fecha; ante empates ordenar también por id.
    grupo.sort((a,b)=>b.creadoEn.localeCompare(a.creadoEn)||b.id.localeCompare(a.id));
    const ultima=grupo[0], activas=grupo.filter(e=>['PENDIENTE','PROCESANDO','REVISION'].includes(e.estado));
    const resumen=document.createElement('p');resumen.textContent=activas.length?`${activas.length} entrega(s) por resolver`:
      ultima.correoManual?(ultima.correoManual.estado==='DECLARADO_ENVIADO'?'Envío manual declarado por el supervisor.':'Correo preparado para envío manual.'):ultima.estado==='ENTREGADA'?'Entrega confirmada.':'Sin envío activo. Los envíos anulados no se enviarán.';seccion.append(resumen);
    boton(seccion,'Revisar Drive y fotos',()=>revisarDrive(codigo,aviso,operativo));
    if(['ENTREGADA','PROCESANDO'].includes(ultima.estado)||ultima.correoManual?.estado==='DECLARADO_ENVIADO')boton(seccion,'Ver correo final archivado',()=>abrirCorreo(codigo,{entregaId:ultima.id}));
    const dibujar=(e,padre)=>{
      const fila=document.createElement('article');fila.style.marginBlock='16px';
      const p=document.createElement('p');p.textContent=`${referencia(e)} · ${fecha(e)} · ${e.correoManual?(e.correoManual.estado==='DECLARADO_ENVIADO'?'MANUAL · ENVÍO DECLARADO':'MANUAL · POR ENVIAR'):e.estado} · De: ${e.remitente || e.supervisor} · Para: ${e.destinatarios || 'Sin correo'}`;fila.append(p);
      const m=document.createElement('p');m.className='mini';m.textContent=(e.mensaje || '')+(e.ayuda?' '+e.ayuda:'')+(e.intentos?' · Intentos: '+e.intentos:'')+(e.proximoIntento&&e.estado==='PENDIENTE'?' · Próximo intento: '+new Date(e.proximoIntento).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}):'');if(e.correoManual)m.textContent=(e.correoManual.estado==='DECLARADO_ENVIADO'?'Envío manual declarado por '+e.correoManual.usuario+'; sin acuse de Google.':'Preparado para envío manual. El envío automático está detenido.');fila.append(m);
      const urls=document.createElement('div');urls.innerHTML=enlace(e.resultado?.carpeta,'Abrir Drive')+' '+enlace(e.resultado?.sheet,'Abrir Sheets');fila.append(urls);
      if(['PENDIENTE','REVISION'].includes(e.estado)){
        boton(fila,'Ya se envió manualmente',async()=>{if(await declararEnviadoManual(e)){aviso('Envío manual registrado; reintentos detenidos.','ok');await actualizar();}});
        boton(fila,'Anular este envío',async()=>{
          const datos=await pedirDatos({titulo:`Anular envío ${referencia(e)}`,texto:`${esc(codigo)} · ${esc(fecha(e))}. Se conservan archivos, conteos y auditoría.`,
            campos:[{clave:'motivo',etiqueta:'Motivo de anulación (mínimo 10 caracteres)',obligatorio:true}],aceptar:'Anular este envío'});
          if(!datos)return;await pedir('/entregas/'+e.id+'/cancelar',{cuerpo:datos});aviso('Envío anulado; archivos conservados.','ok');await actualizar();
        },'b-peligro');
      }
      if(e.estado==='CANCELADA'&&e.correoManual?.estado==='PREPARADO')boton(fila,'Ya se envió manualmente',async()=>{if(await declararEnviadoManual(e)){aviso('Envío manual registrado.','ok');await actualizar();}});
      if(e.estado==='ENTREGADA'||e.estado==='CANCELADA'&&e.correoManual?.estado!=='PREPARADO')boton(fila,e.archivado?'Restaurar historial':'Retirar del historial',async()=>{if(await cambiarArchivoHistorial(e)){aviso('Historial actualizado; documentos conservados.','ok');await actualizar();}});
      if(e.errorAnterior && ['CANCELADA','ENTREGADA'].includes(e.estado)){
        const h=document.createElement('details'),s=document.createElement('summary');s.textContent='Diagnóstico anterior (historial)';h.append(s);
        const t=document.createElement('p');t.textContent=e.errorAnterior;h.append(t);fila.append(h);
      }
      padre.append(fila);
    };
    const visibles=[...activas,...grupo.filter(e=>e.esUltima&&e.correoManual?.estado==='PREPARADO'&&!activas.includes(e))];
    visibles.forEach(e=>dibujar(e,seccion));
    if(['PENDIENTE','CANCELADA','REVISION'].includes(ultima.estado)&&ultima.correoManual?.estado!=='DECLARADO_ENVIADO'){
      if(ultima.confirmacionDisponible){const listo=document.createElement('p');listo.className='msg ok';listo.textContent='Tu conexión está verificada. Los documentos finales esperan tu revisión y confirmación; todavía no se enviaron.';seccion.append(listo);}
      boton(seccion,ultima.confirmacionDisponible?'Conexión verificada · revisar correo y confirmar':'Revisar correo final · copiar o enviar',()=>abrirCorreo(codigo,{entregaId:ultima.id}),'b-primario');
    }
    const historicas=grupo.filter(e=>!visibles.includes(e));
    if(historicas.length){const h=document.createElement('details'),s=document.createElement('summary');s.textContent=`Historial de entregas (${historicas.length})`;h.append(s);historicas.forEach(e=>dibujar(e,h));seccion.append(h);}
    contenedor.append(seccion);
  }
}
