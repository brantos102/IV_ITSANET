# Fotos con trazabilidad y carpetas por bulto — entrega 46

Interfaz `20261018-46`. Etiqueta `itsanet-20261018-fotos-auditoria-46`.

## Comportamiento acordado

La fotografía conserva la clasificación en la que se registró. Cuando el
producto pasa de faltante a encontrado con una unidad PNC, la foto anterior
permanece como evidencia histórica de FALTANTE y la nueva foto se registra en
PNC. La etiqueta histórica de una fotografía no declara un faltante actual: el
conteo y las incidencias actuales se consultan en la ficha del SKU.

Una foto recién preparada para guardar un conteo recibe su clasificación final
una sola vez, al confirmar ese conteo por el mismo autor. Corregir o reutilizar
un evento no reclasifica fotos históricas. Para reclasificar una foto se usa
**Corregir vínculo** en la galería, con permiso de supervisor y registro de
antes/después. Guardar fotos sin registrar conteo ahora vacía la selección,
por lo que no se vuelve a incluir ese lote en el siguiente conteo.

Una selección repetida con contenido idéntico reutiliza el archivo dentro de
la recepción. La deduplicación usa SHA-256 del contenido; un nombre repetido
no identifica una foto y no se descartan fotografías distintas por parecerse.

## Nombres y carpetas

Ejemplo de nombre:

```text
PR-RB654123-18-10-2026_RB654123_20261018_00001.jpg
```

Incluye recepción, embarque(s), fecha original del registro en Ecuador y un
secuencial persistente por recepción. La fecha no se toma de EXIF ni se inventa
una fecha de captura de la cámara. Los nombres largos se abrevian con un hash;
los embarques completos se conservan en los metadatos. El número se mantiene al
renombrar, reintentar o reclasificar; incluye fotos retiradas para no reutilizar
una secuencia anterior.

Las fotos tomadas antes del packing muestran `SIN-EMBARQUE`. Cuando se carga o
corrige el embarque, se actualizan el nombre y la carpeta sin cambiar la
secuencia ni subir otra copia del archivo confirmado.

Ejemplo dentro del repositorio de cliente y marca:

```text
RECEPCION/
  BULTOS/
    Bulto01_RECEPCION_RB654123/
      RECEPCION_RB654123_20261018_00001.jpg
      Caja01_CODIGO-CAJA/
        RECEPCION_RB654123_20261018_00002.jpg
  RECEPCION/PANORAMICA/
  FALTANTE/SKU/
  PNC/SKU/
```

Las panorámicas de toda la recepción no se atribuyen al primer bulto. Las fotos
vinculadas a una caja interior quedan bajo su bulto. Una misma foto puede
servir intencionalmente a dos contextos: conserva un solo binario y un acceso
identificado como `ACCESO__...` en el otro destino.

Se agregó `app_archivo_identidades`, una tabla independiente que conserva
secuencia, nombre original y nombres anteriores. Las columnas y el contenido
binario de las fotos existentes se conservan. Para una foto antigua, el nombre
original disponible es el que tenía registrado el sistema al organizarla; no
se puede reconstruir un nombre de cámara que ya no estuviera guardado.

La galería muestra secuencia, responsable y fecha; el Excel de evidencias añade
nombre actual, nombre original y secuencia. La ruta local y la descarga siguen
usando el ID del archivo. Los enlaces Drive conservan el mismo `fileId`.

## Organizar imágenes existentes

En una galería, el supervisor pulsa **Organizar fotos**. La vista previa muestra
nombre actual, nombre propuesto, carpetas y clasificación que se conservará.
Al confirmar se programan las operaciones; no se modifican conteos ni se envía
correo. Si otro usuario cambió las fotos o hay una copia activa, se pide
actualizar o esperar antes de aplicar.

La apariencia repetida observada en una carpeta anterior puede ser un acceso
directo creado por el puente anterior. El puente nuevo retira solo atajos que
apuntan a esa misma imagen en rutas anteriores conocidas de la recepción y
que ya no corresponden a un vínculo vigente. Los atajos retirados van a la
papelera; el archivo original y sus enlaces permanecen.

Una clasificación antigua que ya se hubiera cambiado incorrectamente no se
adivina ni se sobrescribe durante la organización. Revisa su miniatura y usa
**Corregir vínculo → FALTANTE** para devolver esa imagen histórica a su contexto
correcto. La corrección queda auditada y conserva el archivo.

## Primero actualizar el puente Google

