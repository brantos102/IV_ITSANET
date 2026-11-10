# Recuperar correo y fotografías en producción

Instrucciones actuales: [Recepciones, fotos e informes de producción](PRODUCCION_RECEPCIONES_Y_FOTOS.md).

Entrega `itsanet-20261016-correo-carpetas`, interfaz `20261016-35`.

La captura recibida muestra los envíos de VW anulados y otro envío pendiente de ISZ con una cuenta personal y error HMAC. Anular detiene el envío: pulsar Actualizar no lo reactiva. El error HMAC también impide subir fotografías y crear sus carpetas. Que `verificarGoogleServidor` termine correctamente en el editor prueba los permisos de Google, pero no que la clave guardada en el servidor coincida con la de ese despliegue.

## Preparar la cuenta responsable una vez

1. Actualizar el servidor con el procedimiento de [pase a producción](CIERRE_VALIDACION_Y_PASE.md#ejecutar-el-pase-desde-la-terminal-del-servidor). No importar recepciones de desarrollo ni reemplazar datos operativos.
2. En el proyecto Apps Script publicado por **bespinoza@itsanet.com**, actualizar los archivos [Proxy.gs](../apps-script/proxy/Proxy.gs) y [Servidor.gs](../apps-script/proxy/Servidor.gs). Conservar `Clientes.gs`, las propiedades privadas y las autorizaciones existentes. Ejecutar `verificarGoogleServidor` y después **Implementar → Administrar implementaciones → Editar → Nueva versión → Implementar**, sobre el mismo despliegue. Copiar su URL `/exec`.
3. ADMIN → Usuarios: comprobar que la cuenta responsable activa tiene `bespinoza@itsanet.com`. ADMIN → Operación → **Remitente de informes**: guardar ese correo como responsable predeterminado. No cambiar las contraseñas de Google ni las cuentas de los operadores para esta configuración.
4. ADMIN → **Drive y envío de correo**: seleccionar `bespinoza@itsanet.com`, guardar su URL `/exec` y la **misma** clave que tiene `SERVIDOR_HMAC` en ese proyecto. El campo vacío conserva la clave guardada; no corrige una clave equivocada. No pegar claves en mensajes, capturas ni Git.
5. Pulsar **Verificar remitente y Drive**. Debe confirmar la cuenta y la carpeta. Si falla la firma, corregir esa vinculación: no generar otra clave ni reintentar repetidamente antes de resolverlo.

La carpeta raíz operativa indicada es `https://drive.google.com/drive/folders/1EOCoI3eNpe9lM1iQvgMgDo7e8_oGCBtY`. Puede configurarse en Repositorios Drive o en `CARPETA_EVIDENCIAS` del proyecto. No sustituirla por una carpeta hija de otra recepción. No se vuelve pública la carpeta automáticamente; compartirla con los destinatarios autorizados según corresponda.

## Encontrar las fotos y crear las carpetas

En **Administración → Entregas al ejecutivo**, cada recepción agrupa sus envíos:

1. Pulsar **Revisar Drive y fotos**. Muestra la cuenta responsable, ruta cliente/marca/recepción, carpeta raíz, total guardado, copiado y pendiente, y el error concreto de la cola.
2. Pulsar **Verificar y crear carpetas**. Verifica la firma y cuenta del puente, crea o reutiliza la carpeta de esa recepción y programa sus fotos pendientes. Funciona también con la recepción cerrada. No crea otro cierre ni otro envío de correo.
3. Abrir **Ubicación de cada foto**. Cada imagen muestra su estado, clasificación y enlaces confirmados. La pantalla se actualiza cada cinco segundos mientras está abierta. Si dice PENDIENTE, la imagen sigue en el servidor y aún no debe darse por subida a Drive.
4. Abrir **carpeta de la recepción** desde la app para comprobar el destino exacto. La estructura es `raíz / CLIENTE / MARCA / RECEPCIÓN`; dentro hay `INFORMES`, `RECEPCION/PANORAMICA`, `RECEPCION/ESTADO_FINAL` y las categorías/unidades/listas/SKU/tipos de cada evidencia. Las rutas antiguas conservan sus enlaces. Las subcarpetas de unidades y productos se crean al copiar sus fotos.

Crear carpetas reutiliza sus nombres; reintentar conserva los identificadores de las fotos y respeta los trabajos que ya están en curso. Las fotos tomadas después del cierre se incluyen al preparar la entrega pendiente. Si cambian durante la preparación, esta se repite antes de llamar al correo. Después de una entrega confirmada, agregar fotos no reenvía automáticamente el informe.

## Recuperar el informe que debe enviarse

1. Revisar **Enviados** en las cuentas anteriores y en la responsable. Las tareas con confirmación interrumpida requieren revisión; la app no las recupera automáticamente.
2. En la recepción correspondiente pulsar **Recuperar último informe con responsable**. Verificar versión R000x, fecha, remitente, destinatarios y archivos. Para la captura recibida: revisar el R0006 de VW y el R0003 de ISZ, siempre que sigan siendo los últimos y correspondan al conteo actual.
3. Indicar el motivo y confirmar explícitamente que ese informe todavía no fue enviado. La aplicación verifica la conexión antes de cambiar la cola. Si la clave o cuenta falla, conserva el estado anterior y no envía.
4. La recuperación conserva el identificador de entrega, versión, archivos y autor original. Cambia la cuenta técnica a la responsable configurada, anula las tareas anteriores aún pendientes de esa recepción y registra quién hizo la recuperación y por qué. Rechaza informes cuyo conteo, bitácora o formato ya haya cambiado.
5. Esperar **ENTREGADA** y comprobar la bandeja de prueba `brantos102@gmail.com`. PENDIENTE o PROCESANDO todavía no significan correo enviado. No volver a cerrar o crear otro informe para forzar el envío.

Los envíos anulados y confirmados quedan en **Historial de entregas** contraído. Un error histórico de una tarea anulada no se muestra como un error activo. Los archivos de informes anteriores se conservan.

## Contenido del correo

El correo incluye cliente, marca, enlace de carpeta, miniaturas de evidencia con prioridad para panorámicas y estado final, resumen de cantidades y tablas separadas de incidencias físicas, sobrantes y faltantes. Muestra descripción, declarado, físico, diferencia, pallet, cantidad afectada y observación, además de versión y autor del cierre separados del remitente real.

Las miniaturas viajan como imágenes incrustadas `cid`, sin depender de que una imagen privada de Drive sea accesible anónimamente. Se limitan a doce y a 2 MB; todas las fotografías siguen enlazadas en Drive. Los informes mantienen un adjunto por packing list y la trazabilidad fotográfica adicional. Antes de llamar a MailApp se valida el tamaño total; el registro de intento irreversible se guarda inmediatamente antes del envío, para no repetir correos cuya confirmación se interrumpió.

Las pruebas automáticas y de navegador utilizan Google simulado. La comprobación real requiere el servidor de producción y el despliegue autorizado; publicar el código no acredita que ya se hayan creado carpetas, copiado fotos o entregado un correo real.

Validación de esta entrega: 967 pruebas de la suite completa aprobadas, 33 pruebas adicionales contra una base MySQL desechable aprobadas y recorrido móvil de Administración verificado con Chromium (historial, ubicación de fotos, creación de carpeta y recuperación con responsable). El servicio de desarrollo volvió a arrancar y respondió correctamente a `/health`.
