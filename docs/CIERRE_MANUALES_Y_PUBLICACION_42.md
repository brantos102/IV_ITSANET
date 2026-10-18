# Cierre, manuales y pruebas públicas — versión 42

Interfaz `20261018-42`. Publicación: `itsanet-20261018-cierre-manuales-42`.
Incluye las mejoras de lecturas, etiquetas y columnas de la versión 41.

## Qué cambia

- Tema con iconos ☀ y ☾, conservando la descripción accesible.
- Avance circular de las referencias verificadas de la recepción actual. No representa unidades recibidas ni aparece al salir de esa recepción.
- Botón **Entregas** en la cabecera de supervisores y ADMIN: recepciones cerradas con envío pendiente; considera la última entrega de cada recepción.
- Foto propia desde **Mi cuenta**. El servidor convierte la imagen a JPEG de 256 × 256, elimina metadatos y exige sesión para verla. Se incluye en el respaldo MySQL.
- Administración organizada en Operación diaria, Entregas, Conexiones, Roles y reglas y Formatos Depot. Los formularios y conexiones existentes se conservan.
- Cierre que guía hacia la primera referencia pendiente y permite continuar manualmente cuando las fotos están guardadas pero Drive aún no confirmó la copia.
- Reutilización explícita de un informe ya preparado, cuando pertenece al mismo supervisor, es el más reciente y corresponde a los datos actuales. Una corrección de conteo exige una nueva versión.
- Correo final con nombres de fotografías ajustados al ancho de cada imagen.

## Tres opciones para cerrar

Antes de cerrar se revisan las cantidades, los documentos y el correo final. En ese correo puedes elegir:

1. **Cerrar y enviar desde mi cuenta autorizada**: exige conexión Google verificada y los requisitos de Drive. El cierre no equivale a correo entregado; Entregas presenta la confirmación por separado.
2. **Cerrar y preparar envío manual**: conserva documentos y texto final; detiene el envío automático. Copia el correo, descarga sus documentos y envíalos desde tu cuenta. Después registra el envío manual.
3. **El correo ya se envió manualmente; cerrar**: requiere confirmar la revisión de Enviados e indicar cómo se enviaron los documentos. Conserva la declaración del supervisor sin simular un acuse de Google.

Una referencia sin revisar continúa impidiendo el cierre. Abrir la primera pendiente no registra cantidades. Debes contarla o declarar **No apareció** con una observación.

## Resolver las recepciones históricas enviadas fuera de la app

En **Entregas**, busca la recepción y pulsa **Ya se envió manualmente**. Revisa primero en Enviados el destinatario y los documentos finales. Introduce el motivo y confirma la revisión. La app detiene los trabajos pendientes de esa recepción, conserva el informe y registra autor y fecha.

El sistema rechaza la acción si otro proceso está enviando, la recepción se reabrió, el conteo cambió o el informe seleccionado ya no es el más reciente. Si el estado cambió durante la revisión, actualiza antes de repetir. No se confirma masivamente todo el historial porque cada entrega debe verificarse.

**Retirar del historial** oculta una entrega resuelta. **Incluir historial archivado** permite consultarla y restaurarla. No borra recepciones reales, documentos ni auditoría. Las pendientes deben resolverse antes de retirarlas.

## Varios usuarios simultáneos

Los registros mantienen identificadores de operación y bloqueos de filas por recepción. El cierre compara la bitácora revisada con la actual. Un reintento solo recupera el cierre cuando coincide la solicitud completa y su autor; otra cuenta no hereda el cierre.

Los borradores de correo incluyen la identidad de quien los revisa. La declaración manual y el archivo visible exigen una versión vigente de la entrega. Si cambian mientras están abiertos, el servidor devuelve un conflicto en lugar de aplicar una decisión antigua. El worker y la resolución manual comparten los bloqueos para impedir un envío mientras se declara resuelto.

Los permisos de servidor siguen aplicándose aunque se intente llamar una API directamente. Los operarios no obtienen acceso al correo ni a las conexiones generales. Los supervisores gestionan operación y equipo dentro de sus permisos; ADMIN gestiona conexiones, reglas y administradores. Las contraseñas de usuarios se conservan como hashes: se restablecen, no se recuperan en texto.

## Firebase que ya existe

El historial y `firebase/firebase.json` conservan el sitio **https://iv-itsanet.web.app/**. Su versión histórica usa Firebase Authentication y Firestore **bd-iv-itsanet**. La aplicación empresarial en **/app/** utiliza sesiones de FastAPI y MySQL.

