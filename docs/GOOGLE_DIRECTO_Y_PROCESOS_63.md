# Versión 63 · fotografías, documentos y correo

## Qué cambia

- El servidor puede comunicarse directamente con Drive API y Gmail API mediante un cliente OAuth web central. Cada supervisor autoriza su correo desde **Mi cuenta → Conectar con Google**. No crea proyectos Apps Script ni publica despliegues `/exec`.
- ADMIN autoriza y selecciona una **cuenta operativa de Drive**. Guarda las fotos de las recepciones en las carpetas de cliente/marca y embarque ya configuradas. La cuenta remitente de cada supervisor permanece separada del almacenamiento.
- Las conexiones anteriores se conservan. Las recepciones, conteos, bitácora y binarios no se migran ni se eliminan para activar esta versión. Una autorización central revocada produce un error visible; no cambia silenciosamente a otra cuenta.
- La galería muestra guardado en servidor, copia en curso, organización, confirmación o error por fotografía. Actualiza el estado cada tres segundos, también para operarios. Dos trabajadores procesan reservas distintas sin bloquear el catálogo.
- La subida directa reserva el identificador Drive antes de cargar y confirma el checksum del contenido. Si se pierde la respuesta, el reintento utiliza ese mismo identificador. Los accesos a otras rutas se mantienen como atajos del mismo archivo.
- El guardado del correo acepta una actualización exclusiva de enlaces/copia Drive y regenera sus bloques desde los datos actuales. Un conteo cambiado, una evidencia retirada o una edición concurrente del borrador siguen exigiendo revisión.
- **Preparar y descargar documentos** genera o reutiliza una revisión vigente y permite confirmar los nombres antes de iniciar la descarga. Varios archivos se descargan juntos en ZIP. El modal permite seleccionar hasta 12 adjuntos vigentes del mismo grupo; rechaza documentos ajenos, obsoletos o nombres repetidos. Los nombres de salida no modifican los archivos históricos.
- El envío directo compone un MIME con miniaturas incorporadas, enlaces a los archivos confirmados y los Excel seleccionados. La respuesta verifica el mensaje y el hilo original del buzón propio. Un envío sin acuse se detiene para revisión; no se repite automáticamente. Un rechazo HTTP explícito permite recuperarlo tras corregir la autorización.
- **Administración → Procesos y errores** muestra la cola actual, fallos e intentos y un registro persistente descargable en JSON. No guarda tokens, claves, contenido de buzones ni cuerpos de correo en ese registro.

## Activar Google una vez para la empresa

1. En el proyecto de Google Cloud del cliente OAuth web, habilitar **Google Drive API** y **Gmail API**.
2. Configurar la audiencia OAuth. Una cuenta externa como `johnnybarahona51@gmail.com` necesita una audiencia que la admita; una aplicación limitada al dominio ITSANET no puede autorizarla. Durante pruebas, añadir explícitamente a los usuarios de prueba. Google puede exigir verificación para publicar permisos restringidos. El modo de prueba de Google puede hacer caducar autorizaciones; no debe confundirse con un fallo de ITSANET.
3. Registrar la URI exacta del servidor, conservando puerto y protocolo. Para el servidor mostrado en la conversación: `https://apps.flexnetuio.com:8443/api/auth/google/callback`. Debe coincidir con el acceso real de los usuarios y estar permitido por la política de Google Workspace.
4. En **Administración → Conexiones → Google central**, guardar Client ID, Client secret y esa misma URI. El secreto vacío conserva el guardado. El cliente OAuth y el secreto se configuran una vez; no se solicitan a los operarios.
5. Con la sesión ADMIN de la persona que operará el repositorio, pulsar **Autorizar mi cuenta operativa de Drive**, seleccionar su mismo correo y aceptar el permiso. Al regresar, abrir **Administración → Conexiones**, seleccionar esa cuenta y guardar. La carpeta matriz admite enlace o ID; puede quedar vacía si los repositorios por cliente/marca ya tienen su carpeta. La cuenta operativa debe tener acceso a las carpetas y archivos anteriores para continuar utilizándolos.
6. Cada supervisor inicia sesión en ITSANET con su propio usuario, abre **Mi cuenta**, pulsa **Conectar con Google** y autoriza su mismo correo. Se verifican la identidad Google y la coincidencia con la ficha local. Esto no cambia roles, no habilita usuarios nuevos y no concede acceso a buzones de otros supervisores.
7. Comprobar Gmail desde Mi cuenta. En una recepción de prueba, registrar una fotografía y esperar la confirmación Drive. Preparar el documento, descargarlo y revisar sus cantidades. Comprobar carpetas, elegir el correo original si procede, revisar destinatario/adjuntos y confirmar el envío.

