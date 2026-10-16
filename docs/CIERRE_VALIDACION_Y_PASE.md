# Validación, Drive y candidato de producción

Estos cambios se preparan en `desarrollo-local`. No trasladar la base de desarrollo a producción: las recepciones, fotografías, conteos y usuarios que ya registran los operadores deben conservarse.

## Actualizar la PC de desarrollo

En PowerShell de Windows:

```powershell
Set-Location "$HOME\source\IV_ITSANET-desarrollo"
git pull --ff-only origin desarrollo-local
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local.ps1
```

Abrir `http://localhost:3003/app/`. El volumen de MySQL y la contraseña inicial existentes se conservan.

## Operación y revisión

- Recepción actual mantiene el escáner. El porcentaje mide referencias revisadas; los faltantes confirmados no impiden llegar al 100 %. Lo contado y la diferencia siguen visibles por separado, incluso con la recepción cerrada.
- Al contar 6 unidades con 2 dañadas, registrar cantidad 6, incidencia MAL ESTADO y unidades con incidencia 2: quedan 4 conformes y 2 PNC. Faltantes y sobrantes se calculan respecto al packing list. La bitácora permite a supervisores corregir la clasificación sin alterar el conteo original. Si hay distintos daños, se pueden registrar cantidades separadas; cada unidad pertenece a una clasificación física.
- Administración → Permisos y reglas permite autorizar aprobación de cuentas y asignación de SUPERVISOR, sin permitir que un supervisor otorgue ADMIN. La vinculación del correo responsable corresponde a ADMIN. Las credenciales técnicas y el diagnóstico de instalación continúan siendo exclusivos de ADMIN.
- Administración → Clientes permite decidir si se exige pallet o posición. Los valores opcionales permanecen vacíos; no se inventa una ubicación.
- Columnas del informe permite al supervisor elegir, por cada packing list, dónde escribir marca, cliente, cantidad física, incidencia, cantidad afectada, observaciones, barras y carpeta Drive. No cambia sus filas ni encabezados. Un formato puede asignar A/M/P/Q/R/S y otro columnas diferentes. Guardar las reglas generales del cliente en Administración cuando corresponda. Las columnas de salida deben existir en el archivo recibido.
- Los dos modelos de altas de Depot siguen editables y aparecen contraídos. La plantilla adicional de barras se retiró del menú; registrar una etiqueta nueva sigue asociándola al SKU existente y permite incluirla en el packing list mediante su columna.
- Historial de informes conserva versiones R0001, R0002… con identificador, autor, hora de Ecuador y descarga solicitada. La confirmación de una descarga HTTP no demuestra que el dispositivo haya guardado físicamente el archivo. El estado ENVIADO requiere confirmación del puente Google; EN_COLA no significa enviado. Los archivos anteriores se conservan al generar otra versión.
- El equipo activo se actualiza cada 45 segundos y expira a los dos minutos sin actividad visible. El historial de autores se mantiene separado. La sesión se retira de presencia al cerrar sesión.
- Los avisos aparecen en la pantalla visible sin desplazar al usuario ni quitar el foco al escáner. Los errores y advertencias se pueden cerrar; conservan su copia en la sección de mensajes.
- **Revisar envío a Drive** identifica las fotos ya guardadas que todavía esperan confirmación: nombre, SKU, tipo, bulto y packing list. Permite revisar imágenes, reintentar la copia y descargar un avance. Al confirmar Drive, permite continuar con el cierre y elegir destinatarios. No pide repetir fotos ni envía correo desde la revisión. Las recomendaciones fotográficas siguen sin bloquear el avance.

## Comprobar Google desde una cuenta real

Remitente de prueba indicado: **bespinoza@itsanet.com**. Destinatario de prueba: **brantos102@gmail.com**. Los campos son editables; el servidor comprueba la cuenta Google ejecutora.

