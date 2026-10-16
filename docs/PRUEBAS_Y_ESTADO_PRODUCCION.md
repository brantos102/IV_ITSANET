# Desarrollo con operación real y comparación diaria

Desde que hay operadores trabajando, producción es la fuente de datos real.
Desarrollar en esta nube o en una máquina/VM de pruebas con FastAPI y MySQL,
una base vacía independiente y archivos de prueba. No hace falta desarrollar
en Firestore. Firebase Hosting puede mostrar una interfaz de prueba, pero no
ejecuta este servidor Python ni reproduce MySQL. Usar Firestore implica probar
otro backend; trasladar después esos datos y reglas requiere otra migración.

## Aislamiento antes de las próximas mejoras

| Componente | Producción | Pruebas |
|---|---|---|
| Código | Commit instalado, operadores activos | Copia independiente con el cambio propuesto |
| Base MySQL | Base actual | Base distinta con usuario limitado exclusivamente a ella |
| Archivos y clave de cifrado | `VAL_DATA_DIR` actual | Directorio distinto, clave nueva, sin copiar `app_config` |
| Puerto | 3002 | Puerto libre comprobado en la máquina de pruebas |
| Google | Remitentes y carpetas reales | Proyecto Apps Script, cuenta, carpeta y destinatarios de prueba |
| Acceso móvil | URL operativa actual | URL de pruebas; HTTPS confiable para cámara y OAuth |

No cargar `/etc/iv-itsanet.env` en pruebas ni copiar colas de entregas reales:
el trabajador de la app arranca automáticamente y podría enviar correos.
Una base nueva sin conexiones Google evita ese envío. Para probar Drive y
correo, configurar únicamente cuentas/carpetas/destinatarios de prueba.
Los puertos 3000/8080 y otros proyectos del servidor se conservan.

Se validan importación, usuarios y aprobación, escáner/cámara, conteos
concurrentes, fotos, cierre, entrega y exportaciones con datos sintéticos.
SQLite sirve para pruebas rápidas; los cambios de esquema o concurrencia
requieren además MySQL. El ensayo móvil se hace desde el dispositivo real.

Publicar un commit concreto después de esa validación y en una ventana acordada.
Antes: respaldo recuperable de MySQL, archivos pendientes y clave de cifrado;
ensayo de restauración en pruebas; revisión de migraciones y compatibilidad.
No sustituir la base real por la de pruebas ni ejecutar fixtures sobre ella.
La reversión de código no revierte automáticamente una migración de esquema.
Preservar el cambio local en `mysql/01-crear-base.sql`. Esta entrega solo añade
diagnóstico y documentación; no requiere actualizar ni reiniciar la app real.

## Capturar estado ahora sin actualizar producción

`scripts/estado_produccion.py` es independiente. No importa la aplicación ni
ejecuta migraciones; usa una conexión MySQL y una transacción READ ONLY,
con límite de tiempo por consulta. Solo consulta la base elegida en el entorno
del servicio. No ejecuta ANALYZE, OPTIMIZE, respaldos ni cambios globales MySQL.
Una consulta que exceda el límite se informa como no disponible, no como cero.
Las lecturas consumen algunos recursos; no es un monitor de carga continua.

Copiar **solo este script** desde esta entrega a
`~/bryan/herramientas-itsanet/estado_produccion.py` usando VS Code. También se
puede descargar desde GitHub fijando el commit publicado de esta entrega:

```bash
mkdir -p ~/bryan/herramientas-itsanet ~/bryan/reportes-itsanet
chmod 700 ~/bryan/herramientas-itsanet ~/bryan/reportes-itsanet
# Sustituir por el hash del commit de la entrega, sin los signos < >.
VERSION_DIAGNOSTICO='<commit de esta entrega>'
curl --fail --location \
  "https://raw.githubusercontent.com/brantos102/IV_ITSANET/${VERSION_DIAGNOSTICO}/scripts/estado_produccion.py" \
  --output ~/bryan/herramientas-itsanet/estado_produccion.py
```

En la terminal **SSH de VS Code** del servidor, ejecutar:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --unit="iv-itsanet-reporte-$(date +%s)" \
  --uid="$(id -un)" \
  --property="WorkingDirectory=$HOME/bryan/IV_ITSANET" \
  --property=EnvironmentFile=/etc/iv-itsanet.env \
  "$HOME/bryan/IV_ITSANET/.venv/bin/python" \
  "$HOME/bryan/herramientas-itsanet/estado_produccion.py" \
  --repo "$HOME/bryan/IV_ITSANET" \
  --salida "$HOME/bryan/reportes-itsanet"
