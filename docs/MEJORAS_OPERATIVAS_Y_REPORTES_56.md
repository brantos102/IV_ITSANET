# Informes, evidencias y operación · versión 56

19/10/2026, Ecuador. Interfaz `20261019-56`.
Etiqueta de publicación: `itsanet-20261019-mejoras-operativas-56`.

## Excel y correo para el cliente

Los nuevos Excel ya no añaden comentarios emergentes a la columna de validación
Depot ni mezclan su explicación técnica con las observaciones del operario.
Se mantienen los valores `ok`, `N/D`, `INACTIVO` o `PENDIENTE` que corresponden al
catálogo. El correo informa los productos que requieren revisión, sin incluir
el párrafo técnico sobre la hoja MAESTRO o el mecanismo de consulta.

Los formatos de envío al cliente incluyen **ADICIONALES** cuando corresponde,
con productos no declarados y sobrantes, cantidades y enlaces de sus evidencias
confirmadas. El sobrante de un SKU declarado ya está incluido en la cantidad
física de su packing list: la hoja adicional lo identifica y advierte que no se
sume de nuevo. Los vínculos pertenecen al contexto de lista o embarque elegido.
Una carpeta no confirmada no se convierte en una URL inventada.

El formato auditable incluye todas las listas disponibles, sus hojas de detalle,
**ADICIONALES**, **BITACORA** y un **RESUMEN** visible por lista, con sus cantidades.
No genera una hoja AUDITORIA; los eventos y la auditoría de MySQL se conservan.
Cuando las filas permiten identificarlo, PRINCIPAL se muestra acompañado de sus
embarques, por ejemplo **PRINCIPAL - RAISZ04453**. El identificador interno sigue
siendo el mismo y no se alteran vínculos históricos.

El generador se identifica como versión 56 para no reutilizar un archivo anterior
con el mismo contenido pero otra estructura. Después de actualizar, generar un
**informe actualizado** desde Informes; los documentos archivados anteriormente
no se reescriben. Una vez generado el nuevo, se reutiliza mientras no cambien sus
datos o metadatos.

En el correo, **Verificar carpeta de recepción** crea/comprueba el directorio
mediante la conexión del responsable. Después de confirmar el enlace, también
puede aparecer aunque el correo no lleve fotos. Si no existe una carpeta propia
del grupo, se identifica el acceso como **carpeta general de la recepción**.
No confirma un envío ni cambia permisos de Google. Los datos técnicos de la
validación siguen disponibles internamente para trazabilidad.

## Elegir cómo agrupar el envío

En **Organizar correos de la recepción**, el supervisor puede elegir:

- **Por packing list:** un correo por archivo de origen, que puede contener
  varios embarques. Consolidar varios embarques en ese correo exige confirmación.
- **Por embarque:** un correo por embarque; si un SKU está compartido, se revisa
  el reparto de cantidades, calidad, pallets y observaciones.
- **Recepción consolidada:** un correo y un Excel con las hojas de todos los
  packing lists y sus adicionales. Requiere confirmar la inclusión de los
  embarques y documentos indicados.

La agrupación del correo no mueve las fotos de Drive. Cada imagen conserva su
embarque o su condición explícita de General. Las revisiones de correos ya
emitidos permanecen archivadas y no se reenvían por cambiar el plan.

Al adjuntar un packing list se examinan todas las filas de la hoja seleccionada.
Los embarques de su columna se detectan y muestran en la vista previa; el nombre
editable de la lista se propone con códigos separados por comas. Si el archivo
trae varias hojas, se conserva la selección de hoja y mapeo de columnas: no se
mezcla automáticamente una hoja MAESTRO con una hoja de packing. El nombre de
lista conserva su límite de 40 caracteres; los embarques detectados se guardan
por separado en las filas y la recepción.

## Sugerencias al escanear

La comparación contempla transposiciones y hasta dos cambios en códigos del
packing list. Para `2GP845205B` se propone `2GP845025B` cuando está en la lista,
priorizando códigos de esta recepción y coincidencias de los mismos caracteres.
Ninguna sugerencia sustituye el código ni registra unidades automáticamente.

El cuadro incluye **Ninguno coincide · usar [código leído]** cuando la lectura
contiene un código simple identificable. Se puede consultar ese código y, si no
está declarado, registrar el adicional/sobrante por el flujo habitual. Las
lecturas compuestas que no permiten separar una pieza válida requieren corregir
la lectura antes de crear un adicional.

## Bultos y cámara

Abrir un bulto ya no inicia el lector. **Activar cámara** sirve para tomar fotos;
**Escanear etiqueta** activa expresamente la lectura del código madre. Después
de leerlo se pide confirmar el código y se detiene la lectura automática. Tomar
una fotografía no convierte un código de fondo en el nombre del bulto.

La pantalla indica la secuencia: identificar, fotografiar, revisar y continuar.
El resumen incluye búsqueda por número, código o estado pendiente del bulto.
Se mantienen el guardado por unidad, la versión para evitar sobrescribir cambios
ajenos y la recuperación local de fotos pendientes. También admite arrastrar
imágenes al cuerpo de la ficha; quedan seleccionadas antes de guardarlas.

## Fotos por lote y vista previa

En **Fotos → Seleccionar fotos nuevas**, arrastrar imágenes o elegir varias
desde Galería. Cada miniatura ofrece **Elegir destino de esta foto** para indicar
embarque, packing list, SKU, bulto/caja, clasificación y tipo de fotografía.
Las imágenes no asignadas individualmente conservan la elección común del lote.
Pulsar **Guardar fotos seleccionadas** para registrar el lote.

