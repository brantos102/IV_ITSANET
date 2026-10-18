# Recepciones, fotos e informes de producción

Candidato `itsanet-20261017-recepciones-fotos`, interfaz `20261017-39`.
Las mejoras de la versión 40 se describen en [Supervisión, correo y pruebas](SUPERVISION_CORREO_Y_PRUEBAS_40.md). La versión instalada en producción sigue siendo la 39 hasta un nuevo pase.

Complementa y actualiza las instrucciones anteriores de correo, carpetas y vista previa.

## Cuenta del supervisor y confirmación del correo

Los correos salen desde la cuenta personal del supervisor solicitante. Cada cuenta autoriza Google y su despliegue una sola vez en **Mi cuenta y correo**. La clave compartida se guarda cifrada en el servidor; no se solicita por envío ni se incorpora al código publicado. Distintos supervisores conservan conexiones independientes. Cambiar una dirección en un formulario no cambia la cuenta que ejecuta Apps Script.

En cada proyecto autorizado actualizar **Proxy.gs y Servidor.gs** del repositorio y publicar **Nueva versión del mismo despliegue /exec**, conservando propiedades privadas, `Clientes.gs`, permisos y HMAC. `Servidor.gs` incorpora la capacidad `fotosSkuSimples` y la lectura privada de miniaturas. Si falla la clave, guardar la misma `SERVIDOR_HMAC` del proyecto en su conexión; no generar otra por cada correo. Verificar desde la cuenta propietaria del despliegue, con **Ejecutar como: Yo**. El supervisor necesita acceso a la carpeta matriz compartida.

Una discrepancia de HMAC pausa la tarea; no continúa sumando reintentos automáticos. En **Entregas → Revisar Drive y fotos** se muestran el avance, responsable y cada error. **Copiar pendientes desde mi cuenta** verifica la conexión del supervisor y permite recuperar sus fotos pendientes sin cambiar conexiones base. Esto pausa el correo y requiere una confirmación posterior. Las tareas activas en otro proceso se respetan.

Con las fotos confirmadas aparece el aviso para revisar los documentos finales. **Revisar y confirmar envío desde mi correo** muestra los archivos archivados, permite editar destinatarios y exige comprobar Enviados. Conserva la versión y la identidad de entrega. Solo **ENTREGADA** con acuse del puente significa enviado; PENDIENTE/PROCESANDO no lo acreditan. Una confirmación interrumpida no se repite automáticamente.

## Fotos del SKU y vista previa

- Sin novedad: `MATRIZ / CLIENTE / MARCA / RECEPCIÓN / SKU / SKU_001.jpg`.
- Con novedad: `… / FALTANTE|SOBRANTE|PNC / SKU / SKU_001.jpg`.
- Sin carpetas `GENERAL`, `ADICIONAL` o tipos de foto debajo del SKU. Las categorías vacías no se crean.
- Fotos generales de recepción y estado final conservan su sección propia. La galería distingue el total de la selección y el avance de toda la recepción.
- La numeración es por SKU, incluso entre categorías. Reintentar conserva el archivo y su identidad; los accesos desde carpetas emitidas anteriormente se mantienen.
- Las fotos del conteo se guardan como archivos y sus referencias locales `/api/app/archivos/…`. Esto funciona también por WiFi HTTP. No se almacenan imágenes base64 en cada evento.
- Las miniaturas de Drive se leen con la conexión autorizada, a través del servidor y con sesión de la app. No se publican los originales. La caché de miniaturas ocupa como máximo 20 MiB; las imágenes originales confirmadas se retiran del almacenamiento local.
- En Windows, **Elegir archivo** adjunta la imagen tomada con Cámara de Windows o guardada en el equipo. En móviles, **Tomar foto** abre la cámara y **Galería** permite seleccionar archivos.

## Etiquetas y bultos

El literal es una letra y la numeración tiene un mínimo de dos dígitos: `A01`, `B02`, `C06`, `B10`, `A52`; a partir de cien se usa `B100`, sin truncar ni introducir ceros extra. Se imprime el código y un CODE128 con ese mismo dato. El identificador interno del bulto permanece en el registro, fuera de la etiqueta.

La vista previa se dibuja en la pantalla. Al guardar el ingreso antes del primer bulto se ofrece revisar e imprimir etiquetas. No se imprime sin confirmación. Los lotes emitidos siguen auditados y los identificadores logísticos no se reemplazan al corregir el total.

