# Versión 58 · Vistas previas y consulta de Gmail

19 de octubre de 2026 · Ecuador.

## Qué confirma el incidente

La captura muestra respuestas HTTP 502 para `/api/app/archivos/{id}?miniatura=1`.
Son solicitudes de **vistas previas**, no respuestas del envío de correo. No prueban
que se haya perdido una fotografía ni que haya fallado una entrega.

El mensaje adicional «Gmail no confirmó la consulta…» sí confirma que la consulta
de Gmail falló. Era un mensaje genérico: no identifica por sí solo un permiso
faltante, un despliegue desactualizado o un problema de conexión. No se ha
inspeccionado el Apps Script ni la autorización real del usuario desde este entorno.

En el código anterior, abrir el correo podía solicitar muchas miniaturas privadas
simultáneamente; cada recuperación de Google podía esperar 120 segundos y retener
una conexión MySQL. Gmail comprobaba la cuenta y consultaba los mensajes sin mostrar
progreso; la lectura de las fichas de los resultados se hacía consecutivamente.
Esto podía producir demoras y competencia por recursos. No es una medición de
saturación del servidor real.

## Corrección

- Las pantallas comparten una cola de dos miniaturas simultáneas, cargadas al ser
  visibles. Se agrupan las solicitudes simultáneas del mismo archivo.
- El servidor admite dos recuperaciones remotas de miniaturas por proceso, libera
  la conexión MySQL antes de consultar Google y usa un tiempo de lectura de 12 s.
  Un fallo espera 30 s antes de repetir la misma vista; un problema de puente o red
  también pausa las consultas del mismo propietario. Las memorias de fallos están
  limitadas a 256 entradas.
- Se reutiliza la miniatura local existente; si el original sigue local se genera
  allí sin consultar Google. La caché privada existente mantiene su límite de
  20 MiB en disco. No se crean tablas ni registros MySQL por cada visualización.
- Una miniatura temporalmente indisponible devuelve HTTP 204 y la interfaz ofrece
  **Abrir foto original**. Las autorizaciones y evidencias retiradas conservan sus
  controles 401/403/410. El aviso no vuelve a subir ni reclasifica la evidencia.
- Gmail muestra progreso y permite **Cancelar consulta y cerrar**. Cada lectura
  HTTP a Google usa 25 s; el diálogo limita su espera a 60 s. Cancelar solo
  interrumpe la lectura del navegador; la consulta del servidor termina con su
  límite. No cancela un envío ni autoriza repetirlo.
- Las fichas de hasta 15 mensajes se recuperan mediante `UrlFetchApp.fetchAll`.
  El nuevo `Gmail.gs` identifica API desactivada, permisos, política de dominio,
  autorización, cuota, buzón y respuesta inválida sin devolver cuerpos de errores,
  tokens o secretos. Los problemas de red y tiempo se distinguen en el servidor.
  Los registros técnicos muestran solo el tipo de excepción.
- El HTML usado para enviar/copiar el correo conserva sus imágenes y selección.
  Las direcciones temporales de las vistas previas solo se usan en la pantalla.

Los tiempos de envío y sus confirmaciones durables permanecen en el flujo
existente. No se modifica el contenido de recepciones, conteos ni originales Drive.

## Acceso de supervisores

**Sí: SUPERVISOR y ADMIN pueden buscar y leer el correo de su propia cuenta
Google autorizada.** OPERADOR no tiene acceso al buzón desde la app. El servidor
comprueba la cuenta del usuario y que el puente Google pertenezca a esa misma
cuenta; no permite consultar el correo de otro supervisor.

Por ejemplo, `fmorales@itsanet.com` necesita ese correo registrado en su usuario,
una conexión Google propia y Gmail autorizado en ella. Iniciar sesión en ITSANET
no concede acceso a Gmail automáticamente. Si ese correo no dispone de buzón
Gmail/Google Workspace, esta conexión no puede abrir su correo de otro proveedor.

El supervisor no instala servidores ni claves HMAC en su PC o móvil. La clave
compartida pertenece a su conexión de servidor y se conserva cifrada allí. No se
solicita su contraseña Gmail. El correo completo y sus adjuntos se abren en Gmail;
la app muestra una vista de texto y permite seleccionar el hilo para responder.
Buscar o leer no envía, borra ni marca mensajes, y no copia el buzón a MySQL.

## Aplicar y comprobar

1. Actualizar el servidor con el script de pase seguro y el commit exacto de esta
   versión. Usa respaldo privado y comprobación de salud. Recargar con Ctrl+F5.
2. En el Apps Script **de la cuenta que falla**, actualizar `Gmail.gs` desde
   `apps-script/proxy/Gmail.gs`. Si aún no se habilitó Gmail, seguir los siete pasos
   de [la guía 57](CORREO_GMAIL_CONTENEDORES_Y_LECTURA_57.md#habilitación-opcional-en-google-una-vez-por-cuenta):
   `Proxy.gs`, `Servidor.gs`, plantilla del manifiesto, Gmail API y permisos
   `gmail.readonly` y `gmail.send`. Conservar propiedades y permisos previos.
3. Ejecutar `verificarGmailServidor` con la cuenta propietaria y aceptar los
   permisos; comprobar que devuelve su correo. Esta función no envía mensajes.
4. **Implementar → Administrar implementaciones → Editar → Nueva versión** del
   mismo despliegue `/exec`, ejecutado como **Yo**. No crear otra URL ni rotar la
   clave HMAC por esta actualización.
5. En ITSANET → **Mi cuenta y correo**, verificar su conexión. En el correo final,
   **Buscar correo original en mi Gmail**, buscar por embarque o asunto. Si falla,
   atender el diagnóstico indicado. Si aparece una política de Workspace, TI
   debe habilitar el acceso para esa cuenta.
6. Seleccionar el mensaje correcto, revisar destinatarios, asunto, embarque,
   documentos e imágenes. Abrir el hilo en Gmail permite consultar el mensaje
   completo. Buscar y seleccionar no envía: el envío requiere la acción de revisión
   y envío ya existente. Comprobar el estado confirmado antes de reintentar.

Actualizar Git no publica automáticamente Apps Script ni concede consentimiento
Google a los demás supervisores. Cada cuenta requiere su propia autorización,
una vez por conexión; no por dispositivo. No se necesita facturación Firebase.

## Validación y alcance

Pruebas con Google simulado y bases MySQL aisladas: límites de concurrencia,
liberación de conexión antes de Google, pausa de reintentos, originales intactos,
permisos supervisor/operario, diagnósticos de Gmail, selección de hilo, conservación
idempotente del envío y vista móvil de 390 px. No se enviaron correos reales ni se
movieron fotos reales para validar esta corrección. La comprobación de las cuentas
y del servidor empresarial debe realizarse después de aplicar ambas partes.
