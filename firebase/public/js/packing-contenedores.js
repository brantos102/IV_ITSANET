import {seleccionarContenedoresPacking} from './datos.js?v=20261021-61';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function prepararSeleccionContenedores(resultado,panel,alCambiar){
 const opciones=[...new Set(resultado.lineas.map(l=>l.contenedor||''))];if(!opciones.some(Boolean))return;
 const d=document.createElement('details');d.className='seleccion-contenedores';d.open=true;
 d.innerHTML='<summary>Contenedores y embarques detectados · selecciona solo lo recibido</summary><p class="mini">Un archivo puede contener varios embarques y contenedores. Elegir un contenedor conserva únicamente sus filas, sin duplicarlas. El correo podrá separarse por embarque al finalizar. Las tablas laterales no se cruzan por número de fila.</p><div>'+opciones.map((n,i)=>{const ls=resultado.lineas.filter(l=>(l.contenedor||'')===n);return `<label class="correo-opcion"><input type="checkbox" data-contenedor="${esc(n)}" checked>${esc(n||'Filas sin contenedor')} · ${esc([...new Set(ls.map(l=>l.embarque).filter(Boolean))].join(', '))} · ${ls.length} líneas</label>`;}).join('')+'</div><p data-seleccion-resumen role="status"></p>';
 const pintar=()=>{try{const r=seleccionarContenedoresPacking(resultado,[...d.querySelectorAll('input:checked')].map(e=>e.dataset.contenedor));d.querySelector('[data-seleccion-resumen]').textContent='Se guardarán '+r.lineas.length+' líneas · '+r.unidades+' unidades · '+r.embarques.join(', ');alCambiar(r);}catch(e){d.querySelector('[data-seleccion-resumen]').textContent=e.message;alCambiar(null);}};
 d.addEventListener('change',pintar);panel.append(d);pintar();
}
