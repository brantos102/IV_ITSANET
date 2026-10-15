import { cargar, test, eq, ok, resumen } from './cargador.mjs';
const { fechaDe, recientes } = await cargar('fechas.js');
const { generarZpl, htmlEtiqueta, validarEtiqueta, etiquetaDesdeStock } = await cargar('etiquetas.js');
await test('recepciones recientes: ISO de MySQL y Timestamp de Firestore',()=>{
  const ahora=Date.parse('2026-10-15T00:00:00Z');
  const r=recientes([{id:'local',creadoEn:'2026-10-14T18:00:00Z'},{id:'nube',creadoEn:{toDate:()=>new Date(ahora-86400000)}},{id:'antigua',creadoEn:'2026-09-01T00:00:00Z'},{id:'sin-fecha',creadoEn:null}],15,ahora);
  eq(r.map(x=>x.id),['local','nube']);eq(fechaDe('no-es-fecha'),null);
});
const etiqueta={cliente:'VENTURA',sku:'6RF199315D',descripcion:'PUENTE DEL MOTOR Y LA CAJA DE CAMBIOS',cantidad:1,estado:'NUV',responsable:'Antonio Espinosa',serie:'SERIE-PRUEBA'};
await test('Zebra 203 dpi: etiqueta 100 × 50 mm y todos los campos solicitados',()=>{
  const zpl=generarZpl(etiqueta);ok(zpl.includes('^PW800'));ok(zpl.includes('^LL400'));ok(zpl.includes('^BCN'));
  const texto=htmlEtiqueta(etiqueta,'<svg class="barras"></svg>');
  for(const valor of ['VENTURA','6RF199315D','DISPONIBLE','SERIE-PRUEBA','Antonio Espinosa','RESPONSABLE','QTY','NUV']) ok(texto.includes(valor),valor);
});
await test('ZPL no ejecuta comandos de los datos y HTML no interpreta observaciones',()=>{
  const peligro={...etiqueta,responsable:'^XZ\n^XA',descripcion:'<img src=x onerror=alert(1)>'};
  const zpl=generarZpl(peligro);eq(zpl.match(/\^XA/g).length,1);eq(zpl.match(/\^XZ/g).length,1);
  const h=htmlEtiqueta(peligro,'<svg></svg>');ok(!h.includes('<img'));ok(h.includes('&lt;img'));
});
await test('una etiqueta PNC no declara mercaderia disponible',()=>{ok(htmlEtiqueta({...etiqueta,estado:'PNC'},'<svg/>').includes('CUARENTENA'));ok(!htmlEtiqueta({...etiqueta,estado:'PNC'},'<svg/>').includes('DISPONIBLE'));});
await test('no se imprimen cantidades invalidas ni codigos vacios',()=>{for(const d of [{...etiqueta,cantidad:0},{...etiqueta,cantidad:-1},{...etiqueta,sku:''}]) {let rechazo=false;try{validarEtiqueta(d);}catch{rechazo=true;}ok(rechazo);}});
const csv=await cargar('csv.js'),kpi=await cargar('kpi.js');
await test('producto presente en el maestro no se vuelve a dar de alta por ser adicional',()=>{
  const r=csv.csvDeProductos(csv.FORMATOS_BASE[1],{recepcion:{codigo:'R'},catalogo:{EXISTE:{existe:true}},adicionales:[{sku:'EXISTE'},{sku:'NUEVO'}]});
  eq(r.filas,1);eq(r.tabla[1][1],'NUEVO');
});
await test('códigos de barras se exportan aparte, como texto y con columnas editables',()=>{
  const f=structuredClone(csv.FORMATOS_BASE[2]);f.columnas[0].encabezado='PRODUCTO';
  const r=csv.csvDeCodigosBarras(f,{recepcion:{codigo:'R'},codigosBarras:[{sku:'EXISTE',codigoBarras:'00001234'}]});
  eq(r.tabla,[['PRODUCTO','CODIGO DE BARRAS'],['EXISTE','00001234']]);eq(r.incidencias.length,0);
});
await test('importación de barras elige Modelo a Utilizar y conserva ceros',async()=>{
  globalThis.XLSX={utils:{sheet_to_json:h=>h}};
  const {leerCodigos}=await cargar('codigos.js');
  eq(leerCodigos({SheetNames:['Instrucciones','Modelo a Utilizar'],Sheets:{Instrucciones:[['no usar']], 'Modelo a Utilizar':[['SKU','CODIGO DE BARRAS'],['EXISTE','00001234']]}}),[{sku:'EXISTE',codigoBarras:'00001234'}]);
});
await test('la macro usa B,C,D,E,G,H,I,J,L,M y no confunde responsable con operario',()=>{
  const d=etiquetaDesdeStock([1,'VENTURA','6RF199315D','PUENTE DEL MOTOR','SERIE123','LOTE','DESPACHO','PARTIDA','DISPONIBLE','NUV','BM-A1-01-3','CS',1]);
  eq(d.cliente,'VENTURA');eq(d.sku,'6RF199315D');eq(d.responsable,'PARTIDA');eq(d.unidad,'CS');eq(d.cantidad,1);eq(d.serie,'SERIE123');
  eq(generarZpl(d).match(/\^BCN/g).length,2,'codigo y serie tienen barras');
});
await test('los modelos oficiales conservan campos obligatorios y no copian ejemplos',()=>{
  eq(csv.FORMATOS_BASE[0].columnas.length,18);eq(csv.FORMATOS_BASE[1].columnas.length,38);
  for(const f of csv.FORMATOS_BASE)eq(f.separador,',');
  const r=csv.csvDeProductos(csv.FORMATOS_BASE[1],{recepcion:{cliente:'VENTURA'},adicionales:[{sku:'001',descripcion:'Producto'}]});
  ok(r.incidencias.some(i=>i.encabezado==='CODIGO UNIDAD'));ok(r.incidencias.some(i=>i.encabezado==='CODIGO PAIS'));
  ok(!r.texto.includes('DPW'));ok(!r.texto.includes('DEFAULT'));
});
await test('las series no se suman ni se usa DISPONIBLE para un PNC sin categoria definida',()=>{
  const filas=csv.agruparConteos([{id:'1',sku:'S',cantidad:1,pallet:'F1',serie:'SERIE1'},{id:'2',sku:'S',cantidad:1,pallet:'F1',serie:'SERIE2'}]);eq(filas.length,2);
  const f=structuredClone(csv.FORMATOS_BASE[0]);for(const c of f.columnas)if(c.campo==='categoria')c.valor='DISPONIBLE';
  const r=csv.csvDeCantidades(f,{eventos:[{id:'p',sku:'S',cantidad:1,pallet:'F1',estadoFisico:'PNC'}]});
  eq(r.tabla[1][7],'');ok(r.incidencias.some(i=>i.encabezado==='CODIGO CATEGORIA LÓGICA'));
});
await test('filtros del dashboard recortan unidades, referencias y eventos al mismo conjunto',()=>{
  const todos=[{recepcion:{id:'R',codigo:'VW001',cliente:'VENTURA'},skus:[{sku:'001',descripcion:'Filtro',esperado:4,contado:3,verificado:true,estado:'FALTANTE',tienePnc:true},{sku:'002',descripcion:'Motor',esperado:9,contado:9,verificado:true,estado:'OK'}],eventos:[{id:'1',sku:'001',cantidad:3},{id:'2',sku:'002',cantidad:9}]}];
  const f=kpi.filtrarDetalles(todos,{producto:'filtro',etiqueta:'PNC'});eq(f[0].skus.length,1);eq(f[0].eventos.length,1);
  const t=kpi.consolidar(f.map(kpi.indicadoresDe));eq(t.fisicas,3);eq(t.esperadas,4);eq(t.skus,1);
  eq(kpi.filtrarDetalles(todos,{producto:'999'}).length,0);eq(kpi.referenciasDe(f)[0].diferencia,-1);
});
resumen();
