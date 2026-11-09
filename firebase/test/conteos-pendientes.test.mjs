import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const {crearColaConteos}=await cargar('conteos-pendientes.js');
function memoria(){const datos=new Map();let tx=Promise.resolve();return {datos,
 mutar(id,fn){const p=tx.then(()=>{const r=fn(structuredClone(datos.get(id)));if(r)datos.set(id,structuredClone(r));return structuredClone(r);});tx=p.catch(()=>{});return p;},
 async listar(actor){await tx;return [...datos.values()].filter(j=>j.actor===actor).map(j=>structuredClone(j));}};}
const movimiento=(id='evento-71-123456',cantidad=5)=>({recepcion:'R71',cuerpo:{sku:'SKU1',cantidad,pallet:'A01',idempotencyKey:id,fotos:[]}});
const error=(codigo,estado=0)=>Object.assign(new Error(codigo),{codigo,estado});

await test('antes de transmitir se confirma el guardado durable; la cuota agotada no finge éxito',async()=>{
 let envios=0;const c=crearColaConteos({actor:'A',transportar:async()=>envios++,almacen:{mutar:async()=>{throw Error('cuota');},listar:async()=>[]}});
 let rechazo=false;try{await c.guardar(movimiento());}catch{rechazo=true;}ok(rechazo);eq(envios,0);
});
await test('varios conteos y fotos sobreviven a otra instancia de página y se envían una vez',async()=>{
 const almacen=memoria();let c=crearColaConteos({actor:'A',almacen,transportar:async()=>{throw error('SIN_RED');}});
 const foto=new Blob(['evidencia real de prueba'],{type:'image/jpeg'});foto.name='pnc.jpg';
 await c.guardar({...movimiento('primero-71-123456',2),fotos:[foto]});await c.guardar(movimiento('segundo-71-123456',4));await c.sincronizar(true);c.detener();
 eq((await almacen.listar('A')).length,2);let total=0,fotos=0;
 c=crearColaConteos({actor:'A',almacen,transportar:async j=>{total+=j.cuerpo.cantidad;for(const f of j.fotos){eq(await f.blob.text(),'evidencia real de prueba');fotos++;}return {sku:'SKU1',contado:total};}});
 await c.sincronizar(true);await c.sincronizar(true);eq(total,6);eq(fotos,1);ok((await c.listar()).every(j=>j.estado==='CONFIRMADO'&&j.fotos.length===0));
});
await test('respuesta perdida después del commit conserva el identificador en el reintento',async()=>{
 const almacen=memoria(),servidor=new Set();let cantidad=0,llamadas=0;
 const transportar=async j=>{llamadas++;if(!servidor.has(j.id)){servidor.add(j.id);cantidad+=j.cuerpo.cantidad;throw error('SIN_RED');}return {sku:'SKU1',contado:cantidad,duplicado:true};};
 const c=crearColaConteos({actor:'A',almacen,transportar});await c.guardar(movimiento());await c.sincronizar(true);eq((await c.listar())[0].estado,'PENDIENTE');await c.sincronizar(true);eq(cantidad,5);eq(llamadas,2);eq((await c.listar())[0].estado,'CONFIRMADO');
});
await test('dos pestañas de una cuenta comparten arrendamiento atómico y no pisan el ACK',async()=>{
 const almacen=memoria();let liberar,entrar;const dentro=new Promise(r=>entrar=r),espera=new Promise(r=>liberar=r);let envios=0;
 const transportar=async()=>{envios++;entrar();await espera;return {sku:'SKU1',contado:5};};
 const a=crearColaConteos({actor:'A',almacen,transportar}),b=crearColaConteos({actor:'A',almacen,transportar});await a.guardar(movimiento());const p=a.sincronizar(true);await dentro;await b.sincronizar(true);eq(envios,1);liberar();await p;eq((await b.listar())[0].estado,'CONFIRMADO');
});
await test('varios operarios conservan colas independientes sin reenviar registros ajenos',async()=>{
 const almacen=memoria(),vistos=[];
 const a=crearColaConteos({actor:'A',almacen,transportar:async j=>{vistos.push(j.actor);return {};}}),b=crearColaConteos({actor:'B',almacen,transportar:async j=>{vistos.push(j.actor);return {};}});
 await a.guardar(movimiento('operario-A-123456'));await b.guardar(movimiento('operario-B-123456'));
 await a.sincronizar(true);eq(vistos,['A']);eq((await b.listar())[0].estado,'PENDIENTE');await b.sincronizar(true);eq(vistos,['A','B']);
});
await test('sobrante requiere nueva confirmación explícita; la cola no la inventa',async()=>{
 const almacen=memoria();let envios=0;
 const c=crearColaConteos({actor:'A',almacen,transportar:async j=>{envios++;if(!j.cuerpo.confirmarSobrante)throw error('CONFIRMAR_SOBRANTE',409);return {sku:'SKU1',contado:5};}});
 await c.guardar(movimiento());await c.sincronizar(true);await c.sincronizar(true);eq(envios,1);eq((await c.listar())[0].estado,'REVISION');
 await c.reintentar('evento-71-123456',{confirmarSobrante:true});eq(envios,2);eq((await c.listar())[0].estado,'CONFIRMADO');
});
await test('recepción cerrada conserva campos y fotos, sin repetición automática',async()=>{
 const c=crearColaConteos({actor:'A',almacen:memoria(),transportar:async()=>{throw error('RECEPCION_CERRADA',409);}});
 await c.guardar(movimiento());await c.sincronizar(true);await c.sincronizar(true);const j=(await c.listar())[0];eq(j.estado,'REVISION');eq(j.intentos,1);eq(j.cuerpo.cantidad,5);
});
await test('restaurar respaldo mantiene IDs y rechaza otra cuenta antes de guardar',async()=>{
 const original=crearColaConteos({actor:'A',almacen:memoria(),transportar:async()=>({})});await original.guardar(movimiento());const [j]=await original.listar();
 const destino=crearColaConteos({actor:'A',almacen:memoria(),transportar:async()=>({})});eq(await destino.restaurar([j]),1);eq(await destino.restaurar([j]),0);eq((await destino.listar())[0].id,j.id);
 let rechazo=false;try{await destino.restaurar([{...j,actor:'B'}]);}catch{rechazo=true;}ok(rechazo);eq((await destino.listar()).length,1);
});
await test('fallo de presentación posterior al ACK no repite el conteo',async()=>{
 let envios=0;const c=crearColaConteos({actor:'A',almacen:memoria(),transportar:async()=>{envios++;return {};},alConfirmar:()=>{throw Error('vista');}});
 await c.guardar(movimiento());await c.sincronizar(true);await c.sincronizar(true);eq(envios,1);eq((await c.listar())[0].estado,'CONFIRMADO');
});
resumen();
