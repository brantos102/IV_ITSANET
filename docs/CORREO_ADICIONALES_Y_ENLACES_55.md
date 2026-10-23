# Correos, adicionales y carpetas de cada embarque

19/10/2026, Ecuador. Interfaz `20261019-55`.
Versión fija: `itsanet-20261019-correo-adicionales-55`.

## Revisión y actualización de Drive

Una foto guardada y copiada puede conservar una carpeta de una organización
anterior. Ahora se compara su embarque y ruta vigentes con las rutas registradas
en la última copia confirmada por el puente de Google.

- **Sincronizada:** la copia está confirmada y corresponde a su ruta actual.
- **Asignar embarque:** un SKU o bulto tiene varios destinos posibles. El
  supervisor debe elegir; el sistema no adivina ni reparte la foto entre ellos.
- **Actualizar carpetas:** el archivo existe en Drive pero conserva una ruta
  anterior o de otro embarque. Se ofrece actualizar el destino.
- **Copia pendiente:** aún debe terminar o confirmarse la sincronización.

El supervisor entra a **Fotos → Actualizar carpetas por embarque**. La ventana
muestra nombre, destino propuesto, clasificación y rutas registradas. Selecciona
el embarque de cada vínculo que lo requiera y pulsa **Actualizar carpetas y
fotos**. Después usa **Actualizar** para comprobar la confirmación. Para una
ruta antigua cuyo embarque ya está identificado también sirve **Reintentar
pendientes de Drive**.

```text
RECEPCIÓN/
  EMBARQUES/
    EMB-A/
      SOBRANTE/SKU/
      FALTANTE/SKU/
      PNC/SKU/
      BULTOS/Bulto01_.../
    EMB-B/
      SOBRANTE/SKU/
      FALTANTE/SKU/
      PNC/SKU/
    POR-ASIGNAR/              pendiente de decisión del supervisor
  GENERALES/                 panorámicas comunes de la recepción
```

Funciona con varios archivos packing list y con un solo archivo que contiene
varios embarques. Solo se crean las carpetas que tienen evidencia. La operación
conserva el mismo `fileId`, no vuelve a subir el binario ni manda correos. No
reabre una recepción cerrada ni cambia conteos o clasificaciones históricas.
Las rutas antiguas pueden conservar accesos directos para no romper enlaces de
informes anteriores; esos accesos no son otra copia del archivo.

Si otro usuario cambia las fotos desde que se abrió la ventana, se pide
actualizar la vista previa. Si hay una copia en proceso, se espera su
confirmación. Cambiar la asignación de embarque requiere resolver antes un envío
automático activo en Entregas, para preservar el correo revisado. Una entrega
antigua tampoco continúa automáticamente con fotos en rutas incorrectas.

Los enlaces de carpetas desactualizadas no se presentan como enlaces vigentes
en el nuevo Excel o correo. La comprobación utiliza el último acuse almacenado;
no es una inspección remota continua de Drive ni comprueba cambios hechos a mano
fuera de la aplicación. La actualización solicita de nuevo la confirmación del
puente. Se mantienen los permisos de Google existentes.

## Correos y documentos separados

Cuando se identifican varios embarques, se exige revisar sus correos por
embarque, aunque todos provengan de un solo packing list. Para listas sin varios
embarques identificados se conserva la alternativa por packing list.

Cada correo toma sus resultados, fotos, carpetas y documentos. Un SKU compartido
requiere revisar su reparto de cantidades y PNC. Las observaciones y pallets del
SKU global no se copian automáticamente a ambos embarques: se completan en el
reparto del supervisor. El encabezado identifica primero el grupo que se está
revisando; debajo conserva la recepción como referencia.

En **Editar redacción y destinatarios** están disponibles estos datos opcionales:

- Identificación del contenedor, por ejemplo `C1`.
- Tipo, por ejemplo `1x40`.
- Fecha operativa; el texto calcula su día de la semana en español.
- Número de pallets, ubicación y rango de pallets.
- Condición o nota de ubicación, por ejemplo «Hasta finalizar el contenedor».

Si se completan `C1`, `48`, `CALLEKL`, `A01` y `A09`, aparecen como un bloque
operativo en el correo. Son datos editables del correo correspondiente; no se
registran esos ejemplos como datos de todas las recepciones. Los campos vacíos
no inventan un contenedor, una fecha o ubicación. Se validan fecha y número de
pallets antes de guardar. Se mantienen la selección de fotos, notas libres,
copia completa, descarga HTML y revisión antes del envío.

## Hoja ADICIONALES y enlaces directos

