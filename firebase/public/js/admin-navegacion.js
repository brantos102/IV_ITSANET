/** Agrupa los formularios existentes: conserva sus IDs, valores y eventos. */
export function organizarAdministracion(raiz){
 if(raiz.querySelector('[data-admin-menu]'))return;
 const menu=document.createElement('nav');menu.className='admin-secciones';menu.dataset.adminMenu='';menu.setAttribute('aria-label','Secciones de administración');
 const areas=[['operacion','Operación diaria','Fotos, catálogo, remitentes e impresión'],['procesos','Procesos y errores','Fotos, correos, intentos y diagnóstico'],['entregas','Entregas','Pendientes, envíos manuales e historial'],['conexiones','Conexiones','Depot, Google y acceso al servidor'],['equipo','Roles y reglas','Permisos, clientes e incidencias'],['formatos','Formatos Depot','Archivos de importación y columnas']];
 const descripcion=document.createElement('p');descripcion.className='guia-modal';descripcion.textContent='Selecciona una sección. Los supervisores realizan la operación; las credenciales y la administración de administradores permanecen en ADMIN.';
 raiz.prepend(menu,descripcion);
 const asignar=(selector,area)=>raiz.querySelectorAll(selector).forEach(p=>p.dataset.areaAdmin=area);
 asignar('[data-config-operacion]','operacion');asignar('[data-config-politicas]','equipo');asignar('#panelIntegraciones','conexiones');asignar('#panelLocal','entregas');
 const formatos=raiz.querySelector('#formatosCsv')?.closest('.panel');if(formatos)formatos.dataset.areaAdmin='formatos';
 const local=raiz.querySelector('#panelLocal'),estado=raiz.querySelector('#estadoLocal');
 if(local&&estado){const catalogo=document.createElement('section');catalogo.className='panel';catalogo.dataset.areaAdmin='operacion';const h=document.createElement('h2');h.textContent='Catálogo de productos';catalogo.append(h);let el=estado;while(el){const sig=el.nextElementSibling;catalogo.append(el);el=sig;}local.after(catalogo);}
 for(const [id,titulo,pista] of areas){const b=document.createElement('button');b.type='button';b.className='admin-seccion';b.dataset.area=id;const t=document.createElement('strong');t.textContent=titulo;const p=document.createElement('span');p.textContent=pista;b.append(t,p);b.onclick=()=>{raiz.querySelectorAll('[data-area-admin]').forEach(p=>p.hidden=p.dataset.areaAdmin!==id);menu.querySelectorAll('button').forEach(e=>e.setAttribute('aria-pressed',String(e===b)));};menu.append(b);}
 menu.querySelector('button').click();
 const ayuda=document.createElement('p');ayuda.className='mini';ayuda.innerHTML='<a href="./manuales/tecnico.html">Manual de conexiones, servicios y estructura del código ↗</a>';menu.after(ayuda);
}