Un `firebase deploy --only hosting` publica archivos estáticos; no instala FastAPI, MySQL ni el worker de Drive/correo. Por ello, actualizar únicamente ese Hosting no demostraría que funciona el flujo empresarial actual. La versión 42 no modifica ni reemplaza ese sitio ni su base de datos.

Para usar ese mismo dominio con el servidor actual se necesita publicar un backend HTTPS y configurar un servicio de Google Cloud compatible con los rewrites de Hosting, o migrar el backend y sus datos de manera planificada. Un canal de vista previa que conserve la configuración Firestore tampoco aísla los datos por sí solo. No se debe usar el Firestore real como base desechable de pruebas.

La consulta HTTPS al sitio respondió **200**. El HTML coincide exactamente con el commit **0d417e7ec0636e811b6aec577c3a03277fc7ee61** («Corrige registro y aprobación de usuarios en Firebase y servidor»). Su service worker anuncia **iv-2026-10-14-16**, el HTML fue modificado el **15 de octubre de 2026, 01:33:31 UTC**, y su configuración pública identifica la base **bd-iv-itsanet**. Esta comprobación es de solo lectura: no acredita sesión ni permisos de despliegue. No existe una sesión Firebase autorizada disponible aquí para actualizarlo.

## Producción empresarial 3002

Ejecuta en la terminal del servidor **apps**, desde la cuenta habitual que mantiene `~/bryan/IV_ITSANET`:

```bash
cd ~/bryan/IV_ITSANET &&
git fetch origin tag itsanet-20261018-cierre-manuales-42 &&
VERSION_ITSANET=$(git rev-parse 'itsanet-20261018-cierre-manuales-42^{commit}') &&
SCRIPT_PASE_ITSANET=$(mktemp /tmp/itsanet-pase.XXXXXX.sh) &&
git show "${VERSION_ITSANET}:scripts/actualizar_produccion.sh" > "$SCRIPT_PASE_ITSANET" &&
bash "$SCRIPT_PASE_ITSANET" "$PWD" "$VERSION_ITSANET"
```

El actualizador verifica respaldo de MySQL, archivos y `/etc/iv-itsanet.env` antes de instalar. Conserva los datos y las conexiones; pausa únicamente `iv-itsanet`, comprueba salud y página de acceso y recupera el código anterior si falla el arranque. No requiere copiar bases de desarrollo ni resetear usuarios.

Al finalizar debe indicar **Servicio y página de acceso confirmados**, el commit instalado y la ruta privada del respaldo. Si el actualizador falla, conserva su salida y no sustituyas la base de datos para continuar. No ejecutes pytest contra producción.

Comprobación desde el propio servidor:

```bash
systemctl is-active iv-itsanet
curl --fail --silent http://127.0.0.1:3002/health
curl --fail --silent http://127.0.0.1:3002/app/index.html | rg '20261018-42'
```

Después actualiza el navegador con Ctrl+F5. Esta entrega no cambia por sí misma la versión publicada de Apps Script; si el correo editable aún no está autorizado, sigue [Google y formatos](GOOGLE_Y_FORMATOS.md) y revisa el correo desde tu propia cuenta.

## Pruebas desde casa, sin VPN

El supervisor necesita solamente una URL HTTPS y su cuenta individual. **El comando de publicación lo ejecuta quien administra el servidor**, una sola vez; el supervisor no necesita terminal ni acceso a la red interna.

La alternativa preparada abre una instancia completa de pruebas con un enlace temporal de Cloudflare. Usa otro proyecto Docker, otro MySQL, otros archivos, contraseñas aleatorias y puerto **3003 enlazado únicamente a loopback**. No importa usuarios ni datos productivos. La portada muestra **PRUEBAS**. El enlace usa certificado público confiable y permite solicitar cámara en vivo.

Requisitos: Docker Engine con Compose v2, Python 3, Git, curl, tar y flock; espacio y memoria para otro MySQL. Para instalar Docker usa las instrucciones oficiales de tu distribución: https://docs.docker.com/engine/install/. Docker debe estar funcionando y la cuenta ejecutora debe poder utilizarlo. El servidor necesita salida a Cloudflare: HTTPS para obtener el enlace y TCP 7844 para el túnel HTTP/2. No necesitas abrir un puerto entrante en el router.

Después de descargar la publicación, ejecuta en **apps**:

