# Lecturas, etiquetas y navegación — versión 41

Versión de interfaz `20261018-41`. Etiqueta de publicación: `itsanet-20261018-lecturas-interfaz-41`. Incluye las mejoras de correo revisable de la versión 40.1.

## Lecturas contrastadas con el catálogo

Se conserva el SKU completo cuando existe. La lectura admite separadores del lector (guiones, espacios, comillas rectas o curvas) y datos posteriores de lote o relleno. No se modifica el código registrado del producto.

- `2GJ'805'901'C '04100000` busca `2GJ805901C`.
- `2GJ-941-113 00000` busca `2GJ941113`.
- Los SKU que contienen ceros, por ejemplo `06J103600AM` o `ABC12300000`, conservan sus ceros si existen.
- Una diferencia de una letra o un dígito, incluida su repetición u omisión, propone productos existentes del catálogo completo y de la recepción. Muestra código, descripción, cliente y pertenencia al packing list; exige elegir antes de consultar.
- Si `2GJ9411113` existe como producto, se respeta exactamente. Si no existe, puede sugerir `2GJ941113` cuando esté registrado. No se intercambian automáticamente.
- Quitar ceros o un lote pegado sin separación exige confirmación. Si la lectura contiene dos códigos reales, el operario elige cuál consultar.

Consultar o aceptar una sugerencia no crea una equivalencia ni registra un conteo. Los avisos existentes de producto de otro cliente y de adicional continúan activos.

## Etiquetas de bultos

Rótulo y barras ampliados en 100 × 50 mm y 100 × 150 mm. Solo se imprime el literal con la secuencia mínima de dos dígitos (`B01`, `B02`, `B100`) y su CODE128. Se conservan los identificadores físicos, el historial y la protección contra solicitudes duplicadas.

La vista previa comparte el diseño de impresión y se adapta al ancho de pantalla. Muestra hasta tres etiquetas; la impresión incluye todo el lote. ZPL aumenta y centra las barras, con espacio libre a sus lados.

Imprimir a escala 100 %, con el tamaño elegido en el controlador y sin márgenes ni encabezados. La lectura del SVG se comprobó con ZXing; el tamaño físico y la calidad final requieren una impresión en la Zebra de bodega.

## Columnas y fotografías

El modal de columnas separa la elección del embarque, los campos agrupados y la vista previa. Cada selector presenta su destino y un dato real; cuando está vacío muestra un ejemplo señalado como orientativo. Las columnas incompatibles se identifican como protegidas. Las nuevas columnas de posición, código de barras, marca y cliente se pueden completar al final del informe ampliado.

El bloque original conserva encabezados, orden y datos de origen. Las columnas de resultado se rellenan en sus posiciones compatibles. La numeración de filas aparece como una guía pequeña `#`. La muestra contiene hasta seis registros por página y resalta los destinos seleccionados. Guardar esta configuración no genera un informe ni envía correo.

Fotos distingue «Adjuntar fotografías» y «Fotografías guardadas». La selección muestra miniaturas antes de guardar. La galería mantiene vistas previas autenticadas, ampliación, clasificación por SKU y estado de copia a Drive. Se mantienen las rutas de evidencias y la secuencia de la guía fotográfica.

## Teclado

- En los formularios de datos, Enter avanza al siguiente campo y confirma al final. Los campos obligatorios y los correos inválidos impiden continuar y reciben el foco.
- En listas, Enter mantiene la selección nativa y Tab avanza. En columnas, Ctrl+Enter guarda la configuración.
- En textos de varias líneas, Enter escribe un salto; Ctrl+Enter confirma o actualiza el borrador, según el diálogo.
- En filtros de fotos, Enter aplica el filtro. En etiquetas, Enter avanza y Ctrl+Enter ejecuta la acción de impresión elegida.
- Los botones conservan Enter y espacio. Escape cierra el diálogo cuando no hay una operación en curso. El foco inicial se asigna después de abrirlo.
- Editar el correo con el teclado actualiza el borrador; conserva la confirmación explícita del envío. Los detalles opcionales del ingreso no cambian de bulto automáticamente.

## Cabecera

Menú de Inicio, Recepciones, Validar, KPIs, Equipo, Mi cuenta y Administración según el rol. Catálogo e impresión general siguen disponibles para supervisores y ADMIN. Incluye reloj con fecha y hora de Ecuador; usa el reloj del equipo y no modifica los tiempos de auditoría.

La barra muestra código de recepción, referencias verificadas, unidades contadas y porcentaje con los mismos datos recibidos por la pantalla. Al fallar la conexión señala que son los últimos datos confirmados. Fuera de la recepción no presenta avance ni recuerda otra recepción como activa.

Día/Noche guarda la preferencia en el navegador y la aplica durante el arranque. Las vistas de documentos y etiquetas conservan la presentación del archivo o papel.

## Instalación en producción 3002

Desde la terminal del servidor `apps`, con el servicio `iv-itsanet` activo:

```bash
cd ~/bryan/IV_ITSANET &&
git fetch origin tag itsanet-20261018-lecturas-interfaz-41 &&
VERSION_ITSANET=$(git rev-parse 'itsanet-20261018-lecturas-interfaz-41^{commit}') &&
SCRIPT_PASE_ITSANET=$(mktemp /tmp/itsanet-pase.XXXXXX.sh) &&
git show "${VERSION_ITSANET}:scripts/actualizar_produccion.sh" > "$SCRIPT_PASE_ITSANET" &&
bash "$SCRIPT_PASE_ITSANET" "$PWD" "$VERSION_ITSANET"
```

El actualizador comprueba el respaldo de MySQL, archivos y configuración antes de instalar, pausa el servicio durante el pase, conserva los datos de producción y verifica salud e interfaz. Intenta recuperar el código anterior si falla el arranque. No ejecutar las pruebas sobre producción. No es necesario importar una base de datos de desarrollo ni volver a configurar usuarios o HMAC por esta actualización.

Al terminar debe aparecer «Servicio y página de acceso confirmados», el código instalado y la carpeta privada del respaldo. Actualizar el navegador con Ctrl+F5. Las instrucciones de publicación de Apps Script para correo editable, si todavía están pendientes de la versión anterior, están en [Supervisión, correo y pruebas 40](SUPERVISION_CORREO_Y_PRUEBAS_40.md).

## Verificación

- Validación total: 1.098 pruebas aprobadas, 628 de servidor y 470 de JavaScript (suite completa de 1.097 más la nueva prueba de exportación al final del formato). Las pruebas que requieren archivos privados o servicios externos mantienen sus omisiones declaradas.
- 17 pruebas nuevas de lecturas con separadores, caracteres distintos, ceros reales, metadatos, catálogo de otro cliente y ausencia de escrituras al consultar.
- MySQL 8.4: 62 pruebas de lecturas, contraseñas e impresión aprobadas sobre una base desechable independiente.
- Chromium de escritorio y móvil: escaneo, confirmación de candidatos, avance recibido en vivo, navegación, reloj, persistencia de tema, teclado y validación, elección y guardado D→E, fuente Excel conservada, etiquetas adaptables, CODE128 leído como B01, descarga ZPL mediante teclado, selección y carga de foto real y ampliación.
- Datos de prueba sintéticos en el entorno aislado. No se envían correos reales ni se imprime en equipos de producción desde estas comprobaciones.