Pallet admite letras y números, punto de subpallet (`B02.1`) y guion entre bultos (`B02-B03`). No se eliminan silenciosamente caracteres ni se unen los códigos. El guion conserva una referencia conjunta: para cargar cantidades separadas a posiciones de Depot, registrar el conteo de cada bulto por separado; no se inventa un reparto de unidades.

## Excel e importación

Se protege el bloque de columnas originales: mismo orden, encabezados y datos del cliente. Los selectores muestran destinos de resultado compatibles y no permiten escribir OK Depot sobre ITEM ni Cliente sobre Descripción. Las asignaciones antiguas incompatibles se corrigen al construir el archivo. Las columnas adicionales se añaden después del bloque original y se reutilizan columnas de resultado ya existentes, incluidas cantidad de incidencia y evidencia Drive. Se elimina únicamente la fila instructiva «Espacio que llenan…»; las cabeceras reales se conservan.

**Informes → Vista previa y columnas** muestra datos reales y el mismo generador que exporta el Excel. Las incidencias llevan el tipo; su cantidad va en la columna numérica. Cada embarque conserva sus propias filas, conteos, observaciones, pallets y archivo independiente. Los informes ya archivados no se reescriben: si una versión anterior contiene datos incorrectos, reabrir y generar una versión corregida antes de enviarla. El archivo de productos maestro no se incorpora al informe del cliente.

La importación muestra los nombres de los encabezados para seleccionar SKU, cantidad, descripción y embarque. Sugiere los embarques detectados como nombre editable; no sobrescribe una edición manual. El catálogo consulta el SKU en los clientes disponibles e informa su propietario y si tiene alta confirmada en Depot, sin inventar stock para otro cliente.

En **CSV para Depot → Alta masiva de cantidades** elegir categoría `NUV` (nuevo), `DEV` (devolución) o `SCRAP`. El código debe existir en las tablas de Depot del cliente. Las unidades PNC conservan su clasificación y deben revisarse; no se convierten automáticamente en scrap. Los campos obligatorios faltantes impiden generar un CSV de carga incompleto y aparecen identificados por fila/columna.

## Editar recepción y separar embarques

En Recepciones → **Gestionar** se encuentran bultos/fotos, edición de descripción, embarques y total, retirada/separación de un embarque y acceso a la carpeta Drive confirmada. Las escrituras comprueban versión para no sobrescribir a otro supervisor.

Retirar pregunta si se debe crear otra recepción con las filas originales. Si existen conteos vigentes o evidencias vinculadas, identifica los SKU o vínculos y pide resolverlos antes: no se trasladan cantidades o fotografías por suposición ni se pierde historial. Las filas/formato retirados quedan en auditoría. En las fotos, **Editar vínculo** permite corregir SKU, clasificación, tipo y embarque, conserva el archivo y su versión anterior de vínculo; no cambia cantidades. Para editar una recepción cerrada se debe reabrir, conservando sus informes emitidos.

La actualización habilita una sola vez todas las funciones operativas de supervisión (incluida anulación de envíos pendientes). No cambia roles, contraseñas o credenciales ni otorga ADMIN. Las configuraciones base y conexiones generales continúan reservadas a ADMIN; las autorizaciones propias de Google se administran por cuenta.

## Pase y límites de comprobación

Usar el actualizador de [pase a producción](CIERRE_VALIDACION_Y_PASE.md#ejecutar-el-pase-desde-la-terminal-del-servidor), conservar datos/secretos/carpetas y coordinar una pausa de escrituras. No importar una base de desarrollo, ni ejecutar reset/clean sobre producción. Recargar las pantallas tras el pase.

Las pruebas locales y MySQL usan datos aislados; las verificaciones de Google usan dobles de prueba. No acreditan el envío de un correo real, el acceso a la matriz real ni la publicación del Apps Script de cada supervisor. Esos pasos requieren la cuenta Google autorizada y el servidor de producción.

Validación de la versión 39: `npm test`, **1.050 pruebas aprobadas**; MySQL 8.4 en base desechable, **48 pruebas aprobadas** del flujo de recepción/fotos/etiquetas y **31 pruebas aprobadas** de la revisión posterior de vínculos y cuentas (con casos compartidos entre ambos recorridos). Chromium móvil verificó foto + conteo real por HTTP, observación visible, galería, edición de vínculo sin duplicar archivo, etiquetas B01/B02 visibles, columnas protegidas y datos separados por lista, edición de recepción y confirmación editable de destinatarios. Google se simuló en esas verificaciones; no se envió correo real.
