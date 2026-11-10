# Etiquetas de bultos y fotos al terminar

Disponible para SUPERVISOR/ADMIN desde **Recepciones → Bultos / evidencias**.
En la validación también se encuentra en **Recepción actual**. Frontend
`20261016-32`; entrega `itsanet-20261016-bultos-etiquetas`.

## Confirmar e imprimir

1. Pulsar **Etiquetas de bultos**. El total parte de lo registrado en recepción;
   se puede corregir antes de confirmar. Literal editable de una a ocho letras
   o números, por ejemplo `B`, `P` o `CAJA`.
2. Elegir **10 × 15 cm** o **10 × 5 cm**: 100 mm de ancho y 150 o 50 mm de
   alto, una etiqueta por bulto. El ZPL corresponde a 203 dpi.
3. Elegir destino: **Imprimir / PDF en esta PC**, **Descargar ZPL**, o una
   **impresora mediante PC puente** configurada en Administración.
4. Pulsar **Confirmar e imprimir**. Si hay diez bultos se generan diez etiquetas,
   desde `B-001 · BULTO 1 DE 10` hasta `B-010 · BULTO 10 DE 10`.

Cada etiqueta incluye recepción, cliente, marca disponible, número/total y un
código de barras interno exclusivo de la unidad. La de 10 × 15 muestra además
la caja madre cuando existe. La identidad de la unidad no cambia al reimprimir;
no reemplaza la etiqueta del proveedor. Si se escanea una etiqueta interna desde
otro bulto, se exige abrir el bulto correspondiente para no mezclar sus fotos.

La preferencia de literal/tamaño queda guardada en la recepción. Cada lote
conserva instantánea, autor, fecha, destino y número L1, L2… **Solicitudes anteriores**
advierte sobre los lotes ya generados. **Actualizar / nueva solicitud** permite
preparar una reimpresión consciente. Los reintentos de una solicitud conservan
su identificador; dos supervisores con información desactualizada no generan
dos lotes simultáneamente: uno debe actualizar los datos.

Se pueden añadir bultos manteniendo los identificadores existentes. Un bulto
etiquetado o con registros no se elimina al reducir el total. Si cambia el total,
se deben reemplazar las etiquetas anteriores para que todos los denominadores
coincidan. Las recepciones cerradas no emiten nuevas etiquetas; deben reabrirse
para corregir sus datos operativos.

En la PC usar escala 100 %, papel del tamaño elegido y desactivar encabezados,
pies y márgenes adicionales. **GENERADA** indica preparación del lote, no prueba
que se imprimió físicamente. **PENDIENTE** corresponde a la cola del puente y
**ENVIADA** a su confirmación de transmisión. Revisar el resultado en la Zebra.

## Fotografiar cómo queda la mercadería

Pulsar **Fotos del estado final**. Se admiten varias imágenes sin límite de
cantidad por recepción, mediante la cámara nativa, Cámara de Windows/Galería
o selección de archivos. Clasificación fija **Estado final de la mercadería**;
no solicita SKU ni aumenta el conteo.

Drive organiza las fotos nuevas bajo la recepción, en
`RECEPCION/ESTADO_FINAL` —con subcarpetas de bulto/lista si se vinculan—.
La galería de esta opción filtra ese tipo de evidencia y permite abrir su
carpeta cuando Drive confirma la copia. MySQL conserva metadatos; la imagen
permanece temporalmente en el servidor hasta confirmar Drive.

También se permite agregarlas después del cierre, exclusivamente por
SUPERVISOR/ADMIN. Quedan registradas como **EVIDENCIA_POSTCIERRE**, con usuario,
fecha y archivo. No reabren la recepción, cambian cantidades, sustituyen informes
anteriores ni envían otro correo. Los otros tipos de evidencia siguen requiriendo
reapertura para modificar una recepción cerrada. Para depurar evidencias después
del cierre, reabrir según el procedimiento operativo existente.

## Comprobaciones

Se verificaron en navegador los dos tamaños mediante PDF: una página por bulto,
códigos correlativos y sin desbordamientos; descarga ZPL y fotos finales desde
una vista móvil de 390 px con recepción cerrada. Las pruebas de API incluyen
dos supervisores, reintentos, máximo configurable, cola del puente, evidencia
posterior al cierre y conservación de un informe XLSX ya archivado.
La impresión física y la copia al Drive empresarial deben comprobarse en sus
equipos y cuenta autorizada. No se transfieren recepciones de prueba a producción.

La suite del proyecto pasó 889 pruebas, y otras 37 se ejecutaron contra MySQL
de pruebas. El código de barras del HTML impreso también fue decodificado con
ZXing para comprobar que identifica la unidad correspondiente en ambos tamaños.
