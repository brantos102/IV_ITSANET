# IV ITSANET · Versión 70 · Relaciones de códigos y guía operativa

Fecha: 9 de noviembre de 2026. Recursos web: `20261109-70`.

Esta entrega es un candidato validado en desarrollo. No acredita una actualización del servidor corporativo ni una importación en su base de datos. Apache, MySQL, las cuentas Google y las rutas operativas existentes no se reconfiguran.

## Cambios

- Relaciones de códigos por cliente: `CLIENTE_ID` + `CODIGO` resuelven el `PRODUCTO_ID` canónico. Se preservan ceros iniciales; la equivalencia UPC-A/EAN-13 exige dígito de control válido. Un resultado ambiguo se bloquea. Las lecturas, búsquedas y etiquetas usan el SKU resuelto.
- `CANTIDAD` representa unidades por empaque/código. La ficha ofrece **Usar 1 empaque = N unidades**: requiere pulsación explícita, no registra un conteo por escanear ni modifica automáticamente una cantidad ya escrita. Para varios empaques se verifica la cantidad física total. Los factores vacíos o cero requieren revisión.
- Los filtros retiran **No aparecieron**. Un cero confirmado se presenta como faltante; un ítem sin revisar sigue pendiente. Se añade **Con PNC** sin borrar eventos históricos.
- La edición general del total de bultos transmite confirmación y motivo al reducir. Los controles existentes de ocupación, versión e impresión siguen aplicándose. No se borran bultos históricos para consolidar.
- Se imprimen también subbultos ya registrados, como `A01.1`, cuyo bulto padre tenga rótulo emitido. No se crean ni renumeran cajas para imprimir. Se conservan las selecciones de lote completo, números y rangos.
- La etiqueta de producto 100 × 50 mm separa barras, SKU y datos auxiliares. La impresión rechaza códigos demasiado largos para conservar un módulo legible; no los recorta. Es necesaria la comprobación física con la impresora, papel y lector de cada estación.
- Los accesos directos de Drive reservan identidad por cuenta, carpeta y archivo: un reintento tras perder la respuesta reutiliza el ID. Las reservas existentes de carpetas y archivos se conservan. No se realiza limpieza automática de duplicados históricos.

## Base de datos y compatibilidad

El arranque añade únicamente la tabla ausente `producto_relaciones`, con clave primaria compuesta cliente/código, SKU, código original, tipo, factor decimal de tres posiciones, usuario y fecha. El modelo pasa a declarar 31 tablas. La nueva tabla no cambia la clave global de `productos`, no crea existencias y no reescribe recepciones, packing lists ni conteos.

La separación de estas relaciones por cliente es una ampliación concreta; no equivale a una segregación integral de todos los módulos para V2.

## Carga del archivo corporativo

Después del pase controlado, entrar como supervisor o administrador: **Recepciones → Catálogo → Importar códigos de barras**. Elegir el archivo original `RELACION_CODIGOS.xlsx`, hoja `RL_CODIGOS`, revisar y confirmar.

La lectura del archivo suministrado produjo 12.480 filas, 12.411 relaciones únicas de 71 clientes y 69 filas equivalentes por normalización de separadores. En 705 relaciones no hay factor positivo. Los valores conocidos se conservan frente a equivalentes vacíos. Los conflictos de SKU o de factores positivos dentro del mismo cliente se rechazan y se revierte la importación completa.

La reimportación de ese mismo archivo creó cero filas nuevas. Se ensayó con SQLite y MySQL aislados. El Excel no se incorpora al repositorio ni se carga al arrancar la aplicación. Debe conservarse como dato corporativo bajo control de acceso.

## Documentación

`scripts/generar_manuales_word_70.py` genera HTML independientes, con imágenes incrustadas, a partir del Word autorizado. Necesita las capturas de referencia indicadas por `--referencias`; no conecta con el servidor. Los documentos con imágenes operativas se entregan por separado y no se publican en Git.

La revisión encontró 38 de los 40 pasos del Word y marcos vacíos en los pasos 24 y 33. Se preservan las capturas aportadas, se identifican las referencias de pruebas y se restituyen los pasos 39 y 40 con espacio para captura real. El paso 33 explica cómo capturar la separación de correos antes de guardar o enviar.

## Validación realizada

- `PATH="$PWD/.venv/bin:$PATH" node pruebas.js`: 1.542 pruebas aprobadas, incluidas 930 de Python.
- Selección adicional de pruebas sobre MySQL aislado: 174 aprobadas. No se usó la base corporativa.
- Archivo real: importación y reimportación completas en MySQL; 12.411 registros persistidos, sin altas de productos ni conteos.
- Navegador: lectura EAN por cliente, cantidad conservada hasta confirmar el empaque, filtros vigentes, selección de subbulto y decodificación del código de la etiqueta renderizada. No sustituye una prueba de la impresión física.
- Documentos: 40 pasos, carga de imágenes, ampliación, búsqueda, descarga del HTML completado, funcionamiento sin conexión y visualización móvil sin desbordes en el tamaño probado.

## Pase y mantenimiento

Usar un commit completo de esta entrega y el procedimiento existente `scripts/actualizar_produccion.sh`, en una pausa operativa comunicada. Este procedimiento comprueba el servicio y el árbol de trabajo, prepara dependencias, respalda base/archivos/configuración, aplica avance lineal y verifica el arranque. No usar `git reset --hard`, reinstalar MySQL ni reemplazar el archivo de entorno.

Después: recargar pantallas, comprobar una recepción existente, importar las relaciones, leer un código conocido de cada cliente habilitado, confirmar cantidades y probar una etiqueta. Revisar que Drive confirme la evidencia y que los informes conserven su estructura. Las mejoras no reconectan por sí solas una cuenta Google revocada.

Si se recupera el código anterior, la tabla nueva puede permanecer sin uso; no hace falta borrarla. Una recuperación de código no revierte datos operativos. Antes de cualquier restauración de datos debe evaluarse la actividad posterior al respaldo.
