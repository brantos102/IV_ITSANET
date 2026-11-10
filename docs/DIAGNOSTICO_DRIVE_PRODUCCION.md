# Fotos pendientes y errores de Drive

La carpeta `PRE-INGRESO` se crea al subir la primera evidencia que la necesita.
No es necesario crearla manualmente antes de iniciar una recepción. Su ausencia
después de un error no basta para identificar la causa del fallo.

Un HTTP 404 de Drive significa que la cuenta consultante no puede encontrar el
recurso. Puede corresponder a un recurso inexistente o a uno al que esa cuenta
no tiene acceso. También es la respuesta normal al consultar un ID reservado
antes de crear su archivo o carpeta. No se deben borrar reservas ni generar IDs
alternativos como solución general: eso puede duplicar las evidencias.

## Comprobación en producción

`scripts/diagnosticar_drive_produccion.py` no importa la aplicación ni ejecuta
migraciones. Usa una transacción MySQL de solo lectura y consultas GET de
metadatos a Drive; no crea, sube, mueve ni elimina archivos. Si el token venció,
lo renueva solamente en memoria ante el endpoint de OAuth, sin modificar las
credenciales guardadas. El informe excluye tokens, secretos y cuerpos de error.

La consulta muestra el código instalado, los estados de la cola, la cuenta y
las carpetas seleccionadas, los IDs reservados y la integridad de los originales
locales mediante tamaño y SHA-256. Se limita a 100 pendientes y 30 recursos
remotos, con un presupuesto de 45 segundos antes de iniciar otra consulta.
Las lecturas en curso pueden terminar después de ese presupuesto.

Con `--verificar-archivos`, también consulta los IDs de las fotos: visibilidad,
papelera, tamaño y checksum informado por Google. El límite sube a 80 recursos
con el mismo presupuesto de tiempo. El campo `tamanoRemotoCoincide` compara
solo el tamaño con SQL; no es una validación binaria del SHA-256 original.

El servicio sigue trabajando mientras se revisa: un original local ausente
puede haber sido depurado al terminar su copia después de la captura SQL. Ese
resultado requiere verificar el estado actualizado; no demuestra pérdida por
sí solo. Tampoco un GET correcto acredita que un POST posterior vaya a funcionar.

## Tratamiento del error original

Al crear una carpeta o un acceso directo, el sistema confirma el ID reservado
si se pierde la respuesta. Si la confirmación tampoco encuentra el recurso,
ahora se conserva el error de creación original. Antes, un rechazo como 403
podía quedar oculto por el 404 de esa consulta de confirmación. El error incluye
método, servicio y motivo estructurado de Google, sin copiar el cuerpo remoto.

Esta corrección mejora el diagnóstico. No restaura por sí sola permisos,
carpetas eliminadas ni almacenamiento agotado. La causa del incidente debe
confirmarse con el estado real del servidor y de la cuenta operativa.

## Identificadores de accesos directos

`files.generateIds` admite dos tipos: `files` (valor predeterminado) y
`shortcuts`. Para crear `application/vnd.google-apps.shortcut`, se debe pedir
`type=shortcuts`. El adaptador anterior omitía ese parámetro al reservar atajos,
por lo que reservaba IDs de archivos normales. El posterior error de creación
podía terminar presentado como el 404 de confirmación explicado arriba.

La corrección usa IDs de tipo `shortcuts` y reservas de atajos con una clave que
incluye el tipo. Antes de generar uno nuevo, busca un atajo existente al mismo
original en esa carpeta y lo adopta. Conserva las reservas anteriores para su
trazabilidad y mantiene intactos los IDs de fotos y carpetas. No borra ni vuelve
a subir el archivo original para resolver este problema.

Contrato publicado por Google en su documento de descubrimiento:
[files.generateIds, parámetro type](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/generateIds).
La misma definición está en
[google-api-go-client/drive/v3/drive-api.json](https://github.com/googleapis/google-api-go-client/blob/main/drive/v3/drive-api.json).

Si una foto vuelve a la cola para terminar de organizar sus rutas después de
confirmar su copia, ahora también conserva su original local. La limpieza se
realiza al confirmar `COPIADA` o al completar una eliminación solicitada.

## Prevención y recuperación

1. Antes de cambiar una cuenta o repositorio, verificar el ID de la carpeta y
   el acceso con la misma cuenta operativa usada por el servidor.
2. En pruebas, validar una recepción nueva que cree `PRE-INGRESO`, una ruta
   existente y un reintento después de perder la confirmación. Las pruebas
   simuladas cubren esos contratos; la comprobación con Google real debe hacerse
   en una carpeta de pruebas, con autorización de esa cuenta.
3. Después de un despliegue, comprobar que una evidencia nueva llega a `COPIADA`
   y abre su carpeta correcta. El endpoint `/health` solo acredita el arranque
   de la aplicación, no el funcionamiento de la integración con Google.
4. Ante errores repetidos, revisar primero cuenta, permisos, carpeta y motivo
   original; después reintentar desde la recepción. Ese flujo conserva las
   claves de las tareas y sus reservas. No reenviar correo ni volver a cargar
   todas las imágenes para recuperar únicamente las copias pendientes.
5. Mantener los originales y el respaldo del servidor hasta confirmar su copia.
   No vaciar `data/app_archivos`, borrar filas de la cola ni crear carpetas
   paralelas para sortear el error.

El ajuste de impresión de bultos y descripción de productos no modificó el
adaptador de Drive ni la creación automática de `PRE-INGRESO`.