1. ADMIN → Usuarios → Editar: vincular `bespinoza@itsanet.com` a la cuenta activa responsable. No crear otra cuenta si ya existe con ese correo. Aprobar/promover un usuario no otorga acceso a las credenciales del puente.
2. Desde esa cuenta Google, seguir [GOOGLE_Y_FORMATOS.md](GOOGLE_Y_FORMATOS.md): copiar las versiones actuales de `apps-script/proxy/Proxy.gs`, `Clientes.gs` y `Servidor.gs` al proyecto del supervisor. En las propiedades privadas conservar `SERVIDOR_HMAC` y `CARPETA_EVIDENCIAS`; usar la misma clave aleatoria ya generada en el campo secreto de Administración. No generar otra si la existente ya está configurada.
3. Actualizar el despliegue como aplicación web, ejecutada por esa cuenta, y copiar su URL terminada en `/exec`. El servidor necesita poder invocar ese despliegue; el puente valida HMAC y caducidad antes de escribir o enviar.
4. ADMIN → Drive y envío de correo: indicar supervisor, URL `/exec` y clave compartida. Guardar puente. Pulsar **Verificar remitente y Drive**. Esa comprobación no envía correo.
5. La carpeta suministrada es `https://drive.google.com/drive/folders/1EOCoI3eNpe9lM1iQvgMgDo7e8_oGCBtY`. El supervisor debe tener permiso de editor; compartir con los destinatarios autorizados según corresponda. Para pruebas de subida en desarrollo, crear y configurar una subcarpeta exclusiva de pruebas; mantener la carpeta operativa para producción.
6. ADMIN → Repositorios de Drive: registrar el ID o enlace, cliente/marca opcionales y supervisor de referencia; guardar configuración y probar el repositorio. Las carpetas por cliente/marca/recepción/bulto/SKU/tipo se crean al copiar evidencia. Las imágenes pendientes permanecen temporalmente en el almacenamiento local hasta confirmar Drive; MySQL guarda referencias y trazabilidad.
7. Desplegar **Enviar correo de prueba**, confirmar remitente y destinatario, y pulsar enviar. El botón verifica al ejecutor y al repositorio antes de enviar un mensaje identificable. Si se interrumpe la confirmación del correo, revisar Enviados y la bandeja del destinatario antes de iniciar otra prueba; el mismo identificador no se reenvía automáticamente.
8. Revisar una recepción de prueba → Imágenes de la recepción → carpeta Drive; registrar evidencias por tipo y comprobar la copia. Depurar imágenes antes de finalizar. La columna de evidencia utiliza carpetas confirmadas por Drive, sin inventar enlaces de imágenes pendientes. Si esa columna está asignada y todavía hay fotos de SKU pendientes, el cierre final espera su confirmación; se puede continuar contando y descargar avances. La entrega incluye el enlace a la carpeta de la recepción.

La cuenta autenticada que finaliza es el remitente responsable. Escribir otro correo en una pantalla no concede autorización para enviarlo como esa persona. El botón Google de login usa otro mecanismo: OAuth web. No exige la contraseña de Gmail y no reemplaza el permiso del puente para Drive/correo.

## Red de producción y cámaras móviles

Dirección informada: `http://192.168.4.64:3002/app/`. Desde este entorno de desarrollo la comprobación de `/health` fue rechazada con HTTP 403 por el proxy; no se verificó conexión con el servidor empresarial y no hay SSH configurado aquí.

El acceso con usuario y contraseña puede funcionar por esa red interna. Los navegadores móviles requieren **HTTPS con certificado de confianza** para la cámara en vivo; Google también requiere una URI HTTPS autorizada para el login desde esos equipos. `localhost` es una excepción de desarrollo en la PC, no la dirección del servidor desde el celular. Configurar el dominio y certificado en el proxy web de la empresa sin sustituir otros servicios. La URI OAuth final será `https://DOMINIO/api/auth/google/callback`, exactamente igual en Google Cloud y en Administración. No introducir excepciones inseguras en el navegador de los operadores.

## Verificación y pase

Se ejecutan la suite del proyecto, pruebas contra MySQL en una base desechable separada y pruebas de navegador móvil. Las pruebas de correo/Drive usan dobles hasta disponer del puente autorizado real: no prueban conectividad empresarial ni entrega de un correo real.

Antes del pase, completar las pruebas de Google y de un celular real por HTTPS desde la red empresarial. Capturar el estado inicial y al final del día con [PRUEBAS_Y_ESTADO_PRODUCCION.md](PRUEBAS_Y_ESTADO_PRODUCCION.md). La captura es de solo lectura y compara volumen MySQL y archivos, sin exportar datos privados.

El responsable del servidor debe obtener un respaldo consistente de MySQL y del directorio configurado en `VAL_DATA_DIR`, incluida `secretos/integraciones.key`, y conservar `/etc/iv-itsanet.env`. Coordinar una pausa de escritura para que base y archivos correspondan a la misma captura. Guardar el commit anterior y comprobar la restauración del respaldo. No copiar la base, las credenciales ni el volumen de Docker de desarrollo sobre producción.

La actualización agrega tablas de clasificación, presencia, generaciones de informes y auditoría mediante el arranque normal de la aplicación; no borra ni reemplaza tablas existentes. Desplegar el commit revisado en una entrega identificada, conservando la modificación local de `mysql/01-crear-base.sql` y los directorios no versionados existentes. No ejecutar reset/clean ni forzar un pull ante conflictos. El frontend usa versión `20261016-29`; recargar las pantallas antes de retomar operación.

### Ejecutar el pase desde la terminal del servidor

La etiqueta de esta entrega es `itsanet-20261016-cierre-guiado`. Tras avisar a los
operadores que deben terminar sus guardados y pausar nuevos registros, ejecutar
en la terminal **SSH del servidor**, con el usuario que administra `iv-itsanet`:

