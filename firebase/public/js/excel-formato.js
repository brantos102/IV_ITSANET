/** Tipos Excel explícitos: cantidades calculables, identificadores sin pérdida de dígitos. */
export const FORMATO_CANTIDAD='#,##0';
export const FORMATO_IMPORTE='#,##0.00';
export function formatoDeNumero(n,{importe=false}={}){
 const [mantisa,exponente='0']=String(n).toLowerCase().split('e');
 const decimales=Math.max(importe?2:0,Math.min(15,(mantisa.split('.')[1]?.length||0)-Number(exponente)));
 return FORMATO_CANTIDAD+(decimales?'.'+'0'.repeat(decimales):'');
}
const clave=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().replace(/[^A-Z0-9]/g,'');
const rolesNumero=new Set(['cantidad','precioUnit','precioTotal','fisica','desface','cantidadIncidencia']);
const rolesTexto=new Set(['sku','descripcion','referencia','factura','embarque','contenedor','pallet','posicion','codigoBarra','incidencia','observacion','evidencia','depot','marca','cliente']);

export function rolDeNumero(encabezado){
 const c=clave(encabezado);
 if(/^(?:CANTIDAD|QTY|QUANTITY|CANT|CANTIDADDECLARADA|DECLARADO|ESPERADO)$/.test(c))return 'cantidad';
 if(/^(?:CANTIDADFISICA|CANTFISICA|CANTIDADVALIDADA|CONTADO|FISICO)$/.test(c))return 'fisica';
 if(/^(?:DIFERENCIA|DESFACE|DESFASE)$/.test(c))return 'desface';
 if(/^(?:CANTCONINCIDENCIA|CANTIDADCONINCIDENCIA|CANTCONINCIDENCIADIFERENCIA)$/.test(c))return 'cantidadIncidencia';
 if(/^(?:PRECIOUNIT|PRECIOUNITARIO|PRECIOU|UNITPRICE|VALORUNITARIO|COSTOUNITARIO)$/.test(c))return 'precioUnit';
 if(/^(?:PRECIOTOTAL|PRECIOTO|TOTALPRICE|VALORTOTAL|IMPORTETOTAL|IMPORTE|AMOUNT)$/.test(c))return 'precioTotal';
 return '';
}

/** Analiza solo una columna numérica conocida. Jamás extrae dígitos de texto libre. */
export function numeroParaExcel(valor,{originalNumerico=false}={}){
 if(typeof valor==='number')return Number.isFinite(valor)?valor:NaN;
 let t=String(valor??'').trim();if(!t)return null;
 if(originalNumerico)return /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?$/i.test(t)&&Number.isFinite(Number(t))?Number(t):NaN;
 const parentesis=/^\(.*\)$/.test(t);if(parentesis)t=t.slice(1,-1).trim();
 t=t.replace(/^(?:USD|EUR|US\$|[$€£])\s*/i,'').replace(/\s*(?:USD|EUR|[$€£])$/i,'').replace(/[\s\u00a0]/g,'');
 if(!/^[-+]?\d[\d.,]*(?:e[-+]?\d+)?$/i.test(t))return NaN;
 if(/e/i.test(t))return !t.includes(',')&&Number.isFinite(Number(t))?(parentesis?-1:1)*Number(t):NaN;
 const negativo=t.startsWith('-')||parentesis;t=t.replace(/^[-+]/,'');
 const punto=t.lastIndexOf('.'),coma=t.lastIndexOf(',');
 if(punto>=0&&coma>=0){const decimal=punto>coma?'.':',',miles=decimal==='.'?',':'.';const partes=t.split(decimal);if(partes.length!==2||!/^\d+$/.test(partes[1])||!new RegExp('^\\d{1,3}(?:\\'+miles+'\\d{3})*$').test(partes[0]))return NaN;t=partes[0].split(miles).join('')+'.'+partes[1];}
 else if(punto>=0||coma>=0){const sep=punto>=0?'.':',',partes=t.split(sep);if(partes.length>2){if(!/^\d{1,3}$/.test(partes[0])||!partes.slice(1).every(p=>/^\d{3}$/.test(p)))return NaN;t=partes.join('');}else{if(!partes.every(p=>/^\d+$/.test(p)))return NaN;t=partes[1].length===3?partes.join(''):partes[0]+'.'+partes[1];}}
 const n=Number(t)*(negativo?-1:1);return Number.isFinite(n)?n:NaN;
}

