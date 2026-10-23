# Versión 61 · correo de recepción y bitácora

## Orden del correo

El correo se presenta en este orden: saludo y presentación; enlaces de Drive; fotos de prerecepción/descarga; observaciones de recepción; tablas de novedades con sus fotos; otras evidencias seleccionadas; ubicación y distribución de contenedores; documentos finales, despedida y firma.

Las novedades conservan su clasificación histórica y el alcance del packing list o embarque que se está reportando. Las fotos de prerecepción ya no aparecen al final. En **Imágenes del correo** puedes seleccionar imágenes y usar **↑ / ↓** para ordenar las seleccionadas dentro de la prerecepción o de las demás evidencias. Las categorías de novedades siguen mostrando cada foto junto a su tabla. Máximo: 12 miniaturas por mensaje, con prioridad a las novedades en el modo recomendado.

Las imágenes cargadas desde el correo se agregan a la selección al cerrar el registro de fotos, hasta el límite disponible. Si una imagen fue asignada a otro embarque, solo aparecerá en el correo de su destino. Quitarla del mensaje conserva la evidencia guardada.

## Editar sobre el correo

1. Abre la recepción → **Recepción actual → Informes → Correo final editable** y elige su packing list o embarque.
2. Toca el saludo, la presentación, las observaciones, la despedida o la firma dentro del correo y escribe allí mismo. Los textos editables tienen un borde discontinuo. **Otros campos de redacción y datos operativos** conserva el formulario alternativo.
3. Pulsa **Guardar correo editado**. Las tablas y cantidades proceden de los conteos; no son campos editables del correo.
4. **Imágenes del correo** abre la selección y registro de fotos. **Copiar con miniaturas** prepara las fotos seleccionadas para la respuesta manual. Las descargas y controles de Drive se agrupan en herramientas secundarias.

Los operarios pueden preparar textos y fotos mientras la recepción esté abierta. El nuevo permiso **Preparar la redacción y fotos del correo de recepción** se puede configurar desde ADMIN. El supervisor conserva los destinatarios, asunto, hilo Gmail, agrupación, cierre y envío. El servidor valida esa separación; no depende solo de ocultar botones. Los envíos archivados o en proceso conservan su texto original.

La redacción se almacena como texto validado y selección de IDs, sin guardar HTML libre, imágenes pegadas, miniaturas o copias del buzón en MySQL. Dos personas con el mismo borrador antiguo no pueden sobrescribirse sin actualizar.

## Fotos y envío manual

Una foto guardada localmente puede mostrarse en el borrador y copiarse como miniatura aunque la copia a Drive siga pendiente. Si la miniatura se obtiene, la copia manual incorpora su JPEG y omite el aviso técnico de Drive pendiente. Si no se obtiene, informa que hay una vista no disponible y conserva la alternativa para revisar el original.

Gmail u Outlook pueden retirar imágenes al pegar. Revisa visualmente la respuesta antes de enviarla y usa **Descargar miniaturas** para insertarlas desde el editor de correo si hace falta. Los originales conservan sus permisos privados. El envío automático mantiene su comprobación de fotos confirmadas en Drive y la conexión Google propia autorizada; esta versión no modifica Apps Script ni resuelve por sí sola una autorización Gmail pendiente.

## Cantidad, pallet y posición

**Corregir conteo** incorpora la posición final junto a la cantidad y al pallet. Si la ficha tiene sugerencias de Depot, se ofrecen como apoyo y puedes editar el valor. La corrección conserva el original y su reversa, y registra un conteo sustituto sin duplicar unidades.

Tocar una posición sugerida solo rellena la posición: no escribe DP en el pallet. El pallet sigue siendo un campo de escritura con la validación operativa existente (ejemplos: E01, C12, B04.1). La posición física asignada no cambia las ubicaciones del catálogo de Depot.

Al capturar, corregir el conteo o asignar la posición final, **Nave, Calle/Literal, Columna y Nivel · Depot** permite escribir los segmentos por separado. Por ejemplo, Nave BM, Calle/Literal A, Columna 10, Nivel 1 se guarda como `BM-A-10-1`. También puedes escoger una sugerencia completa y editarla. No se sustituye el identificador del pallet.

El CSV oficial de cantidades coloca ese valor en columnas separadas:

| Posición guardada | NAVE | CALLE / Literal | COLUMNA | NIVEL |
|---|---|---|---|---|
| BM-A-10-1 | BM | A | 10 | 1 |

El modelo oficial llama **CALLE** a la columna de Literal. Conserva los ceros iniciales, el pallet y la cantidad vigente; descarta el conteo anulado. Si no se confirmó una posición completa, se señalan los campos pendientes y el archivo incompleto queda como Excel para revisión. Las sugerencias del catálogo no se asignan automáticamente a las cantidades físicas.

El selector **Tipo de fotografía** del destino por foto o lote ahora comparte la misma lista que la captura y organización, incluida **Prerecepción · descarga del contenedor**. Al seleccionarla se usa contexto de recepción sin SKU ni bulto específico, y se conserva el embarque o packing list elegido.

En el correo del supervisor, abre **Correo original de Gmail y distribución por contenedor → Comprobar mi cuenta de envío**. Comprueba la identidad autorizada y el puente de esa misma cuenta sin enviar mensajes. Antes de programar el envío final siguen las comprobaciones de fotos, permisos, destinatarios y confirmación de Google. La consulta no habilita una API o permiso pendiente por sí sola.

## Bitácora actualizada

La bitácora permite **Buscar código** completo o parcial, combinarlo con estado y mostrar anulados. La búsqueda filtra los datos ya consultados; no hace una consulta por tecla.

Después de anular, corregir o reclasificar, se consultan los SKU y eventos vigentes para actualizar cantidades, indicadores, historial y bitácora inmediatamente. Se conserva el filtro escrito. **Actualizar bitácora** permite repetir la consulta; los cambios de otro dispositivo también refrescan la bitácora cuando está abierta y cambia la información observada. No se agregan temporizadores nuevos de consulta continua.

## Validación y pase

Batería general final: 1.371 pruebas aprobadas. MySQL exclusivo de revisión: siete pruebas aprobadas, incluidas redacción operativa y ediciones simultáneas. Verificación Chromium con recepción y fotos ficticias: edición directa y orden de fotos en escritorio/390 px; corrección con posición y anulación con actualización inmediata; filtros de bitácora y restricciones del operario. Comprobación adicional del registro de fotos desde el correo, su inclusión y preparación de miniaturas. Tras ampliar la revisión: 25 pruebas del remitente y conexión personal, pruebas del desglose CSV BM/A/10/1 y verificación de los selectores de prerecepción y la corrección por segmentos en navegador.

El pase usa `scripts/actualizar_produccion.sh` con el commit completo indicado en la entrega. Hace el respaldo privado y puede pausar brevemente el servicio. No necesita cambios de esquema, Apache, TLS ni Apps Script. Después recargar con Ctrl+F5 y validar con un supervisor y un operario en una recepción de prueba. Esta revisión no altera automáticamente las cantidades o el alcance de packing lists existentes en producción.
