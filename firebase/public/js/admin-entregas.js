import {pedir} from './local.js?v=20261017-39';
import {pedirDatos,confirmar} from './modal.js?v=20261017-39';

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fecha = e => new Date(e.creadoEn).toLocaleString('es-EC', {timeZone:'America/Guayaquil'});
const referencia = e => e.informe?.numero ? 'R'+String(e.informe.numero).padStart(4,'0') : e.id.slice(0,8);
const enlace = (url, titulo) => /^https:\/\/(drive|docs)\.google\.com\//.test(url || '')
  ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(titulo)}</a>` : '';
const operacion = (ruta, opciones={}) => pedir(ruta, {...opciones, base:'/api/operacion'});

export async function revisarDrive(codigo, aviso, operativo=false) {
  const d = document.createElement('dialog'); d.className='modal';
  d.innerHTML=`<h3>Fotos y carpetas · ${esc(codigo)}</h3><div data-estado role="status">Consultando fotos…</div>
    <p data-resultado role="status"></p><div class="modal-acciones"><button class="b-sec" data-actualizar>Actualizar</button>
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
      ultima.estado==='ENTREGADA'?'Entrega confirmada.':'Sin envío activo. Los envíos anulados no se enviarán.';seccion.append(resumen);
    boton(seccion,'Revisar Drive y fotos',()=>revisarDrive(codigo,aviso,operativo));
    const dibujar=(e,padre)=>{
      const fila=document.createElement('article');fila.style.marginBlock='16px';
      const p=document.createElement('p');p.textContent=`${referencia(e)} · ${fecha(e)} · ${e.estado} · De: ${e.remitente || e.supervisor} · Para: ${e.destinatarios || 'Sin correo'}`;fila.append(p);
      const m=document.createElement('p');m.className='mini';m.textContent=(e.mensaje || '')+(e.ayuda?' '+e.ayuda:'')+(e.intentos?' · Intentos: '+e.intentos:'')+(e.proximoIntento&&e.estado==='PENDIENTE'?' · Próximo intento: '+new Date(e.proximoIntento).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}):'');fila.append(m);
      const urls=document.createElement('div');urls.innerHTML=enlace(e.resultado?.carpeta,'Abrir Drive')+' '+enlace(e.resultado?.sheet,'Abrir Sheets');fila.append(urls);
      if(['PENDIENTE','REVISION'].includes(e.estado)){
        boton(fila,'Anular este envío',async()=>{
          const datos=await pedirDatos({titulo:`Anular envío ${referencia(e)}`,texto:`${esc(codigo)} · ${esc(fecha(e))}. Se conservan archivos, conteos y auditoría.`,
            campos:[{clave:'motivo',etiqueta:'Motivo de anulación (mínimo 10 caracteres)',obligatorio:true}],aceptar:'Anular este envío'});
          if(!datos)return;await pedir('/entregas/'+e.id+'/cancelar',{cuerpo:datos});aviso('Envío anulado; archivos conservados.','ok');await actualizar();
        },'b-peligro');
      }
      if(e.errorAnterior && ['CANCELADA','ENTREGADA'].includes(e.estado)){
        const h=document.createElement('details'),s=document.createElement('summary');s.textContent='Diagnóstico anterior (historial)';h.append(s);
        const t=document.createElement('p');t.textContent=e.errorAnterior;h.append(t);fila.append(h);
      }
      padre.append(fila);
    };
    activas.forEach(e=>dibujar(e,seccion));
    if(['PENDIENTE','CANCELADA','REVISION'].includes(ultima.estado)){
      if(ultima.confirmacionDisponible){const listo=document.createElement('p');listo.className='msg ok';listo.textContent='Tu conexión está verificada. Los documentos finales esperan tu revisión y confirmación; todavía no se enviaron.';seccion.append(listo);}
      boton(seccion,ultima.confirmacionDisponible?'Conexión verificada · revisar y confirmar envío':'Revisar y confirmar envío desde mi correo',async()=>{
        const v=await pedir('/entregas/'+ultima.id+'/solicitar');
        if(!v.responsable.disponible)throw new Error('Autoriza tu propia conexión en Mi cuenta y correo; después no se solicita una clave por envío.');
        const datos=await pedirDatos({titulo:`Confirmar envío de documentos finales · ${referencia(ultima)}`,texto:`<p>${esc(codigo)} · ${esc(fecha(ultima))}</p><p>De: <b>${esc(v.responsable.correo)}</b><br>Para: ${esc(ultima.destinatarios || 'Sin correo')}</p><p>Se utilizará el mismo informe archivado: ${v.archivos.map(esc).join(', ')}. ${v.sustituye.length} entrega(s) anterior(es) pendiente(s) serán anuladas.</p><p>Comprueba Enviados en las cuentas anteriores y en la responsable para evitar un envío duplicado. Tu cuenta y el puente se acaban de verificar. Al confirmar se programará este envío; espera después la confirmación de Google.</p>`,
          campos:[{clave:'destinatarios',etiqueta:'Enviar documentos a · correos separados por coma',valor:ultima.destinatarios||'',obligatorio:true},{clave:'motivo',etiqueta:'Motivo de recuperación (10–300 caracteres)',obligatorio:true},
            {clave:'confirmarNoEnviado',etiqueta:'Revisé Enviados: este informe todavía no fue enviado',tipo:'interruptor',valor:false}],aceptar:'Confirmar envío de documentos finales'});
        if(!datos)return;await pedir('/entregas/'+ultima.id+'/solicitar',{cuerpo:{...datos,remitenteConfirmado:v.responsable.correo}});
        aviso('El mismo informe quedó programado con tu cuenta autorizada. Espera la confirmación de Google.','info','Envío pendiente de confirmación');await actualizar();
      },'b-primario');
    }
    const historicas=grupo.filter(e=>!activas.includes(e));
    if(historicas.length){const h=document.createElement('details'),s=document.createElement('summary');s.textContent=`Historial de entregas (${historicas.length})`;h.append(s);historicas.forEach(e=>dibujar(e,h));seccion.append(h);}
    contenedor.append(seccion);
  }
}