1. Abre el proyecto Apps Script ya usado por la cuenta responsable.
2. Sustituye únicamente el contenido de `Servidor.gs` por
   [el archivo de esta entrega](https://github.com/brantos102/IV_ITSANET/blob/itsanet-20261018-fotos-auditoria-46/apps-script/proxy/Servidor.gs).
3. Guarda y entra en **Implementar → Gestionar implementaciones → Editar → Nueva
   versión → Implementar** sobre la implementación existente.
4. Conserva el mismo `/exec`, `SERVIDOR_HMAC`, carpeta y cuenta ejecutora. No se
   añade un permiso nuevo ni se habilita facturación.
5. En Mi cuenta verifica la conexión. Repite la actualización del proyecto para
   cada cuenta personal responsable que tenga su propio puente.

El estado del puente anuncia la capacidad `fotosAuditables`. Si falta, la app
conserva las fotos pendientes en el servidor e informa que debe actualizarse
`Servidor.gs`. No confirma como copiadas las imágenes antes de recibir su ID.
Los reintentos conservan las rutas intentadas para encontrar una carga cuya
respuesta se perdió, aunque después haya cambiado su destino.

## Actualizar la PC del piloto

En PowerShell, dentro de `C:\Users\IMORETA\source\IV_ITSANET-desarrollo`, con Docker
Desktop iniciado:

```powershell
git pull --ff-only origin desarrollo-local; if ($LASTEXITCODE -eq 0) { powershell.exe -NoProfile -File .\tests\probar_lanzador_windows.ps1; if ($LASTEXITCODE -eq 0) { .\scripts\publicar_pruebas.ps1 } }
```

El lanzador vuelve a crear solo el contenedor de la app para cargar el código
nuevo; MySQL y sus volúmenes se conservan. El enlace temporal puede cambiar.
Las cuentas ya existen: `admin`, `supervisor.prueba` y `operario.prueba`. Usa las
claves de `.local\pruebas-publicas\accesos-iniciales.txt`, salvo que se hayan
cambiado en la app. No necesitas registrarte nuevamente. Las cuentas de
producción no se importan al piloto.

## Actualizar producción

Después de actualizar el puente, durante una pausa operativa y con las fotos
seleccionadas ya guardadas, ejecutar en la terminal Linux `enicolalde@apps`:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin tag itsanet-20261018-fotos-auditoria-46 && VERSION_ITSANET=$(git rev-parse 'itsanet-20261018-fotos-auditoria-46^{commit}') && git show "${VERSION_ITSANET}:scripts/actualizar_produccion.sh" > /tmp/actualizar-itsanet-46.sh && bash /tmp/actualizar-itsanet-46.sh "$PWD" "$VERSION_ITSANET"
```

El actualizador verifica el respaldo antes del pase. El arranque crea la tabla
adicional respetando las claves y collations de MySQL; no elimina ni reemplaza
tablas operativas. Recarga con Ctrl+F5 en
**https://apps.flexnetuio.com:8443/app/**. Las recepciones antiguas se organizan
mediante la vista previa descrita arriba, conservando sus IDs e historial.

## Verificación

Resultados finales:

- **1.149 comprobaciones generales aprobadas**: 482 JavaScript y 667 Python.
  La suite Python omite 12 casos condicionados a archivos corporativos o
  MySQL; esas omisiones no se cuentan como aprobadas.
- **47 pruebas adicionales MySQL 8.4 aprobadas** en una base desechable. Incluyen
  secuencia con cuatro usuarios simultáneos y lectura previa a adquirir el
  bloqueo, migración de tablas, cierres, reintentos y documentos grandes.
- **15 pruebas del puente Drive simulado** (incluidas en JavaScript): mismo
  archivo al reclasificar, respuesta perdida con cambio de ruta, retirada
  exclusiva de atajos obsoletos y accesos intencionales sin duplicar binarios.
- **14 pruebas del lanzador PowerShell** aprobadas y preparación con Docker
  real: aplicación reiniciada, MySQL activo, cuentas y claves conservadas.
- Chromium: Guardar fotos limpia la selección; corregir 355 a 356 con una
  unidad PNC conserva la imagen FALTANTE y registra solo la nueva PNC;
  secuencias 00001/00002, vista previa móvil y organización sin cambiar conteos.
- Regresión de navegador: escáner, cabecera, teclado, columnas del informe,
  etiquetas de bultos, selección / guardado / ampliación de fotografías.

Las pruebas usan imágenes sintéticas, bases desechables y un Drive simulado;
no se prueban envíos reales ni se cambia el Google Drive del usuario desde la
nube. El enlace del piloto compartido no pudo comprobarse desde esta nube:
la consulta pública devolvió HTTP 403; eso no demuestra que falle desde la PC.
