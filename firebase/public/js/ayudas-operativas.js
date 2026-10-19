/** Ayudas de acciones en todas las pantallas operativas; no cambia sus eventos. */
const reglas=[
 [/^(cerrar|cancelar|volver|✕|×)$|^cerrar (imagen|visor|sin guardar)$/i,'Cierra esta vista o vuelve a la anterior. Los avisos de cambios pendientes se conservan.'],
 [/guardar conteo|registrar conteo/i,'Guarda las unidades, el pallet y las fotos seleccionadas del producto. Revisa la cantidad antes de confirmar.'],
 [/guardar solo fotos|guardar fotos seleccionadas|guardar imágenes|guardar fotografías/i,'Guarda las fotos seleccionadas como evidencia. No añade unidades al conteo.'],
 [/ver fotos guardadas|^fotos$|evidencias|fotos y carpetas/i,'Abre las fotografías guardadas y su estado de copia a Drive.'],
 [/^leer ahora/i,'Intenta leer la etiqueta del encuadre con el lector y su respaldo. Consulta el producto sin registrar unidades.'],
 [/consulta previa|cacería|conteo directo/i,'Alterna entre consultar primero el producto o preparar directamente su conteo. Escanear nunca guarda unidades por sí solo.'],
 [/^tomar foto|📷 tomar foto|capturar del visor/i,'Captura una foto nueva. Revisa que se haya guardado antes de salir.'],
 [/galería|elegir archivo|elegir foto|seleccionar archivos/i,'Elige fotos existentes del dispositivo; no vuelve a cargar las evidencias que ya están guardadas.'],
 [/cámara del equipo|cámara de windows|cámara del teléfono/i,'Abre la cámara del sistema. Si vuelves con un archivo, selecciónalo desde Galería para guardarlo.'],
 [/cámara|apagar/i,'Activa o detiene el lector de códigos por cámara. Requiere HTTPS y permiso del dispositivo.'],
 [/linterna/i,'Enciende o apaga la luz de la cámara cuando el dispositivo la admite.'],
 [/guardar cambios y ver correo/i,'Guarda redacción, destinatarios y fotos del mensaje y reconstruye la vista previa con los datos reales.'],
 [/copiar correo/i,'Copia el cuerpo con formato, tablas y enlaces. El envío manual requiere adjuntar los documentos finales.'],
 [/copiar asunto/i,'Copia únicamente el asunto y los destinatarios para pegarlos en tu correo.'],
 [/registrar una foto nueva/i,'Abre el registro de evidencia de esta recepción. Al volver podrás incluir la nueva foto en el correo.'],
 [/revisar y enviar|usar este correo/i,'Continúa con la revisión y confirmación del envío o cierre. Comprueba primero asunto, destinatarios y documentos.'],
 [/ya lo envié|envío manual declarado/i,'Declara un envío realizado fuera de ITSANET. Confirma primero el mensaje en Enviados.'],
 [/actualizar datos|^↻ actualizar|^actualizar$/i,'Consulta de nuevo el estado guardado. No reenvía correos ni vuelve a subir fotos.'],
 [/catálogo/i,'Consulta o actualiza productos desde Depot según la acción elegida. Conserva los conteos de las recepciones.'],
 [/etiqueta|imprimir/i,'Revisa el formato, las unidades y las copias antes de imprimir la etiqueta.'],
 [/entregas/i,'Consulta recepciones cerradas y el estado de sus informes, fotos y envíos.'],
 [/finalizar|cerrar recepción/i,'Revisa las validaciones, documentos y correo antes de cerrar esta recepción.'],
 [/reintentar/i,'Reintenta la operación indicada. Ante un correo incierto, revisa Enviados antes de confirmar.'],
 [/retirar|eliminar|anular|borrar/i,'Revisa el elemento y la confirmación antes de retirarlo. La acción depende de tus permisos.'],
 [/no apareció/i,'Registra que se buscó el producto y no apareció. Verifica la referencia y conserva la evidencia del faltante.'],
 [/verificar|comprobar|probar/i,'Comprueba la conexión o los datos de esta sección y muestra el resultado antes de continuar.'],
 [/gestionar|más acciones|^acciones$/i,'Abre las opciones disponibles para este registro según tu rol.'],
 [/siguiente|continuar|anterior|resumen/i,'Avanza al paso indicado o consulta el resumen conservando las validaciones del flujo.'],
 [/^buscar|consultar producto/i,'Busca el código o texto indicado. La consulta no registra unidades.'],
 [/filtr/i,'Limita la lista a los criterios elegidos sin modificar los registros.'],
 [/^guardar/i,'Guarda los cambios de esta sección. Revisa los campos antes de confirmar.'],
 [/descargar/i,'Descarga el documento indicado al dispositivo. Descargar no confirma un envío de correo.'],
 [/^organizar fotos/i,'Revisa vínculos y ubicaciones de las evidencias sin volver a cargar las imágenes.'],
 [/packing list|embarque/i,'Abre la gestión del packing list o embarque de esta recepción.'],
];
export function ayudaDeAccion(texto){const t=String(texto||'').replace(/\s+/g,' ').trim();return reglas.find(([r])=>r.test(t))?.[1]||'';}
let activo=false;
export function iniciarAyudas(){
 if(activo||typeof document==='undefined')return;activo=true;
 const selector='button,summary,a.b-sec,a.b-primario,input[type=submit]';
 const aplicar=raiz=>{const elementos=[...(raiz.matches?.(selector)?[raiz]:[]),...raiz.querySelectorAll(selector)];for(const e of elementos){if(e.title&&!e.dataset.ayudaAutomatica)continue;const nombre=e.getAttribute('aria-label')||e.textContent||e.value,ayuda=e.dataset.ayuda||ayudaDeAccion(nombre);if(ayuda){e.title=ayuda;e.dataset.ayudaAutomatica='1';}}};
 aplicar(document);let programado=false;const pendientes=new Set();
 new MutationObserver(cambios=>{
  for(const c of cambios){const padre=c.target.nodeType===1?c.target:c.target.parentElement,control=padre?.closest(selector);if(control)pendientes.add(control);for(const n of c.addedNodes||[])if(n.nodeType===1)pendientes.add(n);}
  if(programado||!pendientes.size)return;programado=true;queueMicrotask(()=>{programado=false;for(const nodo of pendientes)if(nodo.isConnected)aplicar(nodo);pendientes.clear();});
 }).observe(document.body,{childList:true,subtree:true,characterData:true});
}
