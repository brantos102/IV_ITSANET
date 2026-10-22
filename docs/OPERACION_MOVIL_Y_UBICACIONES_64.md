# Versión 64 · cámara móvil, detalle por conteo y coordinación

## Correcciones

La vista previa de cámara podía ocupar el alto disponible en handheld y dejar los botones fuera de la pantalla. La vista ahora reparte el espacio entre encabezado, video y controles, conserva las acciones accesibles y se adapta a cambios de orientación y del área visible. Incluye respaldo con medidas `vh` y píxeles para navegadores que no reconocen `dvh`. Capturar añade la imagen a la ficha; guardar la ficha o las evidencias sigue siendo necesario. Cancelar conserva la ficha y apaga la cámara.

El informe operativo copiaba los pallets, posiciones y observaciones agregados del SKU a cada línea repetida. Ahora asigna los conteos activos a las filas de su mismo SKU y packing list, respetando sus cantidades físicas. Anulaciones y correcciones de calidad se aplican antes de distribuir. Una fila con un único destino muestra ese destino; una fila que abarca varios destinos indica sus unidades respectivas. Las notas corresponden a los conteos asignados a esa fila.

Se conserva la estructura del packing list. La hoja nueva **UBICACIONES** identifica cada parte por condición física, unidades, pallet, posición final sugerida, observación y conteo. **FILA DEL INFORME** permite saltar a la fila correspondiente del packing validado. **FILA ORIGINAL** se informa cuando fue registrada; no se inventa una referencia de origen ausente. Los enlaces Drive confirmados siguen disponibles.

Ejemplo: un conteo de seis unidades en A01/BM-A-10-1, con dos PNC, y otro de cuatro conformes en A02/BM-B-20-2 generan tres partes: 2 PNC + 4 conformes + 4 conformes. Total físico: 10; PNC: 2; conformes: 8. Si el packing tiene dos filas de 6 y 4, cada una recibe su pallet y posición; si tiene una fila de 10, muestra las cantidades de ambos destinos. El correo de novedades incorpora ese desglose para el ejecutivo de cuenta.

**Límite de la asignación:** cuando el conteo no identificó una factura o línea física, la distribución entre filas repetidas es secuencial dentro del packing list. No acredita una factura física que no se registró. Un conteo antiguo que agrupa pallets o que no puede vincularse a una lista se señala para revisión; no se deducen cantidades por pallet ausentes del registro. Para obtener distribución exacta, registrar por separado las unidades de cada pallet/posición.

## Trabajo simultáneo

Al abrir la ficha de un SKU se publica una presencia temporal, vinculada al usuario y dispositivo de la sesión. El aviso muestra el nombre y actividad de otra persona en el mismo SKU de la misma recepción. Cambiar de SKU actualiza la presencia; abandonar la página intenta liberarla. La consulta se renueva cada 15 segundos y caduca a los 90 segundos si no se renueva. Si no hay conexión, se indica que no fue posible consultar al equipo.

Es una alerta de coordinación: permite a dos personas trabajar con pallets distintos del mismo SKU. No es un bloqueo exclusivo ni puede determinar si las unidades físicas son las mismas. Se mantienen las claves de idempotencia y las transacciones de conteo existentes. La presencia temporal utiliza la tabla de configuración existente, sin modificar conteos ni añadir una migración de esquema.

## Aplicación y revisión

Actualizar con `scripts/actualizar_produccion.sh` fijado al commit de esta entrega. El actualizador comprueba el repositorio y servicio, prepara dependencias y realiza respaldo privado de MySQL, archivos, configuración y código previo antes de cambiar el servicio. Si detecta cambios locales que no puede conservar con seguridad, se detiene. No usar `git reset --hard` para eludir esa comprobación.

La versión común del frontend es **20261022-64**, incluyendo imports y service worker. Tras actualizar, recargar los dispositivos. No requiere volver a desplegar Apps Script ni reconectar una cuenta Google que ya esté autorizada.

Los informes históricos se conservan. En el correo o las descargas, usar **Preparar y descargar documentos** para generar una revisión con el nuevo detalle; la versión de formato impide reutilizar como vigente un documento preparado con el formato anterior.

Comprobar antes de cerrar la revisión operativa:

1. En el handheld real, abrir fotografía, girar el dispositivo, capturar y guardar en la ficha. Confirmar posteriormente la copia en Drive. La prueba de pantalla no sustituye el permiso de cámara y un acceso HTTPS válido en ese equipo.
2. Abrir el mismo SKU desde dos usuarios: verificar el aviso con nombre y coordinar pallets; cambiar uno a otro SKU y verificar que el aviso se retire.
3. Preparar un informe nuevo y revisar PALLET, O/observación y Q/posición según las columnas configuradas. Verificar en UBICACIONES que la suma de las partes coincide con la cantidad física, sin sumar PNC otra vez como unidades adicionales.
4. Revisar novedades, miniaturas, enlaces y adjuntos antes de enviar al ejecutivo. Las pruebas de esta entrega no envían mensajes reales.

## Presentación

`firebase/public/presentaciones/itsanet-operacion.html` contiene seis diapositivas, navegación por teclado, ejemplos interactivos e impresión. Es autónoma y puede copiarse a un hosting estático o abrirse en un navegador. Bajo el servidor actual se publica en `/app/presentaciones/itsanet-operacion.html`. Los datos son ilustrativos y no se atribuyen mediciones de rendimiento que no se hayan realizado.
