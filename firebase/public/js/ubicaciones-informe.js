/** Proyección de salida: no modifica los conteos ni el detalle de auditoría. */
export const COLUMNA_DETALLE_UNIDADES='DETALLE DE UNIDADES Y PNC POR PALLET';

function identificador(valor,campo,fila){
 const texto=String(valor??'').trim();
 if(texto&&!/^[A-Za-z0-9.-]+$/.test(texto))throw Error(`El ${campo} del ítem ${fila.sku||''}${fila.linea?' (línea '+fila.linea+')':''} contiene caracteres no admitidos: «${texto}». Corrige el registro antes de generar el informe del ejecutivo; solo se permiten letras, números, guion y punto.`);
 return texto;
}

// Compatibilidad con filas antiguas sin registros asignados. Solo reconoce las
// cantidades que añadió el propio informe; nunca elimina caracteres de un ID.
function identificadoresAnteriores(valor,campo,fila){
 return String(valor??'').replace(/\)\s*-\s*/g,')/').split(/\s*\/\s*/).map(p=>identificador(p.replace(/\s*\(\s*\d+(?:[.,]\d+)?\s*(?:u\.)?\s*\)\s*$/,''),campo,fila)).filter(Boolean);
}
const numero=n=>Number(n).toString();

export function filaParaEjecutivo(fila){
 const asignados=Array.isArray(fila.registrosAsignados),partes=asignados?fila.registrosAsignados:[];
 const ids=(campo,anterior,etiqueta)=>[...new Set(asignados
  ?partes.filter(p=>Number(p.cantidad)>0).map(p=>identificador(p[campo],etiqueta,fila)).filter(Boolean)
  :identificadoresAnteriores(anterior,etiqueta,fila))].join('-');
 const pallet=ids('pallet',fila.palletsSimple??fila.pallets,'pallet'),posicion=ids('posicionReal',fila.posicionReal,'posición');
 let detalle='';
 if(asignados&&partes.length){
  const grupos=new Map(),sinCalidad=fila.calidadPorRevisar&&fila.cantidadPnc==null;let conformes=0,pnc=0,porRevisar=0,total=0;
  for(const p of partes){
   const n=Number(p.cantidad);if(!Number.isFinite(n)||n<=0)throw Error('Cantidad inválida en el desglose del ítem '+fila.sku+'. Revisa sus conteos.');
   total+=n;
   if(p.estado==='CONFORME')conformes+=n;if(p.pnc)pnc+=n;if(p.estado==='POR REVISAR')porRevisar+=n;
   const estado=p.pnc?'PNC':sinCalidad&&p.estado==='CONFORME'?'CONDICIÓN POR REVISAR':p.estado||'POR REVISAR',clave=JSON.stringify([p.pallet||'',p.posicionReal||'',estado,p.tipo||'',!!p.sinDetalleUbicacion]);
   grupos.set(clave,(grupos.get(clave)||0)+n);
  }
  if(!Number.isFinite(Number(fila.fisica))||Math.abs(total-Number(fila.fisica))>1e-7)throw Error('El desglose no coincide con la cantidad física del ítem '+fila.sku+'. Actualiza los datos antes de generar el informe.');
  detalle=(sinCalidad?'PNC y conformes: cantidades por revisar':`Conformes: ${numero(conformes)} u. · PNC: ${numero(pnc)} u.`)+(porRevisar?` · Por revisar: ${numero(porRevisar)} u.`:'');
  for(const [clave,n] of grupos){const [p,u,estado,tipo,revisar]=JSON.parse(clave);
   detalle+=` | ${numero(n)} u. ${estado} · Pallet ${p||'sin registrar'} · Posición ${u||'sin registrar'}`+(tipo?' · '+tipo:'')+(revisar?' · Distribución por revisar':'');
  }
 }else if(Number(fila.fisica)>0){
  // Un total global no demuestra qué pallet contiene las unidades PNC.
  detalle=(Number(fila.cantidadPnc)>0?`PNC: ${numero(fila.cantidadPnc)} u. · `:'')+'Desglose de unidades por pallet y condición por revisar: sin registros vinculados a esta fila.';
 }
 return {...fila,palletsSimple:pallet,pallets:pallet,posicionReal:posicion,detalleUnidadesEjecutivo:detalle};
}

/** Se agrega después de organizar las columnas: siempre queda al final. */
export function anadirDetalleEjecutivo(hoja,filas,filaCabecera){
 const rango=XLSX.utils.decode_range(hoja['!ref']||'A1'),columna=rango.e.c+1;
 XLSX.utils.sheet_add_aoa(hoja,[[COLUMNA_DETALLE_UNIDADES],...filas.map(f=>[f.detalleUnidadesEjecutivo||''])],{origin:{r:filaCabecera,c:columna}});
 hoja['!cols']=[...(hoja['!cols']||Array(columna).fill({wch:22})),{wch:85}];
 for(let i=0;i<filas.length;i++){const c=hoja[XLSX.utils.encode_cell({r:filaCabecera+1+i,c:columna})];if(c)c.s={alignment:{wrapText:true,vertical:'top'}};}
 if(hoja['!autofilter'])hoja['!autofilter']={ref:XLSX.utils.encode_range({s:{r:filaCabecera,c:0},e:{r:filaCabecera+filas.length,c:columna}})};
 return hoja;
}
