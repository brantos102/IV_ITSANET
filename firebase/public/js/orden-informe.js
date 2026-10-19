/** Identidades estables: mover columnas cambia la presentación, nunca los datos de origen. */
import {columnasSegurasInforme,destinosInforme,prefijoInforme} from './datos.js?v=20261019-55';

export const CAMPOS_AMPLIADOS={fisica:'Cantidad Física',validacion:'Validación',desface:'Diferencia',pallet:'PALLET',observacion:'OBSERVACION',cantidadIncidencia:'Cant. con incidencia',incidencia:'Tipo de incidencia',evidencia:'Carpeta Drive del SKU',depot:'OK Depot',posicion:'Posición',codigoBarra:'Código de barras',marca:'MARCA',cliente:'CLIENTE'};

export function prepararFormatoInforme(original,ampliado=false){
 const formato={...original,encabezados:[...(original.encabezados||[])],columnas:columnasSegurasInforme(original,original.columnas),prefijo:prefijoInforme(original)};
 const identidades=formato.encabezados.map((_,i)=>'original:'+i);
 if(ampliado)for(const [rol,titulo] of Object.entries(CAMPOS_AMPLIADOS))if(formato.columnas[rol]===undefined){
  const existente=destinosInforme(formato,rol)[0];
  if(existente!==undefined)formato.columnas[rol]=existente;
  else{formato.columnas[rol]=formato.encabezados.length;formato.encabezados.push(titulo);identidades.push('resultado:'+rol);}
 }
 return {...formato,identidades};
}

export function columnasDeSalida(formato,{ampliado=true,orden=formato.ordenSalida}={}){
 const f=prepararFormatoInforme(formato,ampliado);
 const columnas=f.encabezados.map((titulo,indice)=>({id:f.identidades[indice],titulo,indice}));
 if(!ampliado)return columnas;
 if(orden===undefined||orden===null){
  const primeras=[...new Set(['marca','cliente'].map(k=>f.columnas[k]))];
  return [...primeras.map(i=>columnas[i]),...columnas.filter(c=>!primeras.includes(c.indice))].filter(Boolean);
 }
 const porId=new Map(columnas.map(c=>[c.id,c]));
 if(!Array.isArray(orden)||orden.length!==columnas.length||new Set(orden).size!==orden.length||orden.some(id=>!porId.has(id)))throw Error('El orden de columnas ya no corresponde al packing list. Revisa y vuelve a guardar su organización.');
 return orden.map(id=>porId.get(id));
}

function trasladarFormula(formula,mapa){
 // No interpretar referencias externas/estructuradas como si fueran celdas de esta hoja.
 const partes=String(formula).split(/("(?:[^"]|"")*")/g);
 return partes.map((parte,i)=>{
  if(i%2)return parte;
  if(/[!\[\]']/.test(parte)||/\b(?:INDIRECT|OFFSET)\s*\(/i.test(parte))throw Error('El informe contiene una fórmula con referencias externas o dinámicas. Usa el formato original para conservarla.');
  const referencia='\\$?[A-Z]{1,3}(?:\\$?[1-9][0-9]*)?';
  return parte.replace(new RegExp('(?<![A-Za-z0-9_.])('+referencia+')(?:\\s*:\\s*('+referencia+'))?(?![A-Za-z0-9_]|\\s*\\()','gi'),(texto,a,b)=>{
   const separar=v=>/^(\$?)([A-Z]{1,3})(\$?[1-9][0-9]*)?$/i.exec(v);
   const ra=separar(a),rb=b&&separar(b);
   if(!rb&&!ra[3])return texto; // Nombre definido, no referencia A1.
   if(rb&&!!ra[3]!==!!rb[3])return texto;
   const numero=s=>[...s.toUpperCase()].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0)-1;
   const ia=numero(ra[2]),ib=rb?numero(rb[2]):ia;
   if(!mapa.has(ia)||!mapa.has(ib))throw Error('Una fórmula referencia columnas fuera de este informe. Usa el formato original para conservarla.');
   if(rb){const menores=Math.min(ia,ib),mayores=Math.max(ia,ib);for(let c=menores;c<=mayores;c++)if(!mapa.has(c)||mapa.get(c)!==mapa.get(menores)+c-menores)throw Error('El orden elegido separaría un rango usado por una fórmula. Mantén juntas esas columnas o usa el formato original.');}
   const letra=n=>{let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
   const mover=r=>r[1]+letra(mapa.get(numero(r[2])))+(r[3]||'');
   return mover(ra)+(rb?':'+mover(rb):'');
  });
 }).join('');
}

export function organizarHojaInforme(hoja,columnas){
 if(columnas.every((c,i)=>c.indice===i))return hoja;
 const mapa=new Map(columnas.map((c,i)=>[c.indice,i])),salida={};
 for(const [direccion,celda] of Object.entries(hoja)){
  if(direccion.startsWith('!')){salida[direccion]=celda;continue;}
  const p=XLSX.utils.decode_cell(direccion),copia={...celda};
  if(!mapa.has(p.c))throw Error('El informe tiene datos fuera de las columnas configuradas. Conserva el formato original.');
  if(copia.f)copia.f=trasladarFormula(copia.f,mapa);
  salida[XLSX.utils.encode_cell({r:p.r,c:mapa.get(p.c)})]=copia;
 }
 if(hoja['!cols'])salida['!cols']=columnas.map(c=>hoja['!cols'][c.indice]);
 return salida;
}
