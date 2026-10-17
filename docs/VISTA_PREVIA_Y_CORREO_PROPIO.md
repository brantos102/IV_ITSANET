# Vista previa y correo propio del supervisor

Versión `20261017-37`, etiqueta `itsanet-20261017-previa-y-correo`.
Conserva datos, documentos archivados, claves y la versión anterior.

## Ver el documento antes de enviarlo

En Recepción actual → Columnas del informe:

1. Elegir el packing list. Cada lista corresponde a su propio archivo.
2. Revisar **Así quedará el archivo**. La tabla muestra los datos reales actuales,
   sus encabezados y números de fila de Excel. Cambiar la asignación de una columna
   actualiza la tabla inmediatamente. «Sin asignar» conserva su celda original.
3. Elegir formato original o con columnas adicionales para comparar ambos.
   La opción es de vista previa; al exportar o enviar se confirma el formato.
4. Usar Anterior/Siguiente para recorrer las filas y **Actualizar registros** para
   traer los últimos conteos. Una lista sin filas puede mostrar un ejemplo
   explícitamente ficticio; nunca se guarda ni se envía. Un fallo de lectura no se
   disfraza con ejemplos. Las fórmulas se conservan como en el Excel; el navegador
   no sustituye su motor de cálculo.
5. Guardar columnas de esta lista. Dos campos no pueden escribir en la misma
   columna. Revisar otra lista o cerrar.

La vista usa la misma función que genera la hoja del XLSX. No reserva un número de
informe, no modifica conteos y no envía correo. Los enlaces Drive apuntan a las
carpetas confirmadas del SKU. La tabla tiene desplazamiento horizontal en móviles.

## Por qué editar el remitente no resuelve el error Google

MailApp envía desde la cuenta que ejecuta la aplicación web publicada en Google.
Escribir `fmorales@itsanet.com` sobre un `/exec` desplegado por otra cuenta no
transfiere esa autorización. El mensaje de cuenta distinta significa que el
puente no confirmó a ese remitente; no demuestra por sí solo cuál es su dueño.

La clave HMAC autentica a ITSANET frente al proyecto Apps Script. No elige el
remitente de Gmail. El error «no coincide con SERVIDOR_HMAC» exige usar exactamente
la misma clave privada en el proyecto correspondiente y en su conexión guardada.
No se necesita una clave nueva si la existente está bien configurada.

## Autorizar el correo propio una sola vez

El supervisor puede configurar **solo su conexión** en Inicio → **Mi cuenta y
correo → Mi correo de informes**. ADMIN conserva Depot/WMS, OAuth, repositorios,
política general y conexiones de otras personas.

1. Iniciar ITSANET con la cuenta del supervisor correcto. Su dirección aparece
   vinculada a la ficha y no se puede suplantar desde el formulario. Si la ficha
   tiene una dirección incorrecta, ADMIN debe corregirla primero.
2. Abrir Apps Script con esa misma cuenta Google. Para `fmorales@itsanet.com`,
   publicar desde esa cuenta su propio proyecto o despliegue autorizado; no copiar
   la URL de otro remitente y cambiar solo el texto del correo.
3. El proyecto necesita Proxy.gs, Clientes.gs y Servidor.gs actuales,
   `CARPETA_EVIDENCIAS` compartida con esa cuenta y `SERVIDOR_HMAC`. Ejecutar
   `verificarGoogleServidor` y aceptar los permisos.
4. Publicar como aplicación web, **Ejecutar como: Yo**, con acceso para las
   solicitudes firmadas del servidor. Al actualizar código, publicar **Nueva
   versión** del despliegue. Copiar la URL completa terminada en `/exec`.
5. En Mi correo de informes, ingresar esa URL y la misma HMAC del proyecto.
   **Verificar y guardar mi conexión** comprueba cuenta y Drive antes de reemplazar
   la configuración. Una clave vacía conserva la propia que ya está guardada;
   una conexión nueva requiere su clave. No se heredan secretos de otras cuentas.
   Un error conserva la conexión anterior y no envía documentos.

Esta versión del servidor no cambia el código de Apps Script respecto a la 36.
Si el puente de esa cuenta ya tiene esa versión y autoriza correctamente, se
reutiliza. No hace falta republicarlo ni rotar HMAC por instalar esta mejora.

## Confirmación del envío final

Un rechazo de HMAC o cuenta Google pausa el envío en REVISION, con motivo
CONEXION_RECHAZADA. Conserva el historial de intentos y no reintenta indefinidamente.
Las entregas antiguas con ese error se pausan cuando el trabajador las revisa;
«Reintentar» tampoco permite saltarse la confirmación. Los fallos temporales de
red conservan sus reintentos con el mismo identificador.

Después de verificar la conexión propia y confirmar las fotos en Drive, el
supervisor remitente ve un aviso en Inicio, Recepciones, Validación, Mi cuenta o Administración:
**Informe pendiente de tu confirmación**. Incluye una acción visible sin tener
que desplazarse arriba. Los avisos se consultan cada 30 segundos y el panel de
entregas se actualiza cada 5 segundos.

**Revisar y confirmar envío desde mi correo** vuelve a comprobar la cuenta Google,
las fotos y la vigencia del informe. Muestra remitente, destinatarios, versión y
nombres de los documentos finales. Exige confirmar que no se enviaron antes y
anotar el motivo; solo entonces se programa el envío. Corregir o guardar la
conexión no manda el correo por sí solo. La confirmación interrumpida de un correo
que pudo enviarse mantiene la revisión para evitar duplicados.

Al recibir la confirmación de remitente y destinatarios desde Google, se muestra
**Correo enviado y confirmado** al remitente. Los avisos no cambian la cuenta de
otro supervisor ni convierten automáticamente una entrega pendiente en enviada.
El supervisor que asuma un informe anterior de otra cuenta debe abrirlo y
confirmar expresamente el envío desde su correo autorizado.

## Validación y pase

Las pruebas cubren coincidencia de vista previa/XLSX, separación de listas,
permisos de conexión propia, claves cifradas, rechazo sin reemplazo, pausa por
HMAC y confirmación antes del envío. Se comprueba MySQL en una base desechable y
la interfaz móvil. Resultado: 1.008 pruebas de la suite y 37 de integración
MySQL aprobadas; compilación y revisión móvil verificadas. Las pruebas de Google usan dobles; la entrega real debe
confirmarse en el entorno empresarial.

Usar el procedimiento de [CIERRE_VALIDACION_Y_PASE.md](CIERRE_VALIDACION_Y_PASE.md)
para instalar esta etiqueta conservando las recepciones existentes. No importar
las bases de pruebas ni compartir contraseñas, HMAC o secretos en el chat.
