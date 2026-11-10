/** Asignación por registro y fila. Nunca convierte una ubicación global en una individual. */
export function segmentosDeConteos(eventos){
 const anulados=new Set(eventos.flatMap(e=>[e.anulaA,e.refEvento]).filter(Boolean));
 const activos=eventos.filter(e=>e.tipo!=='ANULACION'&&!e.anulado&&!anulados.has(e.id));
 const correcciones=new Map(activos.filter(e=>e.tipo==='CALIDAD'&&e.eventoId).map(e=>[e.eventoId,e.incidencias]));
 return activos.filter(e=>(!e.tipo||e.tipo==='CONTEO')&&Number(e.cantidad)>0).flatMap(e=>{
  const fs=correcciones.get(e.id)??e.incidencias??(e.estadoFisico==='PNC'?[{tipo:'MAL_ESTADO',nombre:'PNC',cantidad:Number(e.cantidad),pnc:true}]:[]);
  const partes=[];let resta=Number(e.cantidad);
  for(const f of fs){const n=Math.min(resta,Math.max(0,Number(f.cantidad)||0));if(!n)continue;resta-=n;partes.push({cantidad:n,estado:f.pnc?'PNC':'INCIDENCIA',tipo:f.nombre||f.tipo,pallet:f.pallet||e.pallet||'',pnc:!!f.pnc});}
  if(resta>0)partes.push({cantidad:resta,estado:'CONFORME',tipo:'',pallet:e.pallet||'',pnc:false});
  return partes.map(p=>({...p,sku:e.sku,origen:e.origen||'',eventoId:e.id||'',posicionReal:e.posicionReal||'',observacion:e.observacion||'',sinDetalleUbicacion:!!e.sinDetalleUbicacion||String(e.pallet||'').includes('-')}));
 });
}

function sumar(partes,campo){const mapa=new Map();for(const p of partes)if(p[campo])mapa.set(p[campo],(mapa.get(p[campo])||0)+p.cantidad);return mapa;}
const cantidad=n=>Number(Number(n).toFixed(6)).toString();

export function repartirRegistrosEnFilas(filas,eventos){
 const origenes=new Map();for(const f of filas){if(!origenes.has(f.sku))origenes.set(f.sku,new Set());origenes.get(f.sku).add(f.origen||'PRINCIPAL');}
 const segmentos=segmentosDeConteos(eventos).map(p=>({...p,restante:p.cantidad}));
 const ceros=eventos.filter(e=>['NO_ENCONTRADO','CERO'].includes(e.tipo)&&!e.anulado&&!eventos.some(a=>a.tipo==='ANULACION'&&a.anulaA===e.id));
 return filas.map(f=>{
  const origen=f.origen||'PRINCIPAL',partes=[];let resta=Math.max(0,Number(f.fisica)||0);
  for(const p of segmentos){if(p.sku!==f.sku||p.origen!==origen&&!(p.origen===''&&origenes.get(f.sku).size===1))continue;
   const n=Math.min(resta,p.restante);if(n<=0)continue;p.restante-=n;resta-=n;const {restante,...parte}=p;partes.push({...parte,cantidad:n,origen});
  }
  if(resta>0)partes.push({sku:f.sku,origen,cantidad:resta,estado:'POR REVISAR',tipo:'Sin conteo vinculado a esta fila/lista',pallet:'',posicionReal:'',observacion:'',eventoId:'',pnc:false,sinDetalleUbicacion:true});
  const pallets=sumar(partes,'pallet'),posiciones=sumar(partes,'posicionReal'),notas=[...new Set(partes.map(p=>p.observacion).filter(Boolean))];
  if(!partes.length){for(const e of ceros)if(e.sku===f.sku&&(e.origen===origen||!e.origen&&origenes.get(f.sku).size===1)&&e.observacion&&!notas.includes(e.observacion))notas.push(e.observacion);}
  const destinos=new Map();for(const p of partes){const k=JSON.stringify([p.pallet,p.posicionReal]);destinos.set(k,(destinos.get(k)||0)+p.cantidad);}
  const incidencias=partes.filter(p=>p.estado==='PNC'||p.estado==='INCIDENCIA');
  return {...f,registrosAsignados:partes,pallets:[...pallets].map(([p,n])=>p+'('+cantidad(n)+')').join(' / '),
   palletsSimple:pallets.size===1?[...pallets.keys()][0]:[...pallets].map(([p,n])=>p+' ('+cantidad(n)+' u.)').join(' / '),
   posicionReal:posiciones.size===1?[...posiciones.keys()][0]:[...posiciones].map(([p,n])=>p+' ('+cantidad(n)+' u.)').join(' / '),
   destino:[...destinos].map(([k,n])=>{const [p,u]=JSON.parse(k);return cantidad(n)+' u. · '+(p||'sin pallet')+(u?' → '+u:' · sin posición');}).join(' | '),
   observacion:notas.join(' | '),cantidadPnc:incidencias.filter(p=>p.pnc).reduce((n,p)=>n+p.cantidad,0),
   cantidadConforme:partes.filter(p=>p.estado==='CONFORME').reduce((n,p)=>n+p.cantidad,0),
   cantidadIncidencia:incidencias.reduce((n,p)=>n+p.cantidad,0),incidenciasAsignadas:incidencias,
   ubicacionPorRevisar:partes.some(p=>p.sinDetalleUbicacion||p.pallet.includes('-'))};
 });
}
