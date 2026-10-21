/** Posición elegida en el conteo; los segmentos conservan ceros iniciales. */
const nombres=['nave','calle','columna','nivel','profundidad'];
export function partesPosicion(valor){
 const texto=String(valor||'').trim().toUpperCase();
 if(/^(?:NAVE|CALLE|LITERAL|COLUMNA|NIVEL|PROFUNDIDAD)\s*:/.test(texto)){
  const partes=Object.fromEntries(nombres.map(n=>[n,'']));
  for(const m of texto.matchAll(/(?:^|[,;\s])\s*(NAVE|CALLE|LITERAL|COLUMNA|NIVEL|PROFUNDIDAD)\s*:\s*([A-Z0-9._]+)/g))partes[m[1]==='LITERAL'?'calle':m[1].toLowerCase()]=m[2];
  return partes;
 }
 const p=texto.split('-').map(v=>v.trim());return Object.fromEntries(nombres.map((n,i)=>[n,p[i]||'']));
}
export function unirPosicion(partes){
 return nombres.filter((n,i)=>i<4||partes.profundidad).map(n=>String(partes[n]||'').trim().toUpperCase()).join('-');
}
export function agregarDesglosePosicion(input){
 const d=document.createElement('details');d.className='posicion-depot-partes';d.innerHTML='<summary>Nave, Calle / Literal, Columna y Nivel · Depot</summary><p class="mini">Ejemplo: BM-A-10-1. Completa los cuatro campos para guardar una posición de Depot.</p><div class="rejilla">'+nombres.map(n=>'<label class="campo"><span>'+({nave:'Nave',calle:'Calle / Literal',columna:'Columna',nivel:'Nivel',profundidad:'Profundidad · opcional'}[n])+'</span><input data-posicion-parte="'+n+'" autocomplete="off" maxlength="20" aria-label="'+({calle:'Calle o literal',profundidad:'Profundidad opcional'}[n]||n[0].toUpperCase()+n.slice(1))+'"></label>').join('')+'</div><p class="mini" data-resumen-posicion role="status"></p>';
 input.closest('label').after(d);const campos=Object.fromEntries([...d.querySelectorAll('input')].map(e=>[e.dataset.posicionParte,e]));
 const mostrar=()=>{const p=partesPosicion(input.value),completa=nombres.slice(0,4).every(n=>p[n]);for(const n of nombres)campos[n].value=completa?p[n]:'';d.querySelector('[data-resumen-posicion]').textContent=completa?'Nave: '+p.nave+' · Calle/Literal: '+p.calle+' · Columna: '+p.columna+' · Nivel: '+p.nivel+(p.profundidad?' · Profundidad: '+p.profundidad:''):input.value?'Ubicación general. Para el CSV de Depot completa el desglose.':'Posición pendiente de confirmar.';};
 input.addEventListener('input',()=>{input.setCustomValidity('');if(input.value.includes(':')){const p=partesPosicion(input.value);if(nombres.slice(0,4).every(n=>p[n]))input.value=unirPosicion(p);else input.setCustomValidity('Completa Nave, Calle/Literal, Columna y Nivel.');}mostrar();});
 d.addEventListener('toggle',()=>{if(d.open)mostrar();});
 for(const el of Object.values(campos))el.addEventListener('input',()=>{
  const p=Object.fromEntries(nombres.map(n=>[n,campos[n].value.trim().toUpperCase()])),hay=nombres.some(n=>p[n]),completa=nombres.slice(0,4).every(n=>p[n]);
  const error=hay&&(!completa||nombres.some(n=>p[n]&&!/^[A-Z0-9._]+$/.test(p[n])));
  input.setCustomValidity(error?'Completa Nave, Calle/Literal, Columna y Nivel con letras o números.':'');
  d.querySelector('[data-resumen-posicion]').textContent=error?'Completa los cuatro campos antes de guardar.':'Posición para Depot: '+(completa?unirPosicion(p):'pendiente');
  if(!error){input.value=completa?unirPosicion(p):'';input.dispatchEvent(new Event('input',{bubbles:true}));}
 });
 mostrar();return d;
}
