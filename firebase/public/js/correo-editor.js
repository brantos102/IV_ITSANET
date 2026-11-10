/** Cuerpo libre; los bloques de resultados se recalculan en el servidor. */
export function iniciarEditorCorreo(raiz,campos,{editable=true,alCambiar=()=>{},alAvisar=()=>{}}={}){
 raiz.contentEditable=editable?'true':'false';raiz.setAttribute('role','textbox');raiz.setAttribute('aria-label','Cuerpo completo del correo');raiz.setAttribute('aria-multiline','true');
 for(const el of raiz.querySelectorAll('[data-correo-bloque]')){el.contentEditable='false';el.classList.add('correo-bloque-calculado');el.title='Datos verificados. Puedes quitar este bloque; sus valores se editan desde el registro correspondiente.';}
 raiz.oninput=()=>alCambiar('cuerpoHtml'); // Serializar solo al guardar, para no bloquear cada pulsación.
 const archivos=ev=>{if((ev.clipboardData||ev.dataTransfer)?.files.length){ev.preventDefault();alAvisar('Pulsa Agregar fotos para registrar las imágenes, elegir su embarque y mostrarlas en el correo.');return true;}return false;};
 raiz.onpaste=ev=>{if(archivos(ev))return;ev.preventDefault();const texto=ev.clipboardData?.getData('text/plain')||'';document.execCommand('insertText',false,texto);};
 raiz.ondrop=ev=>{archivos(ev);};
}
export function leerCuerpoCorreo(raiz){
 const copia=raiz.cloneNode(true);for(const el of copia.querySelectorAll('[data-correo-bloque]')){const marcador=document.createElement('div');marcador.dataset.correoBloque=el.dataset.correoBloque;el.replaceWith(marcador);}
 copia.querySelectorAll('[contenteditable]').forEach(e=>e.removeAttribute('contenteditable'));return copia.innerHTML;
}
