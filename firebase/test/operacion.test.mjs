import { cargar, test, eq, ok, resumen } from './cargador.mjs';
const { fechaDe, recientes } = await cargar('fechas.js');
const { generarZpl, htmlEtiqueta, validarEtiqueta } = await cargar('etiquetas.js');
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
resumen();
