/** Importación opcional de etiquetas. Nunca crea productos ni modifica conteos. */
export function leerCodigos(libro) {
  const hoja = libro.Sheets['Modelo a Utilizar'] || libro.Sheets.MAESTRO || libro.Sheets[libro.SheetNames[0]];
  const tabla = XLSX.utils.sheet_to_json(hoja, {header:1,raw:false,defval:''});
  const clave = v => String(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().replace(/[^A-Z0-9]/g,'');
  const sku = ['SKU','PRODUCTOID','CODIGOPRODUCTO','CODPRODUCTO','ITEM'];
  const barras = ['CODIGOBARRAS','CODIGODEBARRAS','CODIGOBARRA','CODIGODEBARRA','EAN','BARCODE','CODIGOBARRA1'];
  const inicio = tabla.findIndex(f => f.some(v=>sku.includes(clave(v))) && f.some(v=>barras.includes(clave(v))));
  if(inicio<0)throw new Error('Se necesitan columnas SKU y CODIGO DE BARRAS. Guarda los códigos como texto para conservar ceros iniciales.');
  const a=tabla[inicio].findIndex(v=>sku.includes(clave(v))), b=tabla[inicio].findIndex(v=>barras.includes(clave(v)));
  const filas=tabla.slice(inicio+1).filter(f=>f.some(v=>String(v).trim())).map((f,i)=>{
    if(!String(f[a] || '').trim() || !String(f[b] || '').trim())throw new Error(`Fila ${inicio+i+2}: falta SKU o código de barras.`);
    return {sku:String(f[a]).trim(),codigoBarras:String(f[b]).trim()};
  });
  if(!filas.length || filas.length>5000)throw new Error('El archivo debe contener entre 1 y 5000 filas.');
  return filas;
}
