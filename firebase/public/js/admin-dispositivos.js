import {pedir} from './local.js?v=20261111-76';
import {esc} from './evidencias.js?v=20261111-76';
import {pedirDatos,confirmar} from './modal.js?v=20261111-76';

export async function configurarDispositivos(raiz){
 if(raiz.querySelector('[data-equipos-autorizados]'))return;
 const s=document.createElement('section');s.className='panel';s.dataset.areaAdmin='equipo';s.dataset.equiposAutorizados='1';
 s.innerHTML='<h2>Equipos autorizados por usuario</h2><p>Un móvil y una laptop por persona. Con el control activo, cada cuenta tiene una sola sesión; entrar en otro equipo autorizado cierra la anterior.</p><p data-politica></p><div class="acciones"><button data-actualizar class="b-sec">Actualizar equipos</button><button data-registrar class="b-sec">Registrar este equipo de ADMIN</button><button data-activar class="b-primario">Activar control</button></div><p data-estado role="status"></p><div data-equipos></div>';
 const enlace=document.createElement('a');enlace.className='b-sec';enlace.href='./equipo.html';enlace.target='_blank';enlace.rel='noopener';enlace.textContent='Abrir solicitud para el propietario del equipo';s.querySelector('.acciones').append(enlace);
 raiz.append(s);const $=q=>s.querySelector(q);let datos,ocupado=false;
 async function cargar(){datos=await pedir('/dispositivos/admin',{base:'/api/auth'});$('[data-politica]').textContent=datos.politica.activo?'Control activo. Solo equipos aprobados; una sesión por cuenta.':'Preparación: el acceso actual sigue disponible. Registra y aprueba los equipos antes de activar.';$('[data-activar]').textContent=datos.politica.activo?'Desactivar control':'Activar control';
  $('[data-equipos]').innerHTML=datos.equipos.map(d=>`<article class="unidad-logistica"><b>${esc(d.nombreUsuario)} · ${esc(d.usuario)}</b><span>${esc(d.tipo)} · ${esc(d.nombre)} · ${esc(d.estado)}</span><span>Solicitud ${esc(d.id.slice(0,8).toUpperCase())}</span>${d.estado==='PENDIENTE'?`<button class="b-primario" data-aprobar="${d.id}">Aprobar presencialmente</button>`:''}${d.estado!=='REVOCADO'?`<button class="b-sec" data-revocar="${d.id}">Revocar</button>`:''}</article>`).join('')||'<p>No hay equipos registrados.</p>';
 }
 s.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b||ocupado)return;ocupado=true;b.disabled=true;
  try{
   if(b.hasAttribute('data-registrar')){
    const v=await pedirDatos({titulo:'Registrar el equipo actual de ADMIN',texto:'Esta solicitud corresponde al navegador que estás utilizando. Después aprueba su código en esta misma sección.',campos:[{clave:'usuario',etiqueta:'Usuario de ADMIN',obligatorio:true},{clave:'pin',etiqueta:'Contraseña del aplicativo',tipo:'password',obligatorio:true},{clave:'tipo',etiqueta:'Tipo de equipo',tipo:'lista',valor:'LAPTOP',opciones:[{valor:'MOVIL',titulo:'Móvil / handheld'},{valor:'LAPTOP',titulo:'Laptop'}]},{clave:'nombre',etiqueta:'Nombre del equipo',obligatorio:true}]});
    if(v){const r=await pedir('/dispositivos/solicitar',{base:'/api/auth',cuerpo:v});$('[data-estado]').textContent=r.mensaje;}
   }else if(b.dataset.aprobar){
    const d=datos.equipos.find(x=>x.id===b.dataset.aprobar),actual=datos.equipos.find(x=>x.operadorId===d.operadorId&&x.tipo===d.tipo&&x.estado==='AUTORIZADO');
    const texto=`Comprueba presencialmente a ${d.nombreUsuario}, el equipo «${d.nombre}» (${d.tipo}) y el código ${d.id.slice(0,8).toUpperCase()}.`+(actual?` Reemplazará a «${actual.nombre}» y cerrará sus sesiones.`:'');
    if(await confirmar({titulo:actual?'Confirmar reemplazo de equipo':'Aprobar equipo verificado',texto,aceptar:actual?'Verificado · reemplazar':'Verificado · aprobar'})){await pedir('/dispositivos/admin/'+d.id+'/aprobar',{base:'/api/auth',cuerpo:{presencial:true,...(actual?{reemplaza:actual.id}:{})}});$('[data-estado]').textContent='Equipo autorizado. Su propietario puede entrar desde ese navegador.';}
   }else if(b.dataset.revocar){
    const v=await pedirDatos({titulo:'Revocar autorización del equipo',campos:[{clave:'motivo',etiqueta:'Motivo de la revocación',obligatorio:true}]});
    if(v){await pedir('/dispositivos/admin/'+b.dataset.revocar+'/revocar',{base:'/api/auth',cuerpo:v});$('[data-estado]').textContent='Equipo revocado; sus sesiones se cerraron.';}
   }else if(b.hasAttribute('data-activar')){
    if(datos.politica.activo){const v=await pedirDatos({titulo:'Desactivar el control de equipos',texto:'Los usuarios volverán a poder entrar sin comprobar un equipo registrado.',campos:[{clave:'motivo',etiqueta:'Motivo',obligatorio:true}]});if(v)await pedir('/dispositivos/admin/politica',{base:'/api/auth',metodo:'PUT',cuerpo:{activo:false,...v}});}
    else if(await confirmar({titulo:'Activar equipos autorizados',texto:'Comprueba que los usuarios de la operación tengan sus equipos aprobados. Las sesiones anteriores deberán volver a entrar; los pendientes locales permanecen en su equipo y su cuenta. Tu equipo de ADMIN debe estar aprobado.',aceptar:'Activar control'}))await pedir('/dispositivos/admin/politica',{base:'/api/auth',metodo:'PUT',cuerpo:{activo:true}});
   }
   await cargar();
  }catch(err){$('[data-estado]').textContent=err.message;}
  finally{ocupado=false;b.disabled=false;}
 });
 try{await cargar();}catch(e){$('[data-estado]').textContent=e.message;}
}
