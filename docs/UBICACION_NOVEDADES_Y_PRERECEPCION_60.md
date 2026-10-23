# Versión 60 · posición final, pallet de la novedad y prerecepción

## Operación

- Al terminar un conteo, pulsa **Asignar posición final** en la confirmación. También puedes consultar el SKU y pulsar **Posición final del pallet**. Si hay varios conteos, selecciona el pallet y packing list correctos. Operarios, supervisores y administradores pueden hacerlo mientras la recepción está abierta.
- Indica CALLEKL, PISO2, A-01 u otra posición operativa. La operación conserva unidades, pallet y autor del conteo. Registra responsable, fecha y posición anterior. Si otra persona cambia la posición mientras editas, debes actualizar antes de guardar. La posición se incorpora al informe actualizado y la bitácora.
- Para una novedad física, indica tipo, unidades afectadas y **Pallet específico de la novedad**. Si el conteo tiene un único pallet, se usa ese como referencia; si abarca B04-B05, elige uno de ellos. Para novedades en distintos pallets, registra conteos separados. La fotografía conserva ese pallet y su clasificación histórica.
- La clasificación posterior desde la bitácora también pide el pallet de la novedad. Los registros anteriores sin este dato siguen siendo legibles; no se inventa su ubicación.

## Fotos de descarga y correo manual

1. En el ingreso, pulsa **Fotos de descarga · prerecepción**. También puedes registrarlas desde el correo final, antes del cierre.
2. Elige Cámara o Galería, revisa el destino por embarque o general y guarda las fotos seleccionadas. La prerecepción documenta la descarga sin asignar un SKU ni un bulto concreto.
3. En el correo, revisa las fotos que quieres mostrar. El modo recomendado incluye novedades y prerecepción, con un máximo de 12 fotos; las novedades tienen prioridad si se supera ese límite. Puedes usar selección manual para decidir cuáles incluir.
4. Pulsa **Copiar correo con miniaturas**, abre el correo original en Gmail/Outlook, pulsa Responder y pega el contenido. Revisa imágenes, destinatarios y documentos antes de enviar.
5. Algunos clientes retiran imágenes al pegar. Usa **Descargar miniaturas**, descomprime el ZIP e inserta los JPEG desde el editor de tu correo. El ZIP incluye el HTML con imágenes incorporadas. **Descargar correo HTML** también incorpora las miniaturas disponibles.

Solo se preparan miniaturas de las fotos seleccionadas cuyo respaldo en Drive esté confirmado. Si una vista previa no se obtiene, se conserva un acceso al original desde ITSANET y se informa el fallo; ese acceso requiere una sesión de la aplicación. La descarga no convierte el acceso privado en público. No se afirma que el envío o la respuesta Gmail funcionen en producción: requieren verificar por separado la conexión y permisos propios de cada supervisor.

## Presentación para jefaturas

[Descargar HTML autónomo](descargas/ITSANET-presentacion-jefaturas-v60.html) · [ZIP con instrucciones](descargas/ITSANET-presentacion-jefaturas-v60.zip).

Seis láminas, navegación por botones o flechas, tareas por rol y ejemplo interactivo con datos ficticios. Funciona sin conexión; permite imprimir o guardar como PDF. Tras el pase, también está disponible en `/app/presentacion-jefaturas.html`.

## Datos y continuidad

No hay migración de esquema ni copia de datos. La posición se guarda en el campo existente del conteo y se audita; su cambio invalida el informe almacenado para evitar reutilizar una ubicación anterior. La relación foto/pallet usa metadatos de identidad existentes. No se guardan miniaturas en MySQL: se preparan temporalmente en el navegador (320 × 240 como máximo), con la misma cola de dos consultas simultáneas de la galería. No se alteran originales ni se genera una nueva copia binaria por indicar el pallet.

Los conteos anulados, ajenos, sin unidades, sin pallet o de recepciones cerradas no admiten esta asignación. Se conserva la validación de permisos para cierre y correo. Esta versión no corrige automáticamente el alcance del packing list de VW ni modifica las cantidades registradas en producción.

## Pase al servidor

Usar el commit completo indicado en la entrega con `scripts/actualizar_produccion.sh`. Este realiza el respaldo privado y comprobaciones del servicio; puede existir una pausa breve durante la actualización. No requiere cambios en Apache, TLS ni Apps Script. Después, recargar con Ctrl+F5 y validar con un operario y supervisor en una recepción de prueba: conteo → novedad/foto → posición → informe actualizado → copia del correo.

## Validación realizada en desarrollo aislado

- Batería general: 1.357 pruebas aprobadas. Después de los ajustes de revisión: 48 pruebas de conteos/correo y 48 de fotos aprobadas; las omitidas requieren condiciones o archivos externos.
- MySQL separado: 14 pruebas nuevas aprobadas, incluida la edición simultánea de la misma posición.
- Cola de miniaturas: seis pruebas aprobadas, límite compartido de dos lecturas y rechazo de destinos externos. Sintaxis e imports: 75 comprobaciones aprobadas.
- Navegador Chromium: operario asigna ubicación sin sumar unidades, abre prerecepción; copia prepara miniaturas JPEG, conserva un aviso por vista fallida y genera un ZIP legible. Presentación sin desbordamiento a 390 px, roles y simulación funcionales; impresión de seis páginas.
- Prueba adicional: una imagen asociada a dos pallets conserva ambos vínculos y un único archivo. No se consultaron cuentas Google reales ni producción.
