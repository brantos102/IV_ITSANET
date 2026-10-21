import {pedir} from './local.js?v=20261021-61';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export async function editarContenedores(codigo){
 const ruta='/recepciones/'+encodeURIComponent(codigo)+'/contenedores';
 const v=await pedir(ruta,{base:'/api/operacion'}),d=document.createElement('dialog');d.className='modal-operativa contenedores-dialogo';
 d.innerHTML='<header class="acciones"><h2>Contenedores, bultos y posición final</h2><button data-cerrar class="b-sec">Cerrar</button></header><p>Registro opcional del supervisor. Distribuye los bultos recibidos sin modificar las cantidades del packing list. Se incluirá en el correo y en los nuevos archivos del embarque correspondiente.</p><p class="mini">El rango E01–E60 equivale a 60 bultos. Los rangos no pueden superponerse. Una posición puede ser CALLEKL u otra ubicación de piso.</p><div data-filas></div><button data-agregar class="b-sec">Añadir contenedor recibido</button><p data-estado role="status"></p><footer class="acciones"><button data-guardar class="b-primario">Guardar distribución</button></footer>';
 document.body.append(d);d.showModal();const $=s=>d.querySelector(s);let ocupado=false;
 function agregar(f={}){
  const fila=document.createElement('fieldset');fila.className='contenedor-fila';
  fila.innerHTML=`<legend>Contenedor recibido</legend><div class="rejilla">${[['numero','Número de contenedor · 4 letras y 7 dígitos'],['desde','Desde el bulto · E01'],['hasta','Hasta el bulto · E60'],['posicion','Posición final · CALLEKL']].map(([k,t])=>`<label class="campo"><span>${t}</span><input data-${k} value="${esc(f[k])}" maxlength="${k==='posicion'?120:20}" ${k==='numero'?'list="contenedores-detectados"':''}></label>`).join('')}</div><p class="mini" data-total></p><div data-embarques><span>Embarques correspondientes</span>${v.embarques.map((b,i)=>`<label class="correo-opcion"><input type="checkbox" data-embarque="${esc(b)}" ${(f.embarques||[]).includes(b)?'checked':''}>${esc(b)}</label>`).join('')}</div><button class="b-sec" data-quitar>Quitar de la distribución</button>`;
  const total=()=>{const a=fila.querySelector('[data-desde]').value.match(/^([a-z]*)(\d+)$/i),b=fila.querySelector('[data-hasta]').value.match(/^([a-z]*)(\d+)$/i);fila.querySelector('[data-total]').textContent=a&&b&&a[1].toUpperCase()===b[1].toUpperCase()&&+b[2]>=+a[2]?'Total del rango: '+(+b[2]-+a[2]+1)+' bultos':'Completa el rango si deseas calcular el total de bultos.';};fila.addEventListener('input',total);total();
  fila.querySelector('[data-numero]').onchange=()=>{const n=fila.querySelector('[data-numero]').value.trim().toUpperCase(),encontrado=v.detectados.find(c=>c.numero===n);if(encontrado)fila.querySelectorAll('[data-embarque]').forEach(e=>e.checked=encontrado.embarques.includes(e.dataset.embarque));};
  fila.querySelector('[data-quitar]').onclick=()=>{if(!ocupado)fila.remove();};$('[data-filas]').append(fila);
 }
 const lista=document.createElement('datalist');lista.id='contenedores-detectados';lista.innerHTML=v.detectados.map(c=>`<option value="${esc(c.numero)}">${esc(c.embarques.join(', '))}</option>`).join('');d.append(lista);
 for(const f of v.filas)agregar(f);
 $('[data-agregar]').onclick=()=>{if(!ocupado)agregar({embarques:v.embarques.length===1?v.embarques:[]});};
 $('[data-guardar]').onclick=async()=>{if(ocupado)return;ocupado=true;const controles=[...d.querySelectorAll('button,input')];controles.forEach(e=>e.disabled=true);try{
  const filas=[...d.querySelectorAll('.contenedor-fila')].map(f=>({...Object.fromEntries(['numero','desde','hasta','posicion'].map(k=>[k,f.querySelector('[data-'+k+']').value])),embarques:[...f.querySelectorAll('[data-embarque]:checked')].map(e=>e.dataset.embarque)}));
  await pedir(ruta,{base:'/api/operacion',metodo:'PUT',cuerpo:{version:v.version,filas}});d.close('guardado');
 }catch(e){$('[data-estado]').textContent=e.message;}finally{ocupado=false;controles.forEach(e=>e.disabled=false);}};
 $('[data-cerrar]').onclick=()=>{if(!ocupado)d.close();};d.oncancel=e=>{if(ocupado)e.preventDefault();};
 return new Promise(resolve=>d.addEventListener('close',()=>{resolve(d.returnValue==='guardado');d.remove();},{once:true}));
}