Permisos: Gmail solicita `gmail.readonly` y `gmail.send`; no marca mensajes como leídos, no archiva ni borra correos. La cuenta operativa solicita Drive para acceder a los repositorios existentes y organizar sus archivos. Los refresh tokens se cifran con la clave privada de integraciones del servidor. El callback usa PKCE, cookie HttpOnly, estado de un uso y coincidencia de cuenta y sesión.

El servidor no crea automáticamente permisos públicos en Drive. ADMIN debe compartir el repositorio con las personas que deban abrir los enlaces. Las miniaturas se incorporan al correo y no dependen de que Gmail pueda cargar una imagen privada desde una URL externa.

La exportación opcional a Google Sheets conserva la vía anterior cuando está configurada. La vía directa prepara los informes Excel revisados; si se solicita Sheets sin un puente compatible, lo indica antes de enviar y no omite esa exportación silenciosamente.

## Flujo diario

1. Elegir embarque y tipo de fotografía; revisar miniatura y destino; guardar.
2. La fotografía queda registrada en servidor. El aviso distingue este guardado de su confirmación en Drive. Los reintentos conservan el archivo y su identidad.
3. Si aparece error, revisar el archivo indicado y su causa. **Recuperación y organización** reúne la recuperación del navegador, los reintentos y la actualización de carpetas. ADMIN dispone del monitor global.
4. Preparar el correo, seleccionar fotos, revisar observaciones y novedades. **Comprobar carpetas e imágenes** comprueba la carpeta y sus enlaces de embarques, sobrantes, faltantes y PNC.
5. Preparar y descargar documentos; confirmar los nombres; revisar los Excel. Seleccionar los adjuntos vigentes que deban enviarse y guardar.
6. Revisar el ejecutivo destinatario y el hilo de Gmail. Confirmar el envío. **Entregas** muestra el acuse de Google o una revisión pendiente. La programación no se presenta como un envío confirmado.

## Diagnóstico

| Código/estado | Revisión |
| --- | --- |
| `GOOGLE_AUTORIZACION` | Reconectar la cuenta que perdió o revocó el permiso. |
| `GOOGLE_PERMISOS` | Revisar los permisos aceptados, la política Workspace y el acceso al repositorio. |
| `GOOGLE_API_DESACTIVADA` | Habilitar la API en el proyecto del cliente OAuth utilizado. |
| `GOOGLE_CUOTA` | Esperar el reintento; revisar cuotas si persiste. |
| `DRIVE_CARPETA_DUPLICADA` / `DRIVE_RUTA_CAMBIO` | Revisar la carpeta antes de continuar; no se elige arbitrariamente una ruta. |
| `DRIVE_CHECKSUM` | Conservar el original y comprobar integridad; no se confirma una copia distinta. |
| Correo en revisión sin acuse | Comprobar Enviados antes de decidir una recuperación. |

El monitor conserva la secuencia desde la instalación de esta versión. Las incidencias de las colas anteriores también aparecen en el estado actual. No inventa eventos históricos que no habían sido registrados.

## Actualización y alcance de las pruebas

Usar `scripts/actualizar_produccion.sh` con el commit completo probado. El actualizador realiza respaldo privado antes de cambiar de código, respeta la configuración del servicio y comprueba el arranque. No ejecutar pruebas ni comandos que creen/eliminen tablas sobre producción.

Las pruebas automatizadas aíslan bases de datos y simulan respuestas Google. La aceptación de navegador verifica carga local, alertas, cambios de estado, edición, selección de imágenes, descarga real de Excel con nombre editable y monitor ADMIN. Los accesos y envíos con cuentas corporativas requieren la autorización anterior y deben comprobarse en el servidor real. Esta entrega de código no acredita un envío real a un ejecutivo ni un despliegue en el servidor corporativo.