Los formatos **Para enviar al cliente** e **Informe ampliado** incluyen la hoja
**ADICIONALES** cuando existen productos fuera del packing list o sobrantes.

- Un producto no declarado muestra su cantidad física, descripción, pallet,
  motivo, observación, packing list y embarque correspondiente.
- Un sobrante de SKU declarado muestra únicamente la diferencia positiva. Se
  advierte que esa cantidad ya está incluida en el resultado físico del packing
  list y no debe sumarse nuevamente.
- Si un adicional se contó en dos listas del mismo embarque, cada documento
  recibe la cantidad y observación de su propia lista. No se repite el total.
- Una asignación incompatible con el packing list de su conteo se debe corregir
  antes de preparar el envío.
- **EVIDENCIAS** incluye enlaces de las carpetas confirmadas del adicional en
  su propio contexto. La primera URL es un hipervínculo; las demás permanecen
  en el texto de la celda. Sin confirmación se indica la ausencia del enlace.

Se conservan las filas del packing list original. Los enlaces de un embarque no
se toman del agregado de otro embarque que tenga el mismo SKU. La vista y el
correo se actualizan con los metadatos vigentes al preparar una nueva revisión;
los archivos ya archivados se conservan como documentos históricos.

## Bitácora y tamaño de datos

El Excel auditable ya no genera una hoja **AUDITORIA**. Se mantiene **BITACORA**
con las fechas de la API o Firestore expresadas en Ecuador, los conteos, el
operador y los enlaces de fotos confirmadas. Una fecha de origen ausente se
identifica como no registrada; no se inventa.

Esta decisión no elimina la auditoría ni eventos de MySQL. No hay nuevas tablas,
migraciones, dependencias o claves HMAC. La organización reutiliza la cola y los
metadatos existentes y no duplica imágenes. Los informes actuales se reutilizan
si su contenido y metadatos coinciden; cambiar enlaces o resultados requiere una
nueva versión para preservar la trazabilidad.

## Pase a producción

GitHub y el servidor empresarial se actualizan por separado. Coordinar una pausa
breve de registros y ejecutar esta única línea en Linux **@apps**:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin --tags && revision_itsanet="$(git rev-parse 'itsanet-20261019-correo-adicionales-55^{commit}')" && git show "$revision_itsanet:scripts/actualizar_produccion.sh" > /tmp/itsanet-pase55.sh && bash /tmp/itsanet-pase55.sh "$PWD" "$revision_itsanet"
```

El procedimiento existente realiza un respaldo privado, comprueba requisitos,
actualiza el código, reinicia únicamente `iv-itsanet` y comprueba su arranque. No
copia usuarios, credenciales, recepciones ni volúmenes del entorno de pruebas. No
ejecuta una organización masiva de archivos históricos al instalarse.

Después abrir **https://apps.flexnetuio.com:8443/app/** y recargar con Ctrl+F5.
Probar una recepción con dos embarques y una fotografía antigua: revisar la ruta,
aplicar la actualización y esperar la confirmación. Preparar los documentos
vigentes y revisar cada correo antes de enviar. La URL y la conexión HTTPS
empresarial se mantienen.

## Validación

Las pruebas usan SQLite/MySQL aislados, Chromium y respuestas de Google simuladas;
no escriben en Drive, correo o MySQL empresarial. Incluyen mismo SKU en dos
embarques, un solo archivo con dos embarques, recepción histórica cerrada,
adicionales repartidos entre listas, enlaces propios, fecha de bitácora y
actualización con el mismo identificador de foto, sin retransmitir su contenido.
Resultados comprobados:

- Suite general: **1.251 pruebas correctas**.
- MySQL aislado: **35 correctas** en agrupación, fotos y correos; pasada final
  de protección de rutas y entrega anterior: **5 correctas**.
- Regresión final de entrega y correo: **18 correctas**.
- Excel/gestión: **33 correctas**; formato: **21 correctas**; páginas: **65**
  comprobaciones de sintaxis y referencias correctas.
- Chromium y MySQL: revisión de una recepción cerrada con dos packing lists,
  cierre manual de una recepción con un archivo y dos embarques, adicionales
  solo en el documento propio, campos operativos editables por correo y
  organización de una foto ambigua mediante el supervisor.
- Vista móvil de 390 px: sin desbordamiento del organizador y permisos de
  operario verificados. Reubicación Drive simulada: mismo fileId, sin binario.

La suite general se ejecutó antes del último caso añadido de protección de una
entrega antigua; ese caso se comprobó después en SQLite y MySQL. Las pruebas de
Google son simuladas; el pase y la comprobación final del Drive empresarial
corresponden al servidor real.