```bash
cd ~/bryan/IV_ITSANET &&
git fetch origin tag itsanet-20261016-cierre-guiado &&
VERSION_ITSANET=$(git rev-parse 'itsanet-20261016-cierre-guiado^{commit}') &&
SCRIPT_PASE_ITSANET=$(mktemp /tmp/itsanet-pase.XXXXXX.sh) &&
git show "$VERSION_ITSANET:scripts/actualizar_produccion.sh" > "$SCRIPT_PASE_ITSANET" &&
bash "$SCRIPT_PASE_ITSANET" "$PWD" "$VERSION_ITSANET"
```

El procedimiento prepara las dependencias antes de detener el servicio, comprueba
la carpeta operativa y los cambios locales, y necesita `sudo`, `systemd-run` y
`mysqldump` o `mariadb-dump`. Si falta este último, se detiene antes de pausar la
app. El usuario MySQL del servicio debe poder exportar sus tablas y disparadores.
Una conexión con opciones TLS especiales requiere un respaldo compatible y se
rechaza antes de detener el servicio, sin desactivar verificaciones.

Pausa únicamente `iv-itsanet`. Guarda MySQL, `VAL_DATA_DIR` completo —incluida la
clave de cifrado—, el entorno operativo y el cambio local SQL en un directorio
privado `~/bryan/respaldos-itsanet/pase-...`. Comprueba la integridad de los archivos
comprimidos y registra sus hashes. Aplica el commit por avance directo, instala
las dependencias preparadas y comprueba el servicio y `/health`. Si falla después
de detenerlo, intenta recuperar el código anterior y arrancar el servicio; no
restaura una base antigua sobre registros nuevos. Una recuperación de código
puede dejar el repositorio en HEAD separado, identificado en el respaldo.

No importa bases, recepciones de prueba, usuarios, secretos ni volúmenes Docker
de desarrollo. Conserva las conexiones ya guardadas en producción. Si Drive se
configuró únicamente en localhost, registrar el puente y repositorio desde ADMIN
de producción con los mismos permisos de Google; no copiar toda la base para
transportar esa configuración.

Al terminar, revisar una recepción real existente, sus cantidades e imágenes,
registrar un conteo controlado y verificar Drive desde ADMIN. Solo entonces avisar
a los operadores para recargar y retomar. La cámara móvil sigue requiriendo HTTPS.

Si falla la comprobación del arranque, volver al código anterior con su mismo entorno; las tablas agregadas pueden permanecer y no requieren restaurar una base antigua sobre conteos nuevos. Si la recuperación exige restaurar datos, detener las escrituras y reconciliar primero lo registrado después del respaldo. No ejecutar las pruebas destructivas en la base real.

El pase no se considera realizado por publicar una rama de Git. Requiere ejecución y comprobación en `192.168.4.64`, además del acuse real de Drive/correo.

## Evidencia de la validación de desarrollo

Se verificaron conteos concurrentes sobre MySQL con 80 unidades: 10 PNC y 70 conformes, anulaciones y correcciones sin alterar cantidades originales, reservas simultáneas de informes, permisos en servidor y navegador, y códigos con ceros en Excel. La cámara decodificó un QR desde video continuo con ZXing y permitió continuar al siguiente bulto sin exigir fotos mínimas.

En Chromium móvil se ejercitaron registro parcial, mapeo de columnas, exportación archivada, promoción/aprobación por supervisor y ocultación del diagnóstico. En un origen HTTP de prueba sin `crypto.randomUUID` funcionaron sesión, escaneo manual, historial y Administración. Se comprobó la selección de etiquetas para 4 unidades conformes de un SKU con otras 2 PNC: cuatro copias de una unidad.

Muestras con datos sintéticos: [revisión de incidencias](muestras/revision-incidencias-movil.png) y [gestión por supervisor](muestras/permisos-supervisor-movil.png). Ninguna de estas comprobaciones envió un correo real, imprimió en una Zebra física ni modificó el servidor empresarial.

La entrega `itsanet-20261016-cierre-guiado` pasó 864 comprobaciones de la suite
completa (441 Python y 423 JavaScript). Los cinco casos del cierre guiado pasaron
también contra MySQL 8.4 aislado. La prueba de navegador móvil verificó avisos sin
desplazamiento ni pérdida de foco, visibilidad sobre diálogos y reintento seguido
de confirmación. [Muestra de la ayuda de cierre](muestras/cierre-pendiente-movil.png)
con datos sintéticos y respuestas simuladas de Drive.

El procedimiento de pase se ensayó con servicios simulados: éxito, fallo de
respaldo y fallo de salud, conservando datos y SQL local. Además se generó y
restauró el SQL de una base MySQL 8.4 desechable, distinta de la de desarrollo.
Estas pruebas no sustituyen el respaldo ni la comprobación de salud en el
servidor real.
