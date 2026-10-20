import {pedir} from './local.js?v=20261020-60';
import {operacion,esc} from './evidencias.js?v=20261020-60';
import {pedirDatos,confirmar} from './modal.js?v=20261020-60';

export async function configurarOperacion(contenedor) {
  if(contenedor.querySelector('[data-config-operacion]'))return;
  const panel=document.createElement('section');panel.className='panel';panel.dataset.configOperacion='1';
  contenedor.prepend(panel);
  let c=await operacion('/config');
  const input=(label,key,value,tipo='text')=>`<label class="campo"><span>${esc(label)}</span><input data-pref="${key}" type="${tipo}" value="${esc(value)}"></label>`;
  function pintar() {
    panel.innerHTML=`<h2>Operación · configuración ADMIN</h2><p class="mini">Recepción, repositorios y estaciones de impresión. No requiere editar código.</p>
      <p data-estado role="status"></p><details><summary>Protocolo fotográfico</summary><div class="rejilla">${[
        ['Exteriores mínimas recomendadas','exterioresMin'],['Objetivo de exteriores','exterioresObjetivo'],
        ['Packing list inicial','packingMin'],['Bulto abierto con lista visible','abiertosMin'],['Panorámicas mínimas recomendadas','panoramicasMin']
      ].map(([l,k])=>input(l,k,c.evidencias[k],'number')).join('')}</div>
      <label><input type="checkbox" data-bloquear ${c.evidencias.bloquear?'checked':''}> Exigir las recomendaciones antes de cargar packing list</label>
      <p class="mini">Desactivado: se puede continuar con fotos pendientes, como en la operación actual.</p></details>
      <details><summary>Actualización automática del catálogo</summary><label><input type="checkbox" data-activo ${c.catalogo.activo?'checked':''}> Activar sincronización</label>
      <div class="rejilla">${input('Horas del día, separadas por coma','horas',c.catalogo.horas.join(','))}${input('Zona horaria','zona',c.catalogo.zona)}</div>
      <button data-turnos class="b-sec">Ver últimas ejecuciones</button><pre data-ejecuciones class="mini"></pre></details>
      <details><summary>Remitente de informes</summary>
      ${input('Responsable de Drive y envíos anteriores','correoResponsable',c.correo.responsable,'email')}
      <p class="mini">Este respaldo no cambia la identidad de los nuevos envíos. Cada supervisor autoriza su propio correo en Mi cuenta. Editar esta dirección no cambia la cuenta que ejecuta Google.</p>
      <label><input type="checkbox" data-correo-personal ${c.correo.permitirPersonal?'checked':''}> Habilitar envío desde la cuenta propia autorizada de cada supervisor</label></details>
      <details><summary>Repositorios de Drive por cliente y marca</summary><p class="mini">Carpeta general o una por cliente/marca. El supervisor autoriza su acceso mediante el puente Google existente. <a target="_blank" rel="noopener" href="https://github.com/brantos102/IV_ITSANET/blob/desarrollo-local/docs/INGRESO_EVIDENCIAS_E_IMPRESION.md">Guía de configuración y pruebas</a></p>
      <div data-repos>${c.repositorios.map(r=>`<article class="unidad-logistica"><b>${esc(r.nombre)}</b><span>${esc(r.cliente || 'Todos los clientes')} · ${esc(r.marca || 'Todas las marcas')}</span><span class="mini">${esc(r.carpetaId)} · ${r.activo?'Activo':'Inactivo'}</span><button data-editar-repo="${r.id}" class="b-sec">Editar</button><button data-probar-repo="${r.id}" class="b-sec">Verificar acceso</button><button data-quitar-repo="${r.id}" class="b-peligro">Quitar configuración</button></article>`).join('')}</div><button data-nuevo-repo class="b-sec">＋ Repositorio Drive</button></details>
      <details><summary>Puentes de impresión y Zebra de red</summary><p class="mini">Cada PC consulta su cola. IP o dominio de la impresora y puerto ZPL, normalmente 9100. No necesita un servicio HTTP en la PC ni controlador en el móvil.</p>
      <div data-estaciones>${c.impresoras.map(p=>`<article class="unidad-logistica"><b>${esc(p.nombre)}</b><span>${esc(p.equipo || 'Equipo por configurar')} → ${esc(p.host)}:${p.puerto}</span><span>${p.tokenConfigurado?'Agente autorizado':'Falta token'} · ${p.activo?'Activo':'Inactivo'}</span><button data-editar-estacion="${p.id}" class="b-sec">Editar</button><button data-token="${p.id}" class="b-sec">Generar configuración del agente</button></article>`).join('')}</div>
      <button data-nueva-estacion class="b-sec">＋ Estación de impresión</button><div class="rejilla">${input('Máximo de copias por solicitud','maxCopias',c.maxCopias,'number')}</div></details>
      <details><summary>Uso de almacenamiento</summary><p>Las fotos permanecen temporalmente en disco hasta confirmarse en Drive. Las instantáneas se comprimen sin eliminar el historial.</p><button class="b-sec" data-ver-almacenamiento>Consultar uso</button><button class="b-sec" data-compactar>Optimizar instantáneas anteriores · lote de 20</button><p data-almacenamiento role="status"></p></details><div class="acciones"><button data-guardar class="b-primario">Guardar configuración operativa</button></div>`;
  }
  pintar();
  const $=s=>panel.querySelector(s);
  function leer() {
    for(const k of Object.keys(c.evidencias))if(k!=='bloquear')c.evidencias[k]=Number($(`[data-pref="${k}"]`).value);
    c.evidencias.bloquear=$('[data-bloquear]').checked;
    c.catalogo={activo:$('[data-activo]').checked,horas:$('[data-pref="horas"]').value.split(',').map(v=>Number(v.trim())),zona:$('[data-pref="zona"]').value};
    c.maxCopias=Number($('[data-pref="maxCopias"]').value);
    c.correo={responsable:$('[data-pref="correoResponsable"]').value.trim(),permitirPersonal:$('[data-correo-personal]').checked};
  }
  async function guardar(){leer();c=await operacion('/config',{metodo:'PUT',cuerpo:c});pintar();$('[data-estado]').textContent='Configuración guardada.';}
  const registro=(lista,valor)=>{const i=lista.findIndex(r=>r.id===valor.id);if(i<0)lista.push(valor);else lista[i]=valor;};
  panel.addEventListener('click',async ev=>{
    const b=ev.target.closest('button');if(!b)return;
    if(b.matches('[data-ver-almacenamiento],[data-compactar]')){b.disabled=true;try{const r=b.hasAttribute('data-compactar')?await operacion('/almacenamiento/compactar',{cuerpo:{}}):await operacion('/almacenamiento');$('[data-almacenamiento]').textContent=r.mensaje?`${r.mensaje} ${r.compactadas} entregas · ${r.bytesAntes} → ${r.bytesDespues} bytes`:`Instantáneas: ${r.bytesInstantaneas} bytes · ${r.fotosPendientes} fotos pendientes (${r.bytesFotosPendientes} bytes temporales).`;}catch(e){$('[data-almacenamiento]').textContent=e.message;}finally{b.disabled=false;}return;}
    try{
      if(b.hasAttribute('data-guardar')){await guardar();return;}
      if(b.hasAttribute('data-turnos')){const r=await operacion('/catalogo/ejecuciones');$('[data-ejecuciones]').textContent=r.map(t=>`${t.turno} · ${t.estado} · ${t.productos || 0} productos · ${t.clientesConError || 0} clientes pendientes`).join('\n') || 'No hay ejecuciones registradas.';return;}
      if(b.dataset.quitarRepo){if(!await confirmar({titulo:'¿Quitar este repositorio?',texto:'Se retira su configuración. Las fotos existentes en Drive permanecen.',aceptar:'Quitar'}))return;leer();c.repositorios=c.repositorios.filter(r=>r.id!==b.dataset.quitarRepo);pintar();return;}
      if(b.dataset.probarRepo){const r=c.repositorios.find(r=>r.id===b.dataset.probarRepo);
        const s=await pedirDatos({titulo:'Comprobar repositorio',campos:[{clave:'supervisor',etiqueta:'Correo del supervisor con puente autorizado',valor:r.supervisor || '',obligatorio:true}]});
        if(!s)return;await guardar();const resultado=await operacion('/repositorios/'+r.id+'/probar',{cuerpo:s});
        $('[data-estado]').textContent=`Acceso confirmado: ${resultado.nombre} · ${resultado.remitente}. La subida completa se comprueba con evidencia de prueba.`;return;}
      if(b.hasAttribute('data-nuevo-repo') || b.dataset.editarRepo){
        const r=c.repositorios.find(r=>r.id===b.dataset.editarRepo) || {};
        const v=await pedirDatos({titulo:'Repositorio Drive',campos:[
          {clave:'id',etiqueta:'Identificador único',valor:r.id || '',obligatorio:true},
          {clave:'nombre',etiqueta:'Nombre visible',valor:r.nombre || '',obligatorio:true},
          {clave:'carpetaId',etiqueta:'Enlace o ID de la carpeta Drive',valor:r.carpetaId || '',obligatorio:true},
          {clave:'cliente',etiqueta:'Cliente (vacío: todos)',valor:r.cliente || ''},
          {clave:'marca',etiqueta:'Marca (vacío: todas)',valor:r.marca || ''},
          {clave:'supervisor',etiqueta:'Correo del supervisor de referencia',valor:r.supervisor || ''},
          {clave:'activo',etiqueta:'Activo',tipo:'interruptor',valor:r.activo!==false}]});
        if(!v)return;leer();if(r.id && v.id!==r.id)c.repositorios=c.repositorios.filter(p=>p.id!==r.id);
        registro(c.repositorios,v);pintar();return;
      }
      if(b.hasAttribute('data-nueva-estacion') || b.dataset.editarEstacion){
        const p=c.impresoras.find(p=>p.id===b.dataset.editarEstacion) || {};
        const v=await pedirDatos({titulo:'Estación de impresión',campos:[
          {clave:'id',etiqueta:'Identificador único',valor:p.id || '',obligatorio:true},
          {clave:'nombre',etiqueta:'Nombre visible al operario',valor:p.nombre || '',obligatorio:true},
          {clave:'equipo',etiqueta:'Nombre o dominio/IP de la computadora puente',valor:p.equipo || ''},
          {clave:'host',etiqueta:'IP o dominio de la impresora Zebra',valor:p.host || '',obligatorio:true},
          {clave:'puerto',etiqueta:'Puerto ZPL',valor:p.puerto || 9100,tipo:'number',obligatorio:true},
          {clave:'activo',etiqueta:'Activo',tipo:'interruptor',valor:p.activo!==false}]});
        if(!v)return;leer();v.puerto=Number(v.puerto);if(p.id && p.id!==v.id)c.impresoras=c.impresoras.filter(r=>r.id!==p.id);
        registro(c.impresoras,{...p,...v});pintar();return;
      }
      if(b.dataset.token){
        const p=c.impresoras.find(p=>p.id===b.dataset.token);
        if(!await confirmar({titulo:'Generar acceso para el agente',texto:'La nueva clave sustituirá la anterior de esta estación. Se descargará un archivo privado para la PC puente.',aceptar:'Generar archivo'}))return;
        const v=await pedirDatos({titulo:'Dirección del servidor para el agente',texto:'Para el agente del mismo Docker local usa http://app:3002. En otra PC usa la dirección real del servidor accesible desde esa PC.',campos:[{clave:'servidor',etiqueta:'URL del servidor',valor:location.origin,obligatorio:true}]});
        if(!v)return;await guardar();
        const t=await pedir('/estaciones/'+p.id+'/token',{base:'/api/impresion',cuerpo:{}});
        const json={servidor:v.servidor,estacion:p.id,equipo:p.equipo,token:t.token};
        const url=URL.createObjectURL(new Blob([JSON.stringify(json,null,2)],{type:'application/json'}));
        const a=document.createElement('a');a.href=url;a.download='puente-'+p.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),4000);
        c=await operacion('/config');pintar();$('[data-estado]').textContent='Archivo privado generado. Instálalo únicamente en la PC puente; no lo subas a GitHub.';
      }
    }catch(e){$('[data-estado]').textContent=e.message;}
  });
}
