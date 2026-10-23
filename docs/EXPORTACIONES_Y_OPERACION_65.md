# Versión 65 · exportaciones y operación compartida

## Qué cambia

### Excel calculable y validado

Las cantidades, precios e importes vuelven a exportarse como números reales con formatos numéricos. Los identificadores —SKU, códigos de barras, facturas, embarques, contenedores, pallets y posiciones— conservan sus dígitos y ceros iniciales como texto. No se cambia la cantidad física ni el dato original almacenado para obtener este resultado.

Las nuevas importaciones conservan tipos y máscaras de las celdas originales dentro del JSON existente: no requieren migración de esquema ni volver a cargar recepciones actuales. Para registros anteriores se recuperan las columnas numéricas conocidas desde sus campos semánticos. El Excel de revisión de Depot también tipa las cantidades, conservando los componentes de ubicación y las fechas que deben cargarse como códigos; el contrato CSV no cambia.

Antes de descargar se detectan números no finitos, caracteres XML inválidos y colisiones de nombres de hojas. Se evitan referencias de autofiltro que SheetJS genera incorrectamente con apóstrofos ASCII. El generador conserva el desglose de UBICACIONES y la asignación por fila de la versión 64. Un valor inválido detiene la descarga con referencia a la celda; no se sustituye por cero.

Las muestras de envío, ampliado y auditable se comprueban leyendo sus XML y con openpyxl. No se recibió el archivo que Excel pidió reparar ni su registro XML de reparación: la captura no permite atribuir con certeza esa alerta concreta ni constituye una prueba con Microsoft Excel de escritorio.

**Después de actualizar, preparar una revisión nueva.** Los informes de formato 64 se conservan como históricos descargables, pero dejan de reutilizarse como documentos vigentes del generador 65. Esto evita entregar otra vez el archivo anterior después de actualizar el código.

### Nombres y selección de documentos

Preparar otro formato añade sus documentos vigentes a la selección; no reemplaza el nombre de otro archivo. Los alias se guardan por identificador, también cuando el documento se desmarca. La descarga individual utiliza y guarda el nombre revisado. Descargar seleccionados prepara un único archivo o ZIP según corresponda.

El envío directo y el cierre de recepción, incluidos los correos separados por grupo, utilizan exactamente los documentos elegidos y sus nombres finales. No cambian los binarios ni los nombres del archivo histórico. Se conservan los controles de pertenencia, revisión vigente, nombres repetidos y permisos. Un borrador puede no tener adjuntos; un envío requiere al menos uno. Si cambian cantidades o evidencias, los documentos obsoletos requieren regeneración y revisión.

### Etiquetas y bultos

- La etiqueta 100×50 mm conserva su diseño. La de 100×150 aprovecha el espacio con cliente, marca, recepción, rótulo, barras y número de bulto sobre total.
- Se puede elegir una sección: por ejemplo `1-10,15,20-25`. La selección no cambia el total físico ni renumera los bultos. Se aplica a PDF/navegador, ZPL y puente de impresión.
- Para corregir 70→50, abrir **Corregir total**, indicar el motivo y confirmar la consolidación. Los finales vacíos se archivan lógicamente conservando ID, rótulo e historial de impresión. Volver a ampliar reactiva sus mismas identidades.
- Los bultos con código, fotos, cajas, pallet, observaciones o registros asociados quedan protegidos. Requieren revisar la distribución física; no se trasladan ni eliminan sus datos automáticamente.
- Una impresión ejecutable que incluya bultos fuera del nuevo total impide consolidarlos hasta resolver la cola. Un lote anterior con total distinto no se vuelve a imprimir silenciosamente. Las etiquetas sobrantes ya impresas deben retirarse físicamente al confirmar la consolidación.
- Si el guardado se rechaza, el formulario permanece abierto con los valores y el mensaje junto a Guardar.

### Actualización y coordinación

