import {destinosInforme,columnasSegurasInforme} from './datos.js?v=20261023-67';
import {pedir} from './local.js?v=20261023-67';
import {CAMPOS_SALIDA,letra} from './admin-politicas.js?v=20261023-67';
import {reunirInforme,previsualizarLista} from './informe.js?v=20261023-67';
import {tecladoDialogo} from './modal.js?v=20261023-67';
import {columnasDeSalida} from './orden-informe.js?v=20261023-67';
const api=(r,o={})=>pedir(r,{...o,base:'/api/operacion'});
const EJEMPLOS={depot:'ok',marca:'MARCA',cliente:'CLIENTE',fisica:'8',validacion:'Faltante',desface:'-2',pallet:'B01.1-B02',posicion:'A-01-02-1',codigoBarra:'000123456789',cantidadIncidencia:'2',incidencia:'PNC',observacion:'Caja abierta; revisar 2 unidades',evidencia:'Enlace a la carpeta del SKU en Drive'};
const GRUPOS=[['Conteo y ubicación',['fisica','validacion','desface','pallet','posicion']],['Incidencias y observaciones',['cantidadIncidencia','incidencia','observacion']],['Identificación y documentos',['depot','marca','cliente','codigoBarra','evidencia']]];
export async function configurarColumnasInforme(codigo){
 const ruta='/recepciones/'+encodeURIComponent(codigo),meta=await api(ruta+'/informe-metadatos');
 const ds=document.createElement('dialog');ds.className='modal-operativa columnas-dialogo';
 ds.innerHTML=`<header class="modal-cabecera"><div><h2>Prepara las columnas del informe</h2><p class="mini">${codigo.replace(/[&<>"']/g,'')} · Configuración por embarque</p></div><button data-cerrar class="b-sec">Cerrar</button></header>
 <p class="guia-modal">Organiza el informe ampliado sin cambiar el packing list recibido. Marca y Cliente se proponen al inicio. El formato original conserva su orden para cargarlo al sistema.</p><details class="guia-modal"><summary>Cómo se valida la columna OK de Depot · sin hoja MAESTRO</summary><p class="mini" data-nota-depot></p><p class="mini">OK: encontrado para este cliente. N/D: requiere revisar el registro o cliente; lee la observación. PENDIENTE: falta validar el catálogo. INACTIVO: requiere revisión de habilitación. La ausencia en el stock consultado no confirma que el código no exista en el maestro.</p></details>
 <div class="columnas-layout"><section><h3>1. Elige el embarque y los destinos</h3><label class="campo"><span>Embarque · archivo independiente</span><select data-lista></select></label><div data-campos></div></section>
 <section class="columnas-muestra"><div class="acciones"><h3>2. Organiza y revisa el resultado</h3><span class="muestra-badge">VISTA PREVIA</span></div><p class="mini">Las celdas azules son resultados. Enfoca un destino para localizarlo en la muestra. Las letras de los destinos corresponden al archivo original; la muestra usa el orden de exportación.</p>
 <div class="acciones"><label class="campo"><span>Formato de la muestra</span><select data-presentacion><option value="ampliado">Informe ampliado · orden editable</option><option value="original">Packing list · orden original</option></select></label><button class="b-sec" data-actualizar>↻ Actualizar datos</button></div>
 <details data-organizacion open><summary>Orden de las columnas del informe ampliado</summary><p class="mini">Elige una posición o usa las flechas. Se mueve la columna completa; no se elimina ningún dato ni fila. Guarda esta configuración por embarque.</p><div class="acciones"><button type="button" class="b-sec" data-identificacion>Marca y Cliente al inicio</button><button type="button" class="b-sec" data-orden-original>Orden del packing list</button></div><ol data-orden class="orden-columnas" aria-label="Orden de exportación de las columnas"></ol></details>
 <p class="mini" data-estado-vista role="status">Cargando datos de la recepción…</p><div data-tabla class="columnas-tabla" tabindex="0" aria-label="Vista previa del archivo Excel"></div><div class="acciones"><button data-anterior class="b-sec">Anterior</button><button data-siguiente class="b-sec">Siguiente</button></div></section></div>
 <footer class="modal-pie"><p data-mensaje role="status" class="mini">Tab: siguiente campo · Enter: elegir · Ctrl+Enter: guardar. La muestra no genera archivos ni envía correos.</p><button data-guardar class="b-primario">Guardar columnas y orden de este embarque</button></footer>`;
 const $=s=>ds.querySelector(s),selector=$('[data-lista]'),campos=$('[data-campos]');
 const validacion=meta.validacionDepot;
 $('[data-nota-depot]').textContent=validacion?validacion.notaMaestro+' '+validacion.metodo+' Actualización: '+(validacion.fechaActualizacion||validacion.actualizadoEn||'sin confirmar'):'Actualiza el servidor para disponer de la fuente y el estado de validación de Depot.';
 for(const origen of Object.keys(meta.formatos))selector.append(new Option(origen,origen));
 document.body.append(ds);ds.showModal();
 let cambio=false,datos=null,offset=0,cargando=false,guardando=false,activo='';
 const borradores=new Map(),ordenes=new Map(),columnas=()=>Object.fromEntries([...campos.querySelectorAll('select')].filter(s=>s.value!=='').map(s=>[s.dataset.campo,Number(s.value)]));
 const formatoActual=()=>{const f=meta.formatos[selector.value];return {...f,ordenSalida:ordenes.has(selector.value)?ordenes.get(selector.value):f?.ordenSalida,columnas:{...Object.fromEntries(Object.entries(f?.columnas||{}).filter(([k])=>!Object.hasOwn(CAMPOS_SALIDA,k))),...columnas()}};};
 function pintarOrden(){
  const caja=$('[data-orden]');caja.replaceChildren();$('[data-organizacion]').hidden=$('[data-presentacion]').value!=='ampliado';
  if(!selector.value)return;
  const orden=columnasDeSalida(formatoActual());
  orden.forEach((c,i)=>{
   const li=document.createElement('li'),nombre=document.createElement('span'),posicion=document.createElement('select');li.dataset.id=c.id;nombre.textContent=c.titulo||'Sin encabezado';
   posicion.setAttribute('aria-label','Posición de '+nombre.textContent);posicion.title='Mover la columna completa a otra posición del informe ampliado';posicion.disabled=guardando;
   orden.forEach((_,j)=>posicion.append(new Option(String(j+1),String(j))));posicion.value=String(i);
   posicion.onchange=()=>moverColumna(c.id,Number(posicion.value));li.append(nombre,posicion);
   for(const [texto,delta] of [['↑',-1],['↓',1]]){const b=document.createElement('button');b.type='button';b.className='b-sec';b.textContent=texto;b.title=b.ariaLabel=`Mover ${nombre.textContent} ${delta<0?'a la izquierda':'a la derecha'}`;b.disabled=guardando||i+delta<0||i+delta>=orden.length;b.onclick=()=>moverColumna(c.id,i+delta);li.append(b);}
   caja.append(li);
  });
 }
 function moverColumna(id,posicion){const orden=columnasDeSalida(formatoActual()).map(c=>c.id),desde=orden.indexOf(id);if(desde<0||posicion<0||posicion>=orden.length)return;orden.splice(posicion,0,...orden.splice(desde,1));ordenes.set(selector.value,orden);previa();const fila=[...$('[data-orden]').children].find(e=>e.dataset.id===id);fila?.querySelector('select').focus({preventScroll:true});fila?.scrollIntoView({block:'nearest'});}
 function enfocarColumna(){
  const i=columnas()[activo];
  ds.querySelectorAll('[data-indice]').forEach(c=>c.classList.toggle('columna-activa',Number(c.dataset.indice)===i));
  const th=i===undefined?null:$(`[data-tabla] th[data-indice="${i}"]`),tabla=$('[data-tabla]');
  if(th)tabla.scrollTo({left:tabla.scrollLeft+th.getBoundingClientRect().left-tabla.getBoundingClientRect().left-tabla.clientWidth/2+th.offsetWidth/2,behavior:'smooth'});
 }
 function ayudas(cols){
  const f=meta.formatos[selector.value],l=datos?.porOrigen.find(l=>l.origen===selector.value)?.detalle[0];
  for(const s of campos.querySelectorAll('select')){
   const k=s.dataset.campo,i=cols[k],card=s.closest('label');
   const original=['marca','cliente'].includes(k)&&f?.columnas?.[k]!==undefined?f.columnas[k]:null;
   const automatico=destinosInforme(f,k)[0];
   card.querySelector('[data-destino]').textContent=i!==undefined?`En el original: ${letra(i)} · ${f.encabezados[i]}`:original!==null?`Se conserva ${letra(original)} · ${f.encabezados[original]} del archivo original`:automatico!==undefined?`Original: conserva la celda. Ampliado: usa ${letra(automatico)} · ${f.encabezados[automatico]}`:'El informe ampliado agrega este campo en la posición elegida.';
   let valor=l?.[k==='posicion'?'posicionReal':k==='pallet'?'palletsSimple':k];
   if(k==='validacion')valor=l?({OK:'Ok',FALTANTE:'Faltante',SOBRANTE:'Sobrante',NO_ENCONTRADO:'Faltante',PENDIENTE:''}[l.estado]||''):'';
   if(k==='desface')valor=l?.diferencia;
   card.querySelector('[data-ejemplo]').textContent=valor!==undefined&&valor!==null&&String(valor)!==''?'Dato actual: '+String(valor):'Ejemplo orientativo: '+EJEMPLOS[k];
  }
 }
 function previa(){
  const tabla=$('[data-tabla]'),estado=$('[data-estado-vista]');tabla.replaceChildren();
  $('[data-anterior]').hidden=$('[data-siguiente]').hidden=true;
  const cols=columnas(),duplicado=new Set(Object.values(cols)).size!==Object.values(cols).length;
  for(const el of ds.querySelectorAll('[data-campos] select,[data-lista],[data-presentacion],[data-identificacion],[data-orden-original],[data-cerrar]'))el.disabled=guardando;
  $('[data-guardar]').disabled=guardando||duplicado||!selector.value;
  ayudas(cols);
  if(duplicado){estado.textContent='Dos campos apuntan a la misma columna. Corrige la selección para guardar.';return;}
  if(!datos){estado.textContent=cargando?'Cargando datos actuales…':'No se pudieron cargar los datos. Pulsa Actualizar datos.';return;}
  const origen=selector.value,f=meta.formatos[origen];if(!f){estado.textContent='Añade primero un embarque con su packing list.';return;}
  try{
   const lista=datos.porOrigen.find(l=>l.origen===origen)||{detalle:[]};
   pintarOrden();
   const configurado=formatoActual(),exacta=previsualizarLista({...lista,formato:configurado,validacionDepot:datos.validacionDepot},configurado.columnas,{ampliado:$('[data-presentacion]').value==='ampliado',offset,limite:6});
   estado.textContent=exacta.ejemplo?'Ejemplo orientativo: este embarque no tiene registros. Estos valores no se guardan.':`${origen} · Datos reales ${offset+1}–${Math.min(offset+6,exacta.total)} de ${exacta.total}.`;
   const t=document.createElement('table'),head=t.createTHead().insertRow();
   const numero=document.createElement('th');numero.textContent='#';numero.scope='col';numero.title='Número de fila en el archivo exportado';numero.className='fila-guia';head.append(numero);
   exacta.encabezados.forEach((texto,i)=>{const indice=exacta.columnas[i].indice,th=document.createElement('th');th.textContent=letra(i)+' · '+texto;th.scope='col';th.dataset.indice=indice;if(Object.values(cols).includes(indice)||indice>=f.encabezados.length)th.className='columna-resultado';head.append(th);});
   const body=t.createTBody();
   for(const fila of exacta.filas){const tr=body.insertRow(),n=tr.insertCell();n.textContent=String(fila.numero);n.className='fila-guia';
    fila.celdas.forEach((c,i)=>{const indice=exacta.columnas[i].indice,td=tr.insertCell();td.dataset.indice=indice;if(Object.values(cols).includes(indice)||indice>=f.encabezados.length)td.className='columna-resultado';
     if(/^https:\/\/drive\.google\.com\//.test(c.url)){const a=document.createElement('a');a.href=c.url;a.target='_blank';a.rel='noopener';a.textContent=c.texto;td.append(a);}else td.textContent=c.texto;
     td.title=[c.comentario,c.formula?'Fórmula conservada: ='+c.formula:''].filter(Boolean).join('\n');
    });
   }tabla.append(t);
   $('[data-anterior]').hidden=offset===0;$('[data-siguiente]').hidden=offset+6>=exacta.total;enfocarColumna();
  }catch(e){estado.textContent=e.message;$('[data-guardar]').disabled=true;}
 }
 function pintar(){campos.replaceChildren();offset=0;activo='';const f=meta.formatos[selector.value];if(!f){previa();return;}
  const actuales=columnasSegurasInforme(f,borradores.get(selector.value)||f.salida||{...f.columnas,...meta.columnas});
  for(const [titulo,claves] of GRUPOS){const grupo=document.createElement('fieldset'),leyenda=document.createElement('legend');leyenda.textContent=titulo;grupo.append(leyenda);const rejilla=document.createElement('div');rejilla.className='rejilla';grupo.append(rejilla);
   for(const k of claves){const l=document.createElement('label');l.className='campo destino-campo';const texto=document.createElement('span');texto.textContent=CAMPOS_SALIDA[k];const s=document.createElement('select');s.dataset.campo=k;s.setAttribute('aria-label',CAMPOS_SALIDA[k]);s.append(new Option('Conservar / automático al ampliar',''));
    const permitidos=destinosInforme(f,k);for(const i of permitidos)s.append(new Option(letra(i)+' · '+f.encabezados[i],String(i)));
    if(!permitidos.length)s.options[0].textContent='Agregar campo · orden editable';
    const protegidas=document.createElement('optgroup');protegidas.label='Otras columnas · protegidas';f.encabezados.forEach((t,i)=>{if(permitidos.includes(i))return;const o=new Option(letra(i)+' · '+t,String(i));o.disabled=true;protegidas.append(o);});s.append(protegidas);
    s.value=actuales[k]===undefined?'':String(actuales[k]);s.title='Solo se pueden rellenar columnas compatibles. Los datos originales están protegidos.';
    const destino=document.createElement('small');destino.dataset.destino='';const ejemplo=document.createElement('small');ejemplo.dataset.ejemplo='';l.append(texto,s,destino,ejemplo);rejilla.append(l);
    s.onfocus=()=>{activo=k;enfocarColumna();};
   }campos.append(grupo);
  }previa();
 }
 campos.onchange=()=>{borradores.set(selector.value,columnas());offset=0;previa();};selector.onchange=pintar;
 $('[data-presentacion]').onchange=()=>{offset=0;previa();};
 $('[data-identificacion]').onclick=()=>{ordenes.set(selector.value,null);previa();};
 $('[data-orden-original]').onclick=()=>{const natural=columnasDeSalida(formatoActual(),{orden:null}).sort((a,b)=>a.indice-b.indice);ordenes.set(selector.value,natural.map(c=>c.id));previa();};
 $('[data-anterior]').onclick=()=>{offset=Math.max(0,offset-6);previa();};$('[data-siguiente]').onclick=()=>{offset+=6;previa();};
 async function cargar(){if(cargando)return;cargando=true;$('[data-actualizar]').disabled=true;try{
   const recepcion=await pedir(ruta);datos=await reunirInforme(codigo,recepcion);if(ds.open)previa();
  }catch(e){datos=null;$('[data-mensaje]').textContent=e.message;}finally{cargando=false;$('[data-actualizar]').disabled=false;if(ds.open)previa();}}
 $('[data-actualizar]').onclick=cargar;
 $('[data-guardar]').onclick=async()=>{if(guardando)return;guardando=true;previa();try{
  await api(ruta+'/columnas-informe',{metodo:'PUT',cuerpo:{origen:selector.value,columnas:columnas(),ordenSalida:columnasDeSalida(formatoActual()).map(c=>c.id),version:meta.versionFormatos}});
  Object.assign(meta,await api(ruta+'/informe-metadatos'));cambio=true;
  $('[data-mensaje]').textContent='Columnas y orden guardados para el informe ampliado de este embarque. El packing list original se conserva.';
 }catch(e){$('[data-mensaje]').textContent=e.message;}finally{guardando=false;previa();}};
 tecladoDialogo(ds,{accion:'[data-guardar]'});
 ds.addEventListener('cancel',e=>{if(guardando)e.preventDefault();});
 $('[data-cerrar]').onclick=()=>{if(!guardando)ds.close();};pintar();cargar();
 return new Promise(resolve=>ds.addEventListener('close',()=>{ds.remove();resolve(cambio);},{once:true}));
}
