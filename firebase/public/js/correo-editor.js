/** Edición en contexto: se guarda texto; las cifras y tablas siguen calculadas. */
const etiquetas={saludo:'Saludo',introduccion:'Presentación de la recepción',notas:'Observaciones de recepción',despedida:'Despedida',firma:'Firma'};
export function iniciarEditorCorreo(raiz,campos,{editable=true,alCambiar=()=>{},alAvisar=()=>{}}={}){
 for(const el of raiz.querySelectorAll('[data-correo-campo]')){
  const k=el.dataset.correoCampo;if(!etiquetas[k])continue;
  if(!editable)continue;
  el.textContent=campos[k]||'';el.contentEditable='plaintext-only';el.classList.add('correo-texto-editable');
  el.setAttribute('role','textbox');el.setAttribute('aria-label',etiquetas[k]);el.setAttribute('aria-multiline','true');el.dataset.placeholder='Escribe '+etiquetas[k].toLowerCase()+'…';
  el.addEventListener('input',()=>alCambiar(k,el.innerText.replace(/\r\n?/g,'\n').replace(/\u00a0/g,' ')));
  el.addEventListener('paste',ev=>{if(ev.clipboardData?.files.length){ev.preventDefault();alAvisar('Usa Agregar fotos para registrar y seleccionar las imágenes del correo.');}});
  el.addEventListener('drop',ev=>{if(ev.dataTransfer?.files.length){ev.preventDefault();alAvisar('Usa Agregar fotos para registrar y seleccionar las imágenes del correo.');}});
 }
}
