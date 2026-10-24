import {fechaDe} from './fechas.js?v=20261024-69';

const zona='America/Guayaquil';
const calendario=new Intl.DateTimeFormat('en-CA',{timeZone:zona,year:'numeric',month:'2-digit',day:'2-digit'});
const fecha=new Intl.DateTimeFormat('es-EC',{timeZone:zona,day:'2-digit',month:'2-digit',year:'numeric'});
const hora=new Intl.DateTimeFormat('es-EC',{timeZone:zona,hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
const normalizar=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();

export function registroRecepcion(valor){
  const f=fechaDe(valor);
  if(!f)return {dia:'',fecha:'Sin fecha registrada',hora:'',iso:''};
  const p=Object.fromEntries(calendario.formatToParts(f).map(x=>[x.type,x.value]));
  return {dia:p.year+'-'+p.month+'-'+p.day,fecha:fecha.format(f),hora:hora.format(f),iso:f.toISOString()};
}

export function filtrarRecepciones(recepciones,{texto='',estado='',desde='',hasta='',orden='RECIENTES'}={}){
  const q=normalizar(texto).trim();
  if(desde&&hasta&&desde>hasta)throw new Error('La fecha Desde debe ser anterior o igual a Hasta.');
  return recepciones.filter(r=>{
    if(estado&&r.estado!==estado)return false;
    const d=registroRecepcion(r.creadoEn).dia;
    if((desde||hasta)&&!d || desde&&d<desde || hasta&&d>hasta)return false;
    return !q||normalizar([r.codigo,r.cliente,r.marca,r.descripcion,...(r.origenes||[]),...Object.values(r.nombresListas||{})].join(' ')).includes(q);
  }).sort((a,b)=>{
    const codigo=String(a.codigo||'').localeCompare(String(b.codigo||''),'es',{numeric:true});
    if(orden==='CODIGO')return codigo;
    const fa=fechaDe(a.creadoEn)?.getTime(),fb=fechaDe(b.creadoEn)?.getTime();
    if(fa==null||fb==null)return fa==null?(fb==null?codigo:1):-1;
    return (orden==='ANTIGUAS'?fa-fb:fb-fa)||codigo;
  });
}
