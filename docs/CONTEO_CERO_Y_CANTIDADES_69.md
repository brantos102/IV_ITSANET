# Versión 69 · cero y cantidades escritas

## Registrar 0 desde el flujo normal

La cantidad admite cero desde **Guardar conteo**. Se retiraron el botón oculto
antiguo y la validación que remitía al usuario a ese botón inexistente.

1. Escanear o consultar el SKU y escribir `0` en cantidad.
2. Indicar una observación sobre la verificación física. Cuando el SKU pertenece
   a varias listas, seleccionar el packing list concreto; no repartir cero.
3. Pulsar **Guardar conteo** y confirmar **Guardar cantidad 0**.

Se conserva el mecanismo existente de declaración de cero: evento CERO, usuario,
observación, lista, fecha, evidencia e identificador para evitar duplicados ante
un reintento. No suma ni resta unidades, no reemplaza un total anterior y no
requiere pallet ni posición física. El total y la calidad PNC previos permanecen.
Un campo vacío, negativo o inválido no se interpreta como una declaración.

Con cero no se clasifica PNC: una incidencia de producto necesita unidades
físicas. Si se eligió PNC, corregir la cantidad o volver al estado sin incidencia.
Cancelar la confirmación conserva la ficha y sus datos sin registrar un evento.
El cero digitado antes de escanear se conserva al abrir la ficha.

La confirmación de guardado indica el cero y el total acumulado. No ofrece
etiquetas de unidades ni asignación de posición a un registro de cero.

## Historial y corrección

El historial de la ficha incluye los eventos CERO. Los supervisores autorizados
pueden corregirlos desde el flujo de corrección existente: queda el original,
su anulación y el conteo sustituto, con motivo y controles de concurrencia.
Anular la única declaración de cero devuelve el SKU a pendiente. Si existen
otros conteos o declaraciones vigentes, conserva esa validación y sus cantidades.
No hay limpieza ni modificación retroactiva de los eventos existentes.

## Evitar cambios por desplazamiento

Los campos numéricos mantienen su validación HTML y teclado decimal, pero
ocultan las flechas nativas de incremento/decremento en Chrome/Edge y Firefox.
La aplicación bloquea rueda del mouse sobre un campo numérico enfocado y teclas
arriba/abajo. Se conserva la escritura, pegado y navegación con Tab/Enter.
El control se aplica también a los campos de modales creados dinámicamente.
El desplazamiento fuera del campo sigue funcionando.

## Actualización

Usar `scripts/actualizar_produccion.sh` con el commit completo de la entrega,
coordinando la pausa de registros para el respaldo. Recargar PC y handheld
después para cargar `20261024-69`.

No requiere migraciones destructivas, reimportar datos ni cambiar las conexiones
Google, MySQL o Apache. Se mantienen las mejoras de informes de v68.

Validación reproducible:

```bash
.venv/bin/python -m pytest -q tests/test_conteo_cero_69.py tests/test_app_modelo.py
node firebase/test/app.test.mjs
node firebase/test/paginas.test.mjs
PATH="$PWD/.venv/bin:$PATH" node pruebas.js
```

Las pruebas usan bases aisladas; nunca ejecutar pruebas con una base productiva
como VAL_TEST_DATABASE_URL. La prueba de navegador usa cuentas y datos sintéticos,
sin enviar correos reales ni conectar las cuentas Google de producción.
