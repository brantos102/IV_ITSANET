import {destinosInforme,columnasSegurasInforme} from './datos.js?v=20261017-39';
import {pedir} from './local.js?v=20261017-39';
import {CAMPOS_SALIDA,letra} from './admin-politicas.js?v=20261017-39';
import {reunirInforme,previsualizarLista} from './informe.js?v=20261017-39';
const api=(r,o={})=>pedir(r,{...o,base:'/api/operacion'});
export async function configurarColumnasInforme(codigo){
 const ruta='/recepciones/'+encodeURIComponent(codigo),meta=await api(ruta+'/informe-metadatos');
 const ds=document.createElement('dialog');ds.className='modal-operativa';ds.style.cssText='max-width:1100px;width:94vw;max-height:90dvh;overflow:auto';
 ds.innerHTML='<h3>Columnas del informe</h3><p class="mini">Selecciona las columnas de cada packing list y revisa debajo cómo quedarán sus datos. Solo se rellenan columnas de resultado. SKU, descripción, cantidades y demás datos de origen están protegidos. Las columnas nuevas se añaden al final. Sin asignar conserva la celda original. Esta vista no envía correo ni genera una versión.</p><label class="campo"><span>Packing list · archivo independiente</span><select data-lista></select></label><div data-campos class="rejilla"></div><h3>Así quedará el archivo</h3><div class="acciones"><label class="campo"><span>Presentación que deseas revisar</span><select data-presentacion><option value="original">Formato original</option><option value="ampliado">Con columnas adicionales</option></select></label><button class="b-sec" data-actualizar>Actualizar registros</button></div><p class="mini" data-estado-vista role="status">Cargando registros actuales…</p><div data-tabla style="max-height:360px;overflow:auto" tabindex="0" aria-label="Vista previa del archivo Excel"></div><div class="acciones"><button data-anterior class="b-sec">Anterior</button><button data-siguiente class="b-sec">Siguiente</button></div><p data-mensaje role="status" class="mini"></p><div class="acciones"><button data-guardar class="b-primario">Guardar columnas de esta lista</button><button data-cerrar class="b-sec">Cerrar</button></div>';
 const $=s=>ds.querySelector(s),selector=$('[data-lista]'),campos=$('[data-campos]');
 for(const origen of Object.keys(meta.formatos)){const o=new Option(origen,origen);selector.append(o);}
 document.body.append(ds);ds.showModal();
 let cambio=false,datos=null,offset=0,cargando=false,guardando=false;
 const borradores=new Map(),columnas=()=>Object.fromEntries([...campos.querySelectorAll('select')].filter(s=>s.value!=='').map(s=>[s.dataset.campo,Number(s.value)]));
 function previa(){
  const tabla=$('[data-tabla]'),estado=$('[data-estado-vista]');tabla.replaceChildren();
  $('[data-anterior]').hidden=$('[data-siguiente]').hidden=true;
  const cols=columnas(),duplicado=new Set(Object.values(cols)).size!==Object.values(cols).length;
  $('[data-guardar]').disabled=guardando||duplicado||!selector.value;
  if(duplicado){estado.textContent='Hay dos campos asignados a la misma columna. Corrige la selección para revisar y guardar.';return;}
  if(!datos){estado.textContent=cargando?'Cargando registros actuales…':'No se cargaron los registros. Pulsa Actualizar registros; no se mostrarán ejemplos en lugar de tus datos.';return;}
  const origen=selector.value,f=meta.formatos[origen];if(!f){estado.textContent='Esta recepción todavía no tiene un packing list para configurar.';return;}
  try{
   const lista=datos.porOrigen.find(l=>l.origen===origen)||{detalle:[]};
   // f.salida es una selección completa: los campos que se quitaron no se reactivan.
   const exacta=previsualizarLista({...lista,formato:f},{...Object.fromEntries(Object.entries(f.columnas||{}).filter(([k])=>!Object.hasOwn(CAMPOS_SALIDA,k))),...cols},{ampliado:$('[data-presentacion]').value==='ampliado',offset});
   estado.textContent=exacta.ejemplo?'Ejemplo ficticio: esta lista no tiene filas. Estos datos no se guardarán ni se enviarán.':`${origen} · Registros reales ${offset+1}–${Math.min(offset+12,exacta.total)} de ${exacta.total}. Se muestran como se exportarán con los datos actuales.`;
   const t=document.createElement('table'),head=t.createTHead().insertRow();
   for(const texto of ['Fila Excel',...exacta.encabezados.map((e,i)=>letra(i)+' · '+e)]){const th=document.createElement('th');th.textContent=texto;th.scope='col';th.style.cssText='position:sticky;top:0;background:var(--panel,#fff);min-width:110px';head.append(th);}
   const body=t.createTBody();
   for(const f of exacta.filas){const tr=body.insertRow();tr.insertCell().textContent=String(f.numero);
    for(const c of f.celdas){const td=tr.insertCell();td.style.cssText='white-space:normal;min-width:110px;max-width:300px;overflow-wrap:anywhere';
     if(/^https:\/\/drive\.google\.com\//.test(c.url)){const a=document.createElement('a');a.href=c.url;a.target='_blank';a.rel='noopener';a.textContent=c.texto;td.append(a);}else td.textContent=c.texto;
     if(c.formula)td.title='Fórmula conservada: ='+c.formula;
    }
   }tabla.append(t);
   $('[data-anterior]').hidden=offset===0;$('[data-siguiente]').hidden=offset+12>=exacta.total;
  }catch(e){estado.textContent=e.message;$('[data-guardar]').disabled=true;}
 }
 function pintar(){campos.replaceChildren();offset=0;const f=meta.formatos[selector.value];if(!f){previa();return;}
  const actuales=columnasSegurasInforme(f,borradores.get(selector.value)||f.salida||{...f.columnas,...meta.columnas});
  for(const [k,t] of Object.entries(CAMPOS_SALIDA)){const l=document.createElement('label');l.className='campo';const texto=document.createElement('span');texto.textContent=t;const s=document.createElement('select');s.dataset.campo=k;s.append(new Option('Sin asignar',''));for(const i of destinosInforme(f,k))s.append(new Option(letra(i)+' · '+f.encabezados[i],String(i)));
   if(s.options.length===1){s.options[0].textContent='Sin columna · se añade al elegir ampliado';}s.value=actuales[k]===undefined?'':String(actuales[k]);l.append(texto,s);campos.append(l);}
  previa();
 }
 campos.onchange=()=>{borradores.set(selector.value,columnas());offset=0;previa();};selector.onchange=pintar;
 $('[data-presentacion]').onchange=()=>{offset=0;previa();};
 $('[data-anterior]').onclick=()=>{offset=Math.max(0,offset-12);previa();};$('[data-siguiente]').onclick=()=>{offset+=12;previa();};
 async function cargar(){if(cargando)return;cargando=true;$('[data-actualizar]').disabled=true;try{
   const recepcion=await pedir(ruta);datos=await reunirInforme(codigo,recepcion);if(ds.open)previa();
  }catch(e){datos=null;$('[data-mensaje]').textContent=e.message;}finally{cargando=false;$('[data-actualizar]').disabled=false;if(ds.open)previa();}}
 $('[data-actualizar]').onclick=cargar;
 $('[data-guardar]').onclick=async()=>{guardando=true;previa();try{
  await api(ruta+'/columnas-informe',{metodo:'PUT',cuerpo:{origen:selector.value,columnas:columnas(),version:meta.versionFormatos}});
  const nuevo=await api(ruta+'/informe-metadatos');Object.assign(meta,nuevo);cambio=true;
  $('[data-mensaje]').textContent='Columnas guardadas. Revisa otra lista o cierra para continuar.';
 }catch(e){$('[data-mensaje]').textContent=e.message;}finally{guardando=false;previa();}};
 $('[data-cerrar]').onclick=()=>ds.close();pintar();cargar();
 return new Promise(resolve=>ds.addEventListener('close',()=>{ds.remove();resolve(cambio);},{once:true}));
}
