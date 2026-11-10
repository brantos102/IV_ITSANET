# Impresión de etiquetas: diseño y mantenimiento

La descripción procede del producto o del archivo de stock. El tamaño de letra,
las barras y las posiciones se definen en el código de impresión. No se necesita
modificar tablas MySQL para ajustar la tipografía.

## Comprobación inicial de bultos

La reproducción local de L11 genera un PDF centrado. Un resultado físico desplazado
requiere comprobar también el tamaño y la escala elegidos en el controlador.

1. Abrir `docs/muestras/impresion-20261110/Bulto-L11-100x50.pdf`.
2. Elegir ancho 100 mm y alto 50 mm tanto en el aplicativo como en esa impresión.
3. Imprimir una página por etiqueta, tamaño real/100 %, sin ajuste a página,
   márgenes ni encabezados. Conservar la orientación que respeta ancho 100 y alto 50.
4. Probar una sola etiqueta en un campo de texto vacío. El resultado esperado es `L11`.
5. Si el PDF aparece centrado pero el papel no, comprobar la configuración de esa
   impresión. No compensar un tamaño de papel incorrecto moviendo los campos del diseño.
6. Si no se obtiene lectura física con el PDF de prueba, revisar contraste, consumible,
   resolución del equipo y habilitación de CODE128 con el responsable de impresión.
   La decodificación por software no acredita el estado del cabezal ni del lector físico.

Para reimprimir L11 desde la aplicación, mantener el total real de bultos y elegir
**Solo números o rangos seleccionados → 11**. El literal emitido se conserva.
Un PDF guardado y un trabajo ZPL anterior conservan el diseño con el que se generaron;
una nueva solicitud usa el diseño vigente sin cambiar la identidad del bulto.

## Archivos que controlan cada salida

| Salida | Archivo | Ajuste |
|---|---|---|
| Producto, navegador/PDF | `firebase/public/js/etiquetas.js` | `ESTILO_ETIQUETA`, `htmlEtiqueta` y `barrasDe`. |
| Producto, ZPL descargado | `firebase/public/js/etiquetas.js` | `generarZpl`. |
| Producto, estación/puente | `app/routers/impresion.py` | `zpl`. |
| Bulto/subbulto, navegador/PDF | `firebase/public/js/etiquetas-bultos.js` | `barrasBulto` y `htmlEtiquetasBultos`. |
| Bulto/subbulto, ZPL/estación | `app/services/etiquetas_bultos.py` | `zpl`. |

Las impresiones por navegador y por puente tienen generadores separados. Probar
ambas salidas cuando se cambie un valor compartido.

## Aumentar la descripción del producto

El tamaño actual es **8 puntos**. Estos dos valores deben mantenerse iguales:

```javascript
// firebase/public/js/etiquetas.js
export const DESCRIPCION_ETIQUETA_PT=8;
```

```python
# app/routers/impresion.py
DESCRIPCION_ETIQUETA_PT = 8
```

El generador convierte automáticamente el valor a puntos de impresora para ZPL:

```text
alto ZPL = redondear(puntos_tipográficos × 203 / 72)
8 pt → 23 puntos de impresora
```

El perfil ZPL existente corresponde a 203 dpi. Una impresora de 300 dpi requiere
un perfil completo compatible: ancho, alto y coordenadas, además de las fuentes.
El PDF conserva las medidas físicas y su controlador realiza esa conversión.

Se conservan el ancho de 100 mm, el alto de 50 mm, las filas del producto y las
coordenadas de sus campos. La descripción del navegador mantiene su área de 7 mm;
en ZPL comienza en `(22,241)` y Serie en `(22,300)`.
Comprobar descripciones cortas y largas al aumentar la fuente: el espacio de texto
es limitado y debe respetar el área de Serie y los campos contiguos.

## Barras y centrado de bultos

- Contenido: rótulo físico, por ejemplo `L11` o `A01.1`.
- Simbología del navegador: CODE128B; ZPL utiliza CODE128 normal con subconjunto B.
- Módulo del navegador: 0,375 mm en 100 × 50 y 0,5 mm en 100 × 150.
- Margen blanco lateral del símbolo: diez módulos por lado.
- El SVG conserva su proporción y se centra dentro de la etiqueta. Su ancho no se
  estira para llenar el papel.
- El perfil ZPL limita el módulo a tres o cuatro puntos según el tamaño y calcula
  la posición horizontal a partir de la longitud del símbolo.

No añadir cantidades, UUID o textos de recepción dentro del contenido de barras:
el lector debe devolver el mismo rótulo que ve el operario.

## Flujo para futuras modificaciones

1. Modificar el diseño en una copia de desarrollo y conservar las posiciones que
   no forman parte del cambio.
2. Generar PDF y ZPL; comprobar códigos cortos, bultos grandes y subbultos.
3. Verificar dimensiones de página, centrado, márgenes blancos, texto completo y
   ausencia de superposición. Imprimir una prueba física y comprobar el lector.
4. Ejecutar las pruebas en el entorno de desarrollo:

   ```bash
   npm test
   .venv/bin/python -m pytest -q tests/test_etiquetas_visibilidad.py tests/test_etiquetas_bultos_finales.py tests/test_etiquetas_parciales_65.py
   ```

5. Cambiar el identificador de recursos en `scripts/versionar_frontend.mjs` y
   ejecutar `node scripts/versionar_frontend.mjs`. Confirmar y publicar el código probado.
6. Aplicar el commit con `scripts/actualizar_produccion.sh`, que conserva el respaldo
   y verifica el arranque. Recargar las pantallas con Ctrl+F5 y generar una solicitud nueva.

## Evidencia de esta revisión

`docs/muestras/impresion-20261110/Validacion-impresion.json` registra ocho casos de
bulto/subbulto en ambos tamaños, lecturas de los PDF a 203 y 300 dpi y comprobaciones
de posición de los campos del producto. Las pruebas se realizaron en un entorno
aislado; la impresión física debe confirmarse con el equipo de bodega.
