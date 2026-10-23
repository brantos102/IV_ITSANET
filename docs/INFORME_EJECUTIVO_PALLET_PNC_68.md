# Versión 68 · PALLET y posición del informe del ejecutivo

El informe del ejecutivo (`envio` y `envio-ampliado`) ya no mezcla identificadores
con cantidades. Se conserva la asignación por registro y fila del packing list;
no se cambian conteos, incidencias, pallets guardados ni posiciones del sistema.

| Campo | Resultado del ejemplo |
| --- | --- |
| Cantidad física | 30, celda numérica |
| PALLET, columna L del ejemplo | `G64-G68` |
| POSICION FINAL SUGERIDA, columna Q del ejemplo | `BM-Q-10-5-BM-Q-10-6` |
| Nueva columna al final, R en este ejemplo | DETALLE DE UNIDADES Y PNC POR PALLET |

La columna final explica cantidades y condición por pallet/posición. Por ejemplo,
si de las 20 unidades en G64 hay 2 PNC, indica 2 PNC en G64 y su posición,
18 conformes en G64, y las 10 conformes en G68 y su posición. **Este desglose
PNC es una demostración; no se deduce de la captura ni modifica datos reales.**

## Reglas de salida

- Las columnas originales conservan encabezados, orden, datos y cantidad de
  filas. El ampliado mantiene su organización guardada. La columna explicativa
  nueva se agrega después del resto, sin mover las columnas originales.
- PALLET y posición contienen letras/números, guion y punto. Los nombres se
  separan con guion, sin cantidades, paréntesis ni barras. Un mismo identificador
  aparece una sola vez por fila. Los ceros y subpallets como `G04.1` se conservan.
- Los identificadores salen de los registros asignados a esa fila y lista.
  Un SKU repetido no toma los pallets de otras líneas ni de otros packing lists.
  La columna final identifica qué unidades son PNC y cuáles conformes, así como
  otras incidencias registradas; no añade filas al packing list.
- Un identificador inválido detiene la generación del ejecutivo con un mensaje
  que indica el ítem y el dato que debe corregirse. No se borran símbolos para
  inventar otro identificador ni se modifica el registro original.
- Las filas antiguas sin registros vinculados mantienen los identificadores
  recuperables y señalan el desglose pendiente. Una PNC sin cantidad validada
  queda por revisar; no se declara como cero ni se inventa su distribución.
- Un desglose cuya suma difiere de la cantidad física detiene la generación.
  Las correcciones y anulaciones siguen excluyendo los registros retirados.
- La vista previa usa el mismo resultado de exportación. UBICACIONES conserva
  el detalle existente. El informe auditable mantiene su presentación y bitácora.
  ADICIONALES mantiene su estructura y limpia PALLET en los formatos de envío.
- Se preservan los tipos numéricos y las fórmulas de las columnas originales.

## Documentos preparados antes de la actualización

La revisión del generador pasa a 68. Los archivos anteriores permanecen en el
historial para consulta/descarga, pero no se reutilizan como revisión vigente
ni como adjuntos vigentes del correo. Tras actualizar, preparar una versión
nueva, revisar/seleccionar los documentos y sus nombres antes de enviar.
La reserva anterior a la actualización tampoco puede archivarse como nueva.

No se modifican entregas ya enviadas ni se envía ningún correo automáticamente.
Una entrega que ya estaba en proceso se gestiona mediante su confirmación
existente; actualizar no sustituye sus adjuntos ni crea un reenvío.

## Actualización y verificación

Usar `scripts/actualizar_produccion.sh` con el commit completo indicado en la
entrega. Coordinar la pausa de registros durante el respaldo/actualización y
recargar las pantallas de PC y handheld para cargar `20261023-68`.

No requiere borrar datos, reimportar packing lists ni migraciones destructivas.
La conexión Google central, las fotos y las carpetas conservan su configuración.

1. Preparar una revisión nueva del informe del ejecutivo y descargarla.
2. Verificar que L/Q conservan identificadores y que las cantidades están en
   la columna final; las letras exactas dependen de cada formato original.
3. Contrastar cantidad física, PNC, conformes y ubicaciones con los registros.
4. Revisar el ampliado, la auditoría y los nombres/selección de adjuntos.
5. Guardar y enviar solo después de validar los documentos finales.

Pruebas reproducibles: `node firebase/test/informe-ejecutivo68.test.mjs`,
`.venv/bin/python -m pytest -q tests/test_revision_exportacion_68.py` y
`PATH="$PWD/.venv/bin:$PATH" node pruebas.js`.

La validación local no acredita una importación en Depot ni un envío real de
producción. Esas comprobaciones corresponden al servidor y al ejecutivo.