**General · compartida entre embarques** es una decisión explícita, incluso para
el contexto de un SKU o bulto compartido. Se guarda bajo GENERALES, conservando
clasificación y contexto. Sin una decisión explícita, una foto histórica ambigua
continúa pendiente de asignación; no se distribuye por intuición.

En **Actualizar carpetas por embarque**, cada archivo muestra su miniatura y un
botón **Ver foto** para ampliarla dentro de la aplicación. En recepciones abiertas
se ofrece **Editar SKU, bulto o clasificación**, con corrección auditada. En una
recepción cerrada se mantiene la asignación de embarque sin reabrir; para cambiar
el SKU o clasificación se conserva la exigencia de reabrir y preservar el
informe original.

La falta de miniatura se distingue de la falta de guardado: si Drive ya confirmó
la imagen, se informa **Foto guardada en Drive · Abrir original**. No se pide
subirla otra vez. Las nuevas copias conservan una miniatura privada local antes
de liberar el original local confirmado en Drive. La caché está limitada a
20 MB y no almacena binarios en MySQL. Las fotos antiguas sin miniatura siguen
utilizando el puente privado o el original con la cuenta autorizada de Google.

## Cerrar desde Recepciones

En el listado abrir **Gestionar → Cerrar · correos ya enviados**. Esta opción es
para informes enviados fuera de ITSANET; no prepara ni manda otro correo.

Se requiere que las referencias estén verificadas. El supervisor confirma para
cada embarque que el correo fue enviado y que incluyó recepción y validación,
e indica cómo y cuándo se enviaron. Se registra la declaración y su autor.

Si hay una entrega automática pendiente o en revisión se cancela al confirmar
esta declaración para evitar otro envío. Si hay un correo **procesándose**, se
espera su resultado antes de cerrar de esta manera. Una pantalla desactualizada
no puede cerrar con confirmaciones de datos anteriores; repetir la misma
solicitud confirmada no duplica el cierre. No se fabrica un acuse de Google.

## Etiquetas, catálogo, clientes y menús

- **Etiqueta por código** también está en la barra del operario. Permite buscar
  el producto del catálogo y revisar unidades y copias antes de imprimir. La
  configuración de estaciones y sus tokens sigue siendo de administración.
- El catálogo se comparte entre usuarios. Las actualizaciones manuales y
  programadas utilizan una reserva común: no ejecutan simultáneamente la misma
  descarga. Una actualización completa reciente se reutiliza durante 15 minutos
  según su alcance; una respuesta parcial no se trata como catálogo completo.
- La programación automática es opcional en Administración. Su valor
  predeterminado pasa a desactivado para configuraciones nuevas; una programación
  existente expresamente guardada se conserva y puede desactivarse allí.
- En **Gestionar clientes**, elegir el cliente y después **Editar nombre y
  reglas** o **Eliminar de clientes activos**. Eliminar VENTURA/VW del selector
  no borra sus recepciones, catálogo o archivos históricos; impide crear nuevas
  recepciones con ese identificador eliminado.
- Los menús Informes, Más acciones, Acciones y Gestionar se cierran al abrir otro
  o elegir una acción. Los apartados de formularios y las guías mantienen su
  comportamiento independiente.

## Despliegue empresarial

No se cambian tablas, dependencias, puertos, HTTPS, usuarios ni claves HMAC.
La versión se publica en GitHub; el servidor empresarial requiere su propio
pase. Coordinar una pausa breve de registros y ejecutar en Linux **@apps**:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin --tags && revision_itsanet="$(git rev-parse 'itsanet-20261019-mejoras-operativas-56^{commit}')" && git show "$revision_itsanet:scripts/actualizar_produccion.sh" > /tmp/itsanet-pase56.sh && bash /tmp/itsanet-pase56.sh "$PWD" "$revision_itsanet"
```

El procedimiento existente prepara dependencias, hace respaldo privado, actualiza
el código y comprueba el servicio. No copia base, usuarios, credenciales o fotos
del entorno de pruebas. La URL sigue siendo
**https://apps.flexnetuio.com:8443/app/**. Recargar con Ctrl+F5 y generar los nuevos
informes; los Excel y correos históricos conservan su contenido original.

## Comprobaciones

Validación en SQLite, MySQL aislado y Chromium de escritorio/móvil. Se ejercitan
lotes de fotos con destinos diferentes, General explícita, vista ampliada,
cámara optativa, sugerencia transpuesta con alternativa de adicional, menús,
etiquetas del operario y cierre desde el listado. Las pruebas de Google son
simuladas; no se mandan correos ni se escribe en Drive, impresoras o MySQL
empresariales.

Resultados:

- Suite general: **1.265 pruebas correctas**.
- MySQL aislado: **43 correctas**; pasada final: **11 correctas**, incluidas
  reserva simultánea de catálogo y rechazo de un plan basado en un snapshot
  anterior al cambio de otro supervisor.
- Regresión final de API: **20 correctas y 2 omitidas** por requerir MySQL; esos
  dos casos se ejecutaron en la pasada MySQL anterior.
- Excel y gestión: **35 correctas**; formato: **21 correctas**; páginas:
  **67 comprobaciones correctas**. Compilación de recursos completada.
- Chromium y MySQL: elección consolidada, menús exclusivos, lote arrastrado con
  destinos diferentes, General explícita, organizador y vista ampliada a 390 px,
  cámara de bulto optativa, etiqueta de catálogo del operario, alternativa del
  código leído y cierre desde Recepciones de ambos embarques.

La pasada general precede al último caso añadido de snapshot; el cambio final
se verificó con MySQL y la regresión específica indicadas.