```bash
cd ~/bryan/IV_ITSANET &&
git fetch origin tag itsanet-20261018-cierre-manuales-42 &&
VERSION_PRUEBAS_ITSANET=$(git rev-parse 'itsanet-20261018-cierre-manuales-42^{commit}') &&
SCRIPT_PRUEBAS_ITSANET=$(mktemp /tmp/itsanet-pruebas.XXXXXX.sh) &&
git show "${VERSION_PRUEBAS_ITSANET}:scripts/publicar_pruebas.sh" > "$SCRIPT_PRUEBAS_ITSANET" &&
bash "$SCRIPT_PRUEBAS_ITSANET" "$PWD" "$VERSION_PRUEBAS_ITSANET" publicar
```

La primera ejecución descarga y construye las imágenes. Solo anuncia una URL después de comprobar que ese enlace responde como la instancia de pruebas. Si el proveedor no responde, informa el error; no declara publicada la app.

La salida muestra:

- Una URL real con forma **https://…trycloudflare.com/app/**. Esa es la que recibe el supervisor de casa.
- La ruta del archivo privado **../itsanet-pruebas-publicas/.privado/accesos-iniciales.txt**. Contiene las cuentas iniciales `admin`, `supervisor.prueba` y `operario.prueba`, con contraseñas exclusivas de esta instancia. Léelo localmente; comparte solo la cuenta necesaria por un canal privado. Las contraseñas iniciales deben cambiarse en Mi cuenta.

Para varias personas crea cuentas individuales desde Equipo. Carga un packing list de prueba y trabaja con datos sintéticos. Las conexiones Google/Depot están vacías: no se envían correos ni se consulta Depot hasta configurarlas explícitamente para pruebas.

El enlace temporal puede cambiar al reiniciar el túnel. Los datos persisten en sus volúmenes. Repetir el comando conserva las claves privadas existentes. Si faltan esas claves y ya existen datos, se detiene para evitar sobrescribir el acceso. Para un enlace estable, el administrador puede sustituir el túnel temporal por un túnel con dominio propio y política de acceso.

Acciones de mantenimiento usando las variables del mismo bloque:

```bash
bash "$SCRIPT_PRUEBAS_ITSANET" "$PWD" "$VERSION_PRUEBAS_ITSANET" estado
bash "$SCRIPT_PRUEBAS_ITSANET" "$PWD" "$VERSION_PRUEBAS_ITSANET" detener
```

**detener** apaga únicamente el enlace público; conserva datos y producción. **preparar** instala y verifica la instancia local sin abrir un enlace. No se requiere ejecutar el actualizador productivo para publicar pruebas, ya que este script extrae su propia copia del commit comprobado.

## Cámara en producción

Una IP HTTP no puede habilitar video en vivo mediante JavaScript. Ahora Cámara ofrece tomar una foto del código o elegir una imagen como alternativa; esa imagen se utiliza solo para consultar el código, sin guardarse como evidencia ni registrar unidades.

Para video en vivo permanente hay que entregar una URL HTTPS con certificado confiable. El proxy inverso debe llevar tanto **/app/** como **/api/** al mismo FastAPI del puerto 3002; un Hosting estático aislado no lo resuelve. El certificado debe ser confiable en los móviles. No se usan opciones para desactivar la seguridad del navegador. Las fotos de evidencia siguen teniendo sus propios botones y guardado.

## Manuales HTML interactivos

Se instalan con la app y funcionan también como archivos HTML independientes, sin servicios externos:

- [Operario](../firebase/public/manuales/operario.html): lectura, conteo, pallets, fotos, incidencias, teclado, cámara y práctica local.
- [Supervisor](../firebase/public/manuales/supervisor.html): recepciones, informes, revisión de correo, cierre, declaración manual, equipo, etiquetas y fotografías.
- [Técnico](../firebase/public/manuales/tecnico.html): arquitectura, conexiones, permisos, configuración, servicios, código, respaldo y publicación.

En el servidor quedan en **/app/manuales/operario.html**, **/app/manuales/supervisor.html** y **/app/manuales/tecnico.html**. Menú → Ayuda abre el manual correspondiente. Incluyen búsqueda, navegación por pasos, temas revisados y formato de impresión/PDF.

## Validación y límites

Las pruebas usan bases desechables y registros sintéticos. Se verifican API, permisos, declaración manual, reintentos, conservación de documentos, concurrencia sobre MySQL y los recorridos principales en Chromium de escritorio y móvil. No se envían mensajes reales ni se imprime en la Zebra de producción desde estas pruebas.

El pase productivo y la creación del enlace público deben confirmarse mediante la salida de sus comandos en **apps**. Publicar el código en GitHub no equivale a instalarlo en el servidor. Desde este entorno no hay acceso administrativo a ese equipo ni una sesión Firebase autorizada.
