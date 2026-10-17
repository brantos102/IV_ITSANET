# Corrección del HTTP 500 al cargar entregas

Entrega: `itsanet-20261017-mysql-entregas`. Mantiene la interfaz `20261016-35` y todas las funciones de `itsanet-20261016-correo-carpetas`.

El registro de producción del 17 de octubre identifica `sqlalchemy.exc.OperationalError`, código MySQL **1038**, «Out of sort memory», en `listar_entregas`, `app/routers/app_api.py`. La consulta ordenaba registros completos de `app_entregas`: además de las columnas pequeñas, incluía los documentos JSON con líneas de packing list, conteos y bitácora. MySQL podía agotar su memoria de ordenación incluso con pocas entregas grandes.

Guardar una conexión desde Administración recarga el listado de entregas. Por eso puede aparecer ese HTTP 500 después de guardar el puente o el acceso Google aunque el fallo registrado esté en la lectura posterior de entregas. El registro aportado no acredita un fallo OAuth ni demuestra que el correo se haya enviado.

La corrección selecciona primero los identificadores de las entregas más recientes, ordenados por fecha e identificador para resolver empates. Recupera después sus documentos por clave primaria, sin ordenar el JSON. Aplica al listado general, las entregas de una recepción, los destinatarios recientes, el enlace Drive de la galería y la consulta del cierre idempotente. Mantiene los límites, la separación por cliente, los permisos y los estados existentes.

No requiere modificar variables globales de MySQL, esquemas, credenciales, Apps Script ni archivos de recepciones para corregir este HTTP 500. La verificación de la conexión Google se realiza después y conserva sus comprobaciones de cuenta, firma y carpeta.

## Aplicar en producción

Coordinar una pausa de escritura y ejecutar en la terminal del servidor, con el usuario habitual:

```bash
cd ~/bryan/IV_ITSANET &&
git fetch origin tag itsanet-20261017-mysql-entregas &&
VERSION_ITSANET=$(git rev-parse 'itsanet-20261017-mysql-entregas^{commit}') &&
SCRIPT_PASE_ITSANET=$(mktemp /tmp/itsanet-pase.XXXXXX.sh) &&
git show "$VERSION_ITSANET:scripts/actualizar_produccion.sh" > "$SCRIPT_PASE_ITSANET" &&
bash "$SCRIPT_PASE_ITSANET" "$PWD" "$VERSION_ITSANET"
```

El procedimiento respalda la base y el almacenamiento operativo y conserva las recepciones y conexiones de producción. No importar datos de desarrollo ni ejecutar reset/clean.

## Verificar después de actualizar

1. Abrir Administración → Entregas al ejecutivo → **Actualizar entregas**. Deben aparecer las entregas con sus estados; esta consulta no envía correo.
2. Seleccionar el puente de `bespinoza@itsanet.com` y pulsar **Verificar remitente y Drive**. Revisar el resultado de esa operación.
3. En **Revisar Drive y fotos**, confirmar que la cuenta responsable sea la indicada y pulsar **Verificar y crear carpetas**. Esperar la confirmación de las copias.
4. Resolver por separado cualquier aviso de clave HMAC, cuenta ejecutora o permiso de Drive que aparezca. No generar otra clave para corregir el error MySQL.
5. Para recuperar las entregas anuladas, seguir [CORREO_Y_CARPETAS_RECUPERACION.md](CORREO_Y_CARPETAS_RECUPERACION.md), revisar primero Enviados y recuperar únicamente el informe correspondiente.

La regresión se comprueba en una base MySQL desechable: la consulta anterior falla con 1038 al ordenar documentos grandes y un `sort_buffer_size` de 32 KB; las cuatro rutas corregidas responden 200 con la misma memoria, sin cambiar variables globales. La prueba específica de MySQL se omite en SQLite y se ejecuta por separado contra MySQL.

Validación de la entrega: suite completa con 968 pruebas aprobadas y una prueba específica de MySQL omitida en SQLite; 47 pruebas aprobadas contra MySQL, incluida esa regresión. El servicio de desarrollo se reinició correctamente y respondió 200 en `/health`, autenticación local y listado autenticado de entregas. No se enviaron correos reales ni se modificó el servidor empresarial durante estas comprobaciones.
