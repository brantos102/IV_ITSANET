# Foto del operario y recuperación de la ficha · 50

Interfaz `20261019-50`. Etiqueta `itsanet-20261019-foto-operador-50`.

## Problema y corrección

Se reprodujo con rol OPERADOR el reseteo de la versión 49: un Escape recibido
desde el selector nativo ejecutaba el atajo general de limpiar la ficha antes de
recibir el archivo. Además, los campos y las fotos seleccionadas vivían en
memoria; una recarga o recuperación de la pestaña podía perderlos.

En móviles, **Tomar foto** abre ahora la cámara dentro de la misma página. La
captura no inicia un escaneo ni suma unidades. Se detiene el lector anterior y
las pistas de la cámara se apagan al cerrar u ocultar el visor. Se mantiene una
alternativa explícita para usar la cámara nativa del dispositivo.

El selector de archivos protege la ficha frente a Escape. Los campos se anotan
antes de abrirlo y las fotos recibidas se respaldan en IndexedDB. El borrador
incluye cantidad, pallet, estado físico, incidencia, observación, packing list y
la clave del intento de envío. Se separa por cuenta, recepción y pestaña.

Al recargar, se consulta el producto y el estado actual de la recepción antes de
recuperar la ficha. No se registra ni envía nada automáticamente. Si la recepción
ya está cerrada, se conserva el borrador y se solicita revisión del supervisor.
El borrador se descarta tras una confirmación de guardado o una decisión explícita
del operario. Cerrar una consulta sin cambios no exige una confirmación adicional.

También se conserva el packing list seleccionado cuando otro operario actualiza
el mismo SKU. La selección no se arrastra al consultar un producto distinto.
**No apareció** envía las fotos elegidas y el packing list del registro; antes
podía omitir las imágenes o fallar en una recepción con varios embarques.

## Uso del operario

1. Abrir el producto e ingresar la cantidad, pallet y novedades que correspondan.
2. Abrir **Fotos para este conteo** y pulsar **Tomar foto**.
3. Enfocar y pulsar **Usar esta foto**. Verificar la miniatura; permite ampliar y
   quitar la foto seleccionada. Cancelar la cámara conserva la ficha.
4. Pulsar **Guardar conteo** para registrar unidades y evidencias, o **Guardar solo
   fotos · sin unidades** para confirmar únicamente las imágenes.
5. Comprobar el mensaje de éxito y consultar **Ver fotos guardadas** si hace falta.

“Respaldada localmente” significa que la imagen sigue pendiente de confirmación
en el servidor. Una recarga recupera el borrador para revisarlo y continuar;
no equivale a un conteo guardado. Si una respuesta se pierde después de guardar,
el reintento conserva la clave original y el servidor devuelve el mismo conteo
sin volver a sumar unidades. Las fotos confirmadas conservan sus URLs al recuperar
el borrador y no se vuelven a subir por ese reintento.

La recuperación depende de conservar la misma cuenta, pestaña, navegador,
dispositivo y dirección del sitio. Cambiar de origen HTTPS o borrar los datos
del navegador impide acceder a esa copia. No sustituye un respaldo del servidor.
Si el almacenamiento falla, la app avisa y conserva lo disponible en memoria;
hay que guardar antes de salir. Si falta una foto al recuperar, se informa para
volver a adjuntarla. No se puede recuperar una imagen que la cámara externa nunca
devolvió al navegador. La cámara en la página evita esa salida por defecto.

## Datos y conexiones

No hay nuevas tablas, columnas ni dependencias. El borrador se guarda en el
navegador, no en MySQL. Las imágenes confirmadas siguen usando el almacenamiento
y la cola de Drive existentes, con sus controles de identidad y clasificación.
No cambia Google/HMAC, roles, Apache, TLS ni los puertos 3002/8443. Esta versión
no copia datos o claves entre pruebas y producción.

## Actualizar la PC de pruebas

En **PowerShell de Windows**, desde el repositorio de la PC anfitriona:

```powershell
git pull --ff-only origin desarrollo-local; if ($LASTEXITCODE -eq 0) { .\scripts\publicar_pruebas.ps1 -Accion preparar }
```

Actualiza la app y conserva los volúmenes, cuentas y configuración del piloto.
`preparar` retorna antes de iniciar/reiniciar el túnel; si continúa activo, se
conserva su proceso y enlace. La URL temporal sigue dependiendo de Cloudflare y
de que la PC, Docker y el túnel permanezcan encendidos.

Después, cerrar y volver a abrir la pestaña del móvil y actualizar la página.
En **Información del escáner** debe aparecer `20261019-50`.
Comprobar captura, cancelación, miniatura y guardado con una recepción de prueba.

## Pase empresarial

Publicar en GitHub no instala el cambio en el servidor. Aplicar cuando los
operarios hayan guardado sus fichas: el procedimiento existente realiza respaldo
privado, pausa brevemente solo iv-itsanet y verifica el arranque. No ejecutar
pruebas sintéticas sobre las recepciones reales.

En **Linux @apps**, una sola línea:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin --tags && revision_itsanet="$(git rev-parse 'itsanet-20261019-foto-operador-50^{commit}')" && git show "$revision_itsanet:scripts/actualizar_produccion.sh" > /tmp/itsanet-pase50.sh && bash /tmp/itsanet-pase50.sh "$PWD" "$revision_itsanet"
```

Recargar después y comprobar sesión, recepción existente, conteos y vista de
fotos. No se requiere reinstalar la app ni configurar HMAC para los operarios.

## Validación

- Runner general: 1.182 pruebas aprobadas (690 Python y 492 JavaScript).
- Compilación frontend y 62 comprobaciones de páginas/imports aprobadas; 139
  pruebas del módulo de aplicación aprobadas tras el ajuste final.
- Chromium con cámara simulada, viewport móvil y MySQL propios: reproducción del
  fallo 49 con rol OPERADOR; captura dentro de la página y retorno del selector
  con Escape; recuperación de dos fotos y campos tras recargar; aislamiento por
  cuenta/recepción; otro operario actualizando sin cambiar el packing elegido.
- Interrupción de respuesta después de confirmar un conteo real en la instancia
  aislada: al reintentar, las unidades y las dos imágenes permanecen únicas.
- Declarar **No apareció** conserva la evidencia como FALTANTE, sin sumar unidades.
- Cancelar cámara y galería conserva los campos; quitar una foto no la restaura
  al recargar; descartar exige confirmación si hay cambios. La simulación de cuota
  agotada informa del fallo y de la foto no recuperada, conservando los campos.

Las pruebas no se conectan al servidor empresarial, no envían correo y no usan
carpetas operativas de Google. El teléfono físico del usuario requiere repetir
el flujo después del pase; la simulación no certifica todos los comportamientos
de Android/iOS o la recuperación tras una terminación del sistema operativo.
