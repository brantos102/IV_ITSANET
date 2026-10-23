# Fotografías separadas por embarque

19/10/2026, Ecuador. Interfaz `20261019-54`.
Versión fija: `itsanet-20261019-fotos-embarques-54`.

## Organización en Drive

Las nuevas fotos identifican su embarque de forma independiente del archivo
packing list. También funciona cuando un mismo archivo contiene varios
embarques. La ruta parte del repositorio, cliente, marca y recepción ya
configurados:

```text
RECEPCIÓN/
  EMBARQUES/
    RB654123/
      SOBRANTE/SKU/
      FALTANTE/SKU/
      PNC/SKU/
      SKU/                     fotos de validación sin novedad
      BULTOS/Bulto01_.../       fotos de bulto y sus cajas
    RB654124/
      SOBRANTE/SKU/
      FALTANTE/SKU/
      PNC/SKU/
    POR-ASIGNAR/                evidencia antigua de destino ambiguo
  GENERALES/                   panorámicas compartidas de recepción
  INFORMES/
```

Las carpetas se crean cuando tienen evidencia. Los nombres de embarque se
normalizan para usarlos como carpetas; si dos códigos distintos contienen
símbolos que producirían el mismo nombre, se añade una huella para mantenerlos
separados. Los bultos y cajas mantienen sus subcarpetas dentro del embarque.

## Al subir fotografías

1. Selecciona las fotos desde la ficha del producto, el ingreso de bultos o el
   modal de evidencias.
2. Si el SKU y packing list identifican un único embarque, se propone ese
   destino automáticamente.
3. Si hay varias posibilidades, selecciona **a qué embarque pertenecen estas
   fotos**. Un lote corresponde a un destino; carga otro lote para otro embarque.
4. Las panorámicas de toda la recepción pueden guardarse en **GENERALES**.
   Los detalles de productos o bultos deben identificar su embarque.
5. Guarda y revisa la confirmación del servidor y después la copia a Drive.
   La galería y el Excel de trazabilidad muestran el embarque de cada vínculo.

La elección se conserva al reintentar el mismo lote y en la copia temporal
recuperable del navegador. Cancelar la elección conserva las fotos seleccionadas.
El servidor rechaza un embarque incompatible con las filas conocidas de ese SKU
y packing list. Los clientes anteriores que no envían la elección siguen
funcionando: una foto ambigua queda en POR-ASIGNAR y no se atribuye por intuición.

Si todavía no hay packing list ni códigos de embarque registrados, el ingreso
fotográfico inicial continúa como antes. Después se puede completar la
asignación con los datos reales.

## Fotografías ya guardadas

El supervisor abre **Fotos → Organizar fotos**. La ventana **Organizar nombres y
carpetas** muestra las rutas propuestas y permite elegir el embarque de cada
vínculo. Tras revisar, pulsa **Organizar estas fotografías**.

La organización permite asignar fotografías de una recepción cerrada sin
reabrirla. Conserva clasificación, archivo, fecha, secuencia y conteos. La
asignación queda auditada; no programa un correo ni cambia el acuse de la entrega
original. Si las fotos o sus asignaciones cambiaron desde que se abrió la vista,
se pide actualizar antes de aplicar. Las fotos que se están copiando deben
terminar antes de organizarse.

Si hay un envío automático pendiente o en revisión, se debe resolver en
**Entregas** antes de cambiar el embarque de las fotos. Así se conserva la
selección del correo ya revisado y se evita modificar su contexto durante el
envío.

La foto histórica de FALTANTE sigue en FALTANTE aunque después aparezca el
producto y se registre una foto PNC nueva. Cambiar la clasificación continúa
siendo una corrección explícita del supervisor, separada de asignar el embarque.

Las rutas anteriores conocidas se conservan como accesos directos cuando cambia
la organización por embarque, para mantener los enlaces de informes anteriores.
Se mantiene el mismo identificador de archivo en Drive. No se duplican binarios.

## Una misma fotografía en varios destinos

Si se selecciona intencionalmente la misma imagen para dos embarques, se guarda
un archivo con dos vínculos y un acceso directo en el segundo destino. Reintentar
el lote no añade otra copia ni otro vínculo idéntico. La carpeta del SKU se
confirma por cada vínculo, incluso si SKU y clasificación coinciden entre ambos
embarques.

En un correo separado por embarque, solo se incluyen sus vínculos. Una foto con
embarque explícito deja de tratarse como evidencia ambigua de un SKU compartido.
Las panorámicas generales pueden seguir sirviendo como contexto común.

## Compatibilidad y almacenamiento

- No hay nuevas tablas, dependencias ni claves HMAC.
- Se utiliza el puente Google actual con rutas de evidencias y fotos auditables;
  este cambio no necesita reemplazar su despliegue Apps Script.
- La asignación se guarda como metadato pequeño de la identidad existente del
  archivo. El binario se conserva una sola vez; no se almacena dentro de MySQL.
- Las reubicaciones usan el mismo `fileId`; no vuelven a enviar el contenido de
  una imagen que Drive ya confirmó.
- La consulta de embarques lee solo identificación de las filas; no descarga las
  celdas completas del Excel por cada foto ni añade bloqueos para abrir la galería.
- Se mantienen las reservas y reintentos durables de Drive, la recuperación de
  fotos del navegador y los permisos de operario/supervisor.

## Pase a producción

La publicación en GitHub no actualiza por sí sola el servidor empresarial.
Coordinar una pausa de registros y ejecutar esta única línea en Linux **@apps**:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin --tags && revision_itsanet="$(git rev-parse 'itsanet-20261019-fotos-embarques-54^{commit}')" && git show "$revision_itsanet:scripts/actualizar_produccion.sh" > /tmp/itsanet-pase54.sh && bash /tmp/itsanet-pase54.sh "$PWD" "$revision_itsanet"
```

Usa el procedimiento existente de respaldo privado y comprobación de arranque;
requiere una pausa breve de `iv-itsanet`. Incluye las mejoras de la versión 53,
por lo que no hace falta instalarla por separado si todavía no se aplicó.
No copia datos, usuarios ni credenciales del entorno de pruebas.

Después entrar a **https://apps.flexnetuio.com:8443/app/**, recargar con Ctrl+F5
y comprobar dos embarques con fotos distintas. Las fotografías ya confirmadas
se organizan desde la vista previa del supervisor; instalar la versión no
ejecuta una migración masiva de archivos.

## Verificación realizada

- Suite general: **1.238 pruebas correctas**.
- Pasada final MySQL aislado: **12 correctas**, incluidas concurrencia de dos
  operarios, recuperación de vínculos añadidos durante la copia y lectura del
  plan vigente pese a una sesión con snapshot anterior.
- Regresión final de fotos y agrupación: **28 correctas y 3 omitidas** por
  requerir MySQL; esos casos se ejecutaron en la pasada MySQL anterior.
- Puente Google con Drive simulado: **17 correctas**. Se comprobó la jerarquía
  real de carpetas y los accesos directos sin cambiar el puente desplegado.
- Chromium y MySQL aislado: selección de embarque como operario, una sola
  imagen con dos destinos PNC, cancelación sin subida ni pérdida, permisos de
  organización y visualización móvil de 390 px sin desbordamiento.
- Sintaxis y referencias de interfaz: **65 comprobaciones correctas**.

Estas pruebas usan datos simulados y no envían correos ni escriben en Drive o
en la base empresarial. El pase real y la comprobación de sus carpetas se
realizan desde el servidor empresarial.
