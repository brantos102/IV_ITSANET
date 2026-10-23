# Versión 66 · etiquetas de bultos

Los dos tamaños, 100 × 150 mm y 100 × 50 mm, muestran únicamente:

- Nombre del cliente de la recepción.
- Rótulo del bulto, por ejemplo `G01`.
- Código de barras CODE128 que devuelve ese mismo rótulo al escanearlo.

Se aplica a vista previa, navegador/PDF y nuevas solicitudes ZPL o mediante PC
puente. Se conserva la impresión por números o rangos, sin renumerar bultos.
El tamaño compacto también muestra el nombre del cliente.

Marca, recepción, total, código madre e identificadores internos siguen guardados
en sus registros e instantáneas; ya no se imprimen como campos adicionales. Las
solicitudes históricas conservan su ZPL original: para obtener el nuevo diseño,
preparar una nueva solicitud de impresión o reimpresión.

No requiere migración de base de datos ni cambios en Google. Aplicar con el
actualizador con respaldo y recargar los equipos para tomar `20261023-66`.
Imprimir al 100 %, sin márgenes ni encabezados del navegador.

Validación: 21 pruebas de API para identidad, reintentos, rangos, permisos y
consolidación; 115 verificaciones de navegador, importaciones y etiquetas.
Se generaron PDF de ambos tamaños, una página por etiqueta; un lector CODE128
independiente recuperó `G01`, `G1000` y `P51` desde capturas y desde los PDF
rasterizados a 203 dpi. Vista previa comprobada en anchos de 393 y 1200 píxeles,
sin desbordes y con selección parcial conservada. La lectura se verificó por
software; corresponde confirmar una etiqueta en la impresora y handheld de la
operación al aplicar la actualización.