```

Esto crea una **unidad temporal diferente** al servicio operativo. systemd lee
su archivo protegido y ejecuta el diagnóstico con tu usuario. No reinicia ni
modifica `iv-itsanet`. No ejecutar `source /etc/iv-itsanet.env`, cambiar sus
permisos o compartir su contenido. Requiere sudo y systemd con `--collect`.
Si el servicio usa otro EnvironmentFile, usar el mismo que ya tenga configurado.

Se muestran las rutas de dos archivos privados: `.json` comparable y `.md`
legible. Conservar el nombre exacto del JSON inicial. El código de salida 2
significa fallo de diagnóstico MySQL o comparación; revisar avisos del reporte.
Un fallo de salud HTTP aparece expresamente aunque MySQL sí responda.

Si producción ya usa TLS, añadir `--health https://localhost:3002/health` solo
si su certificado es válido para localhost y la CA está instalada. No desactivar
la verificación de certificados; un error de salud no invalida las cifras MySQL.

## Repetir al cierre del día

Repetir el mismo comando con este argumento al final (sustituir el nombre):

```bash
  --comparar "$HOME/bryan/reportes-itsanet/estado-<captura-inicial>.json"
```

No ejecutar esa línea sola: añadirla al comando anterior, con `\` al final de
la línea `--salida`. Se guarda otra captura con fecha UTC en el nombre y hora
de Ecuador dentro del reporte; no se sobrescribe la inicial.

El reporte muestra estado del servicio y reinicios, `/health`, commit instalado,
datos/índices por tabla, filas estimadas, fotos pendientes/confirmadas en Drive,
volumen multimedia registrado, entregas y recepciones por estado, y tamaño de
la carpeta local de archivos. La comparación calcula cambios de asignación
MySQL y de cantidades por estado. No lista personas, credenciales ni fotos.

`information_schema` ofrece estimaciones de InnoDB, a veces demoradas. La
asignación crece por páginas y puede mantenerse aunque se añadan registros.
Los cambios por estado son variaciones netas; no son todos los movimientos
ocurridos en el intervalo. Para auditoría de eventos individuales se usa el
historial de la aplicación. No se realiza COUNT completo de eventos/productos.
Las secciones se leen consecutivamente mientras la operación sigue activa.

## Verificar Drive sin confundir referencias con imágenes

MySQL `app_archivos` contiene nombre, tamaño, hash, ID y URL de Drive; no
contiene el binario. `app_archivo_skus` relaciona archivos e ítems. Los JSON
de entrega pueden crecer por las instantáneas de cierre, aunque no haya fotos
dentro de MySQL. El informe enumera columnas binarias presentes sin leerlas.

Actualmente el archivo se guarda temporalmente en `VAL_DATA_DIR/app_archivos`.
Al cerrar la recepción, el trabajador lo copia a Drive, confirma el ID en
MySQL y elimina la foto local. Los informes locales se conservan. Si Drive
falla, la evidencia queda protegida en disco y la entrega pendiente.
Una recepción abierta puede tener fotos pendientes aunque el puente funcione.
No borrar esa carpeta manualmente ni desactivar esta protección en producción.

Drive será el repositorio definitivo. Para enviar las imágenes mientras la
recepción sigue abierta, el siguiente cambio debe ser una cola independiente
con reintentos e idempotencia, ensayada en pruebas; hoy se envían al cierre.
No es necesario guardar fotos en MySQL ni en Sheets. Mantener solo memoria
temporal perdería evidencia si se reinicia el servicio.

Desde ADMIN → Drive y envío de correo → **Verificar remitente y Drive**,
comprobar cuenta ejecutora y carpeta. Esta comprobación consulta el puente
firmado y no envía un correo. No equivale a comprobar una subida completa.
La prueba completa de subir/abrir una foto y recibir un correo se hace primero
con una recepción y destinatarios de prueba, mediante el cierre normal.

Carpeta indicada por el proyecto:
`1EOCoI3eNpe9lM1iQvgMgDo7e8_oGCBtY`. Confirmar que
`CARPETA_EVIDENCIAS` de cada puente contiene ese ID y que el supervisor tiene
permiso de edición. `SERVIDOR_HMAC` debe coincidir con el valor guardado por
ADMIN para ese supervisor. No pegar esa clave en reportes/chat. El correo
sale de la cuenta que ejecuta el puente y debe coincidir con el supervisor
responsable. Ver [configuración Google](GOOGLE_Y_FORMATOS.md).

Un ID confirmado en el diagnóstico prueba la subida registrada anteriormente;
no comprueba que alguien no haya borrado después el archivo en Drive. Abrir
**Imágenes de la recepción → Abrir carpeta de imágenes en Drive** para esa
comprobación. No se ha establecido una conexión al servidor o a Drive desde
este entorno: los reportes reales deben ejecutarse en el servidor empresarial.
