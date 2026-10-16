import {pedir} from './local.js?v=20261016-31';
import {CAMPOS_SALIDA,letra} from './admin-politicas.js?v=20261016-31';
const api=(r,o={})=>pedir(r,{...o,base:'/api/operacion'});
export async function configurarColumnasInforme(codigo){
 const ruta='/recepciones/'+encodeURIComponent(codigo),meta=await api(ruta+'/informe-metadatos');
 const ds=document.createElement('dialog');ds.className='modal-operativa';ds.style.cssText='max-width:720px;width:94vw;max-height:85dvh;overflow:auto';
 const h=document.createElement('h3');h.textContent='Columnas del informe';ds.append(h);
 const ayuda=document.createElement('p');ayuda.className='mini';ayuda.textContent='Cada packing list conserva sus filas y encabezados. Selecciona sus columnas para cantidades, incidencias, barras y carpeta Drive. Vacío conserva el dato original.';ds.append(ayuda);
 const selector=document.createElement('select');for(const origen of Object.keys(meta.formatos)){const o=document.createElement('option');o.value=origen;o.textContent=origen;selector.append(o);}ds.append(selector);
 const campos=document.createElement('div');campos.className='rejilla';ds.append(campos);
 const pintar=()=>{campos.replaceChildren();const f=meta.formatos[selector.value];if(!f)return;
  const actuales=f.salida||{...f.columnas,...meta.columnas};for(const [k,t] of Object.entries(CAMPOS_SALIDA)){const l=document.createElement('label');l.className='campo';const texto=document.createElement('span');texto.textContent=t;const s=document.createElement('select');s.dataset.campo=k;s.append(new Option('Sin asignar',''));f.encabezados.forEach((enc,i)=>s.append(new Option(letra(i)+' · '+enc,String(i))));s.value=actuales[k]===undefined?'':String(actuales[k]);l.append(texto,s);campos.append(l);}
 };selector.onchange=pintar;pintar();
 const msg=document.createElement('p');msg.className='mini';msg.setAttribute('role','status');ds.append(msg);
 const guardar=document.createElement('button');guardar.className='b-primario';guardar.textContent='Guardar columnas de esta lista';
 const cerrar=document.createElement('button');cerrar.className='b-sec';cerrar.textContent='Cerrar';ds.append(guardar,cerrar);document.body.append(ds);ds.showModal();let cambio=false;
 guardar.onclick=async()=>{guardar.disabled=true;try{const columnas={};for(const s of campos.querySelectorAll('select'))if(s.value!=='')columnas[s.dataset.campo]=Number(s.value);
  await api(ruta+'/columnas-informe',{metodo:'PUT',cuerpo:{origen:selector.value,columnas,version:meta.versionFormatos}});const nuevo=await api(ruta+'/informe-metadatos');Object.assign(meta,nuevo);cambio=true;msg.textContent='Columnas guardadas. Puedes configurar otra lista o cerrar.';
 }catch(e){msg.textContent=e.message;}finally{guardar.disabled=false;}};
 cerrar.onclick=()=>ds.close();return new Promise(resolve=>ds.addEventListener('close',()=>{ds.remove();resolve(cambio);},{once:true}));
}