const textoIdentificador=c=>/^(?:SKU|CODIGO|CODIGOPRODUCTO|CODPRODUCTO|CODPROD|CODIGOBARRA|CODIGOBARRAS|CODIGODEBARRAS|FACTURA|INVOICE|REFERENCIA|REFERENCIAPEDIDO|PEDIDO|EMBARQUE|SHIPMENT|BL|CONTENEDOR|NOMBRECONTENEDOR|NUMEROCONTENEDOR|CONTAINER|PALLET|PALETA|POSICION.*|UBICACION.*)$/.test(c);

export function tiparHojaOriginal(hoja,filas,encabezados,columnas,primeraFila){
 filas.forEach((l,i)=>encabezados.forEach((titulo,c)=>{
  const direccion=XLSX.utils.encode_cell({r:primeraFila+i,c}),celda=hoja[direccion];if(!celda)return;
  const explicito=Object.entries(columnas).find(([,j])=>j===c)?.[0],rol=rolesNumero.has(explicito)?explicito:rolDeNumero(titulo);
  const identificador=rolesTexto.has(explicito)||textoIdentificador(clave(titulo))||clave(titulo)==='ITEM'&&String(celda.v??'')===String(l.sku??'');
  const tipoOriginal=l.tiposCelda?.[c],formatoOriginal=l.formatosCelda?.[c];
  if(identificador){if(celda.v!==null&&celda.v!==undefined)celda.v=String(celda.v);celda.t='s';celda.z='@';delete celda.w;return;}
  if(rol||tipoOriginal==='n'){
   // Cantidades corregidas se toman del dato vigente. Los demás valores de origen
   // conservan el número bruto; el formato de visualización no redondea el dato.
   const esOrigen=['cantidad','precioUnit','precioTotal'].includes(rol);
   const valor=esOrigen&&typeof l[rol]==='number'?l[rol]:celda.v;
   if(valor===null||valor===undefined||valor==='')return;
   const n=numeroParaExcel(valor,{originalNumerico:typeof valor==='number'||tipoOriginal==='n'});
   if(!Number.isFinite(n))throw Error('No se puede exportar un número inválido en '+titulo+', fila '+(primeraFila+i+1)+'. Revisa el valor de origen; no se sustituyó por cero.');
   celda.v=n;celda.t='n';celda.z=formatoOriginal&&formatoOriginal!=='@'&&formatoOriginal!=='General'?formatoOriginal:formatoDeNumero(n,{importe:/^precio/.test(rol)});delete celda.w;
  }else if(tipoOriginal==='b'&&['true','false'].includes(String(celda.v))){celda.t='b';celda.v=String(celda.v)==='true';delete celda.w;}
 }));
 return hoja;
}

function xmlValido(valor){
 const s=String(valor);for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);if(c===0xfffe||c===0xffff||c>=0xd800&&c<=0xdbff&&(i+1>=s.length||s.charCodeAt(++i)<0xdc00||s.charCodeAt(i)>0xdfff)||c>=0xdc00&&c<=0xdfff)return false;}return true;
}

/** Detiene un archivo corrupto antes de descargarlo, conservando los datos fuente. */
export function validarLibroExcel(libro){
 const nombres=new Set();
 for(const nombre of libro.SheetNames){
  const k=nombre.toUpperCase();if(nombres.has(k))throw Error('Hay hojas con nombres repetidos: '+nombre);nombres.add(k);
  if(!xmlValido(nombre))throw Error('El nombre de una hoja contiene caracteres no válidos para Excel.');
  const hoja=libro.Sheets[nombre];
  for(const [direccion,c] of Object.entries(hoja)){
   if(direccion.startsWith('!')||!c||typeof c!=='object')continue;
   if(c.t==='n'&&!Number.isFinite(c.v))throw Error('No se puede exportar '+nombre+'!'+direccion+': el valor numérico no es finito. Actualiza los datos y revisa ese registro.');
   for(const campo of ['v','f','z'])if(c[campo]!==undefined&&!xmlValido(c[campo]))throw Error('No se puede exportar '+nombre+'!'+direccion+': contiene un carácter no válido para Excel. Corrige el dato de origen.');
   if(c.l&&(!xmlValido(c.l.Target||'')||!xmlValido(c.l.Tooltip||'')))throw Error('Hay un enlace no válido en '+nombre+'!'+direccion+'.');
  }
 }
 for(const v of Object.values(libro.Props||{}))if(!xmlValido(v))throw Error('Los datos de identificación del informe contienen un carácter no válido para Excel.');
 return libro;
}

/** Formatos para las hojas calculadas, sin transformar números escritos como identificadores. */
export function formatoNumericoCalculado(hoja){
 for(const [direccion,c] of Object.entries(hoja))if(!direccion.startsWith('!')&&c?.t==='n'&&Number.isFinite(c.v)&&(!c.z||c.z==='General'))c.z=formatoDeNumero(c.v);
 return hoja;
}
