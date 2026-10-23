# Recuperar fotos y una entrega pendiente

Entrega `itsanet-20261016-drive-recuperacion`, frontend `20261016-34`.

## Conexión de Google

La carpeta de Drive y el enlace del puente son campos distintos. El puente debe
ser la URL HTTPS de la **aplicación web activa**, terminada en `/exec`, copiada
de Apps Script → Implementar → Administrar implementaciones. No usar el ID del
proyecto ni un enlace `/drive/folders/…` en ese campo.

Un HTTP 404 indica que esa dirección no está disponible para el servidor; no
demuestra que falten las fotos. Confirmar el despliegue, su acceso y la URL
guardada. Verificar en el editor la función `verificarGoogleServidor` comprueba
la cuenta, carpeta y cuota del proyecto abierto, pero no confirma que ITSANET
esté usando su despliegue correcto.

Si se informa que la clave no coincide, el valor privado de `SERVIDOR_HMAC`
en las propiedades de **ese mismo proyecto** debe coincidir con el guardado para
la cuenta responsable en ITSANET. No es la contraseña del correo. No pegarlo en
el chat ni en Git. El campo secreto vacío conserva lo guardado; para corregir
una diferencia hay que actualizarlo explícitamente en el formulario.

Después de editar URL, cuenta o clave, pulsar **Guardar puente** antes de
**Verificar remitente y Drive**. La verificación y la prueba de correo rechazan
ahora una URL visible que difiere de la guardada para ese responsable, para no
probar silenciosamente un despliegue anterior.

No se ha comprobado aquí el despliegue empresarial: el proxy de esta sesión
rechazó la conexión saliente a `script.google.com` con 403. Esa restricción es
distinta del 404 observado por el servidor del usuario.

## Fotos ya tomadas

Las copias pendientes adoptan el correo responsable de la configuración actual,
conservando al usuario que tomó o registró la foto. También se puede usar el
único puente configurado cuando el responsable original era un alias local.
No se cambia el propietario de fotos ya confirmadas ni se pierde su archivo.

**Actualizar fotos y Drive** renueva la galería. Los supervisores ven el total
guardado, las copias confirmadas y las pendientes/procesando, incluidas las
panorámicas y el estado final. La primera página se actualiza automáticamente
cuando cambia el estado de Drive; al consultar páginas adicionales, el botón
permite volver a cargar la galería. No se alteran las imágenes seleccionadas
por el usuario durante la subida.

**Reintentar fotos pendientes** reutiliza sus identificadores, no sustituye
reservas activas y conserva las fotos locales hasta que Google confirme la copia.
Está permitido también para fotos de una recepción cerrada, sin reabrirla ni
cambiar conteos. Una recomendación fotográfica sigue siendo diferente de una
copia pendiente: no se exige repetir fotografías ya guardadas.

## Recuperar el informe que ya quedó cerrado

1. Corregir y verificar el puente con la cuenta responsable.
2. Abrir **Recepción actual → Entrega del informe → Revisar fotos pendientes**.
   Reintentar la copia y esperar su confirmación.
3. Si hay una sola entrega pendiente, pulsar **Reintentar esta entrega**.
   Reutiliza la misma tarea y los informes archivados.
4. Si aparece PROCESANDO, actualizar el estado y esperar. La reserva activa no
   se adelanta ni se crea una segunda ejecución.
5. Si hay varias entregas sin resolver para la misma recepción, ADMIN debe
   revisar fechas, identificadores/versiones, destinatarios y Enviados de Google.
   **Anular este envío**, con motivo, detiene solo la tarea que no corresponde;
   conserva archivos, conteos, recepción e historial. Luego reintentar la tarea
   elegida. Una revisión por envío ambiguo sigue requiriendo revisar Enviados;
   no se habilita el reenvío automático de esos casos.

El trabajador pausa los envíos pendientes en conflicto antes de contactar a
Google. Una reserva vencida que podría haber llegado al envío queda en revisión
por interrupción. Un nuevo cierre no agrega otra tarea mientras exista una
entrega de esa recepción sin resolver. Los envíos ya confirmados se conservan.

La anulación requiere ADMIN y queda auditada con usuario, fecha y motivo. Los
supervisores pueden reintentar una tarea pendiente. Ambas acciones bloquean la
recepción y leen el estado actual de la cola para evitar carreras con el
trabajador. No hace falta borrar ni recrear la recepción.

Hasta que Google confirme la entrega, PENDIENTE/PROCESANDO no significa enviado.
Las pruebas automatizadas usan respuestas simuladas de Google: no prueban un
correo real ni el acceso a las carpetas de producción.

## Verificación

La suite del proyecto completó 948 pruebas aprobadas.

Se ejecutaron 25 pruebas contra una base MySQL desechable, incluyendo fotos
posteriores al cierre, reservas activas, colas duplicadas y anulación auditada
de una sola entrega. En Chromium móvil se verificaron los contadores y el
cambio automático de SERVIDOR a DRIVE, además del menú ADMIN de remitente,
fecha e identificador, anulación con motivo y aviso de URL sin guardar.
Las peticiones externas de Google se simularon; no se enviaron correos reales.