Se utiliza un canal autenticado de eventos del servidor (SSE), compartido por las vistas de una misma página. El servidor comprueba cambios confirmados en SQL aproximadamente cada 0,75 segundos por canal activo y worker; no mantiene una conexión de base ocupada durante la espera de red. Detecta cambios de otros procesos, eventos con la misma fecha y commits iniciados antes pero confirmados después. La invalidación consolida los cambios si un navegador está ocupado.

Conteos, correcciones, anulaciones, bitácora e indicadores se refrescan sin sobrescribir la cantidad, pallet, posición u observación que otra persona está escribiendo. Si el proxy bloquea SSE, se activa una consulta de respaldo cada cuatro segundos. La red o un dispositivo suspendido pueden aumentar la latencia; no existe una garantía de actualización instantánea. Se mantienen idempotencia y controles de conflicto al guardar.

Al coincidir en el mismo SKU se muestran las personas y actividades. Supervisores/ADMIN con permiso de equipo pueden consultar coincidencias globales; un operario sin ese permiso recibe únicamente la coordinación de los SKU en los que mantiene presencia propia. No se transmiten correos, tokens, contraseñas ni contenido de buzones por este canal. La presencia caduca sin modificar conteos y no constituye un bloqueo exclusivo de pallets distintos.

### Avisos operativos

La barra común incluye **Avisos**, con estado por usuario y un recordatorio de catálogo al inicio de la jornada de Ecuador. Una consulta individual de un producto no se presenta como actualización de todo el catálogo: se utiliza la constancia de una carga masiva por cliente. La actualización por otro supervisor retira el recordatorio cuando queda confirmada. Los clientes pendientes siguen identificados.

Los avisos distinguen PNC, sobrantes, faltantes y adicionales fuera del packing list. Las diferencias mientras la recepción está abierta se presentan como **provisionales**, pendientes de revisión del conteo. No se notifican como faltantes los SKU que nadie ha revisado.

Cada novedad indica si tiene fotografías de la categoría correspondiente, cuántas están registradas y cuántas esperan o tienen confirmación de Drive. Una foto genérica no se utiliza para afirmar que existe evidencia de PNC. Los filtros de tipo y de falta de fotografías se aplican en el servidor antes del límite de resultados. La vista muestra los avisos más recientes; los informes y la recepción permiten revisar el alcance completo. Marcar un aviso como revisado no cambia cantidades, no elimina la novedad y es propio del usuario; un cambio real vuelve a avisar.

## Aplicar en producción

Usar el actualizador con respaldo incluido y el commit exacto indicado en la entrega. Avisar la pausa de registros antes de cambiar el servicio. El actualizador prepara dependencias, comprueba el repositorio y realiza respaldo privado de MySQL, archivos, configuración y código anterior antes de aplicar el cambio. No usar `git reset --hard` para eludir cambios locales detectados.

No hay migración destructiva ni necesidad de volver a desplegar Apps Script. Las conexiones Google actuales se conservan. Tras actualizar, recargar computadoras y handhelds para tomar **20261023-65** y preparar nuevos informes. La consulta de respaldo permite continuar si SSE no atraviesa el proxy.

## Revisión operativa después del pase

1. Exportar una revisión nueva y comprobar SUMA sobre cantidades e importes; verificar códigos con ceros y conciliación de físicos, conformes y PNC. Abrirla en el Microsoft Excel utilizado por la operación.
2. Renombrar un informe ampliado; preparar el de ejecutivo; comprobar que ambos alias persisten y solo los marcados se adjuntan.
3. Previsualizar dos etiquetas de cada tamaño e imprimir una selección pequeña con los números originales.
4. Probar una consolidación autorizada de bultos vacíos y verificar que las evidencias de los bultos usados siguen intactas.
5. Con dos usuarios de prueba, registrar/corregir un conteo y verificar bitácora e indicadores. Confirmar que una entrada sin guardar del otro usuario permanece en su ficha.
6. Revisar Avisos, las coincidencias de SKU, el recordatorio del catálogo y una PNC con/sin evidencia. No se enviaron correos reales en las pruebas de esta entrega.
