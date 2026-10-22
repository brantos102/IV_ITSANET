/** Posición elegida en el conteo; los segmentos conservan ceros iniciales. */
const nombres=['nave','calle','columna','nivel','profundidad'];
export function partesPosicion(valor){
 const texto=String(valor||'').trim().toUpperCase();
 if(/^(?:NAVE|CALLE|LITERAL|COLUMNA|NIVEL|PROFUNDIDAD)\s*:/.test(texto)){
  const partes=Object.fromEntries(nombres.map(n=>[n,'']));
  for(const m of texto.matchAll(/(?:^|[,;\s])\s*(NAVE|CALLE|LITERAL|COLUMNA|NIVEL|PROFUNDIDAD)\s*:\s*([A-Z0-9._]+)/g))partes[m[1]==='LITERAL'?'calle':m[1].toLowerCase()]=m[2];
  return partes;
 }
 const p=texto.split('-').map(v=>v.trim());if(p.length>5||p.some(v=>v&&!/^[A-Z0-9._]+$/.test(v)))return Object.fromEntries(nombres.map(n=>[n,'']));return Object.fromEntries(nombres.map((n,i)=>[n,p[i]||'']));
}
export function unirPosicion(partes){
 return nombres.filter((n,i)=>i<4||partes.profundidad).map(n=>String(partes[n]||'').trim().toUpperCase()).join('-');
}
export function agregarDesglosePosicion(input){
 if(!input||input.dataset.desglosePosicion)return;
 input.dataset.desglosePosicion='1';
 const resumen=document.createElement('p');resumen.className='mini posicion-resumen';resumen.setAttribute('role','status');input.closest('label').after(resumen);
 const mostrar=()=>{const p=partesPosicion(input.value),completa=['nave','calle','columna','nivel'].every(n=>p[n]);
  input.setCustomValidity(input.value.includes(':')&&!completa?'Escribe una posición completa, por ejemplo BM-A-10-1.':'');
  resumen.textContent=completa?'Depot: Nave '+p.nave+' · Literal '+p.calle+' · Columna '+p.columna+' · Nivel '+p.nivel+(p.profundidad?' · Profundidad '+p.profundidad:''):input.value?'Ubicación general registrada. Para una posición de estantería usa BM-A-10-1.':'Selecciona una sugerencia o escribe la posición final.';
 };
 input.addEventListener('input',mostrar);input.addEventListener('change',()=>{const p=partesPosicion(input.value);if(['nave','calle','columna','nivel'].every(n=>p[n]))input.value=unirPosicion(p);mostrar();});mostrar();return resumen;
}
