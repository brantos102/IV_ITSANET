# Correo revisable, escáner móvil y ayudas operativas · 49

Edición del 18/10/2026 (Ecuador). Interfaz y lector `20261018-49`.
Etiqueta: `itsanet-20261018-correo-camara-49`.

[Descargar ejemplo visual del correo (HTML sin conexión, datos ficticios)](https://github.com/brantos102/IV_ITSANET/raw/refs/tags/itsanet-20261018-correo-camara-49/docs/descargas/ITSANET-vista-correo-49.zip).

## Correo de recepción

La revisión se organiza en redacción, selección de imágenes, vista previa y
archivos finales. Se pueden editar asunto, destinatarios, saludo, presentación,
notas, despedida y firma. Las cantidades y tablas se reconstruyen con los
registros reales; no se permite sustituirlas mediante HTML escrito por el cliente.

Por defecto se oculta el resumen total de unidades y se proponen fotografías de
las novedades actuales. No se muestra un inventario de todas las imágenes ni su
cantidad dentro del mensaje. Una foto histórica de FALTANTE no se propone como
PNC al encontrarse el producto: conserva su clasificación.

Opciones de fotografías:

- **Solo novedades actuales:** relacionadas con faltantes, sobrantes o PNC vigentes.
- **Elegir fotografías:** marcar o desmarcar imágenes guardadas en esa recepción.
- **Primeras fotos de la recepción:** conserva una alternativa al orden cronológico.
- **Correo sin fotografías:** mantiene tablas, redacción, documentos y vínculos.

El correo admite hasta 12 imágenes, conforme al puente Google existente. La
selección está limitada y validada en el servidor; no acepta IDs de otra
recepción ni enlaces arbitrarios. Las demás evidencias permanecen en sus carpetas.
Quitar una foto del mensaje no elimina su archivo ni modifica su clasificación.

**Registrar una foto nueva** abre el registro de evidencias de la recepción
abierta. Al volver se actualiza la selección. En recepciones cerradas se elige
entre evidencias existentes; se conserva la política actual de incorporación
posterior al cierre. **Mostrar resumen total de unidades** es opcional.

El nuevo formato utiliza encabezado, cliente y recepción visibles, colores por
novedad, tablas con filas alternadas, fotos junto a su sección y documentos finales
separados. La vista previa usa imágenes autenticadas de ITSANET; el correo conserva
los enlaces Drive y el puente puede incrustar las miniaturas autorizadas. En la
copia manual, Gmail/Outlook y los destinatarios siguen necesitando los permisos de
Drive; los documentos se adjuntan manualmente. Una imagen pendiente de Drive se
identifica como tal, sin fingir que ya esté disponible para el destinatario.

Se conserva la versión del borrador para rechazar cambios simultáneos. Un correo
confirmado o en proceso mantiene su HTML congelado. La opción de imágenes y su
lista de IDs se congelan junto al mensaje; el envío automático y la copia manual
parten de la misma redacción guardada. Se mantiene la revisión de Enviados ante
una confirmación incierta; esta actualización no reenvía entregas antiguas.

## Escaneo móvil

El video ocupa el visor sin franjas laterales; el recorte del lector corresponde
al área visible aunque la cámara entregue video vertical. Se alterna el marco
central con el área completa visible. El lector conserva cada carácter y la
consulta sigue validando el resultado contra catálogo/recepción.

**Leer ahora** intenta el fotograma actual, sin esperar un nuevo intervalo. Si el
lector nativo no encuentra el código, usa el respaldo ZXing local. El intento
reforzado procesa etiquetas giradas. Los fotogramas nunca se decodifican en
paralelo y se mantienen pausa, supresión de duplicados y apagado de pistas.
Encontrar varios códigos exige encuadrar uno; no se toma silenciosamente el primero.

Zoom y linterna aparecen únicamente si el dispositivo informa que los admite.
La cámara trasera y enfoque continuo se solicitan cuando están disponibles. No se
abren permisos ni dispositivos adicionales sin intervención del usuario. Al abrir
el visor se oculta el teclado y se desplaza a la cámara; al volver de una ficha
con la cámara activa se enfoca Leer ahora, evitando abrir el teclado otra vez.
La lectura consulta; no registra unidades ni guarda una foto como evidencia.

**Información del escáner** muestra versión, motor, resolución y fps disponibles.
El diagnóstico de cámara del mismo sitio incorpora versión, contexto seguro,
API y ajustes reales, sin incluir contraseñas o identificadores de dispositivo.

## Comparar el teléfono con pruebas y producción

Se usa el mismo módulo de cámara cuando ambos entornos tienen la misma versión.
La última captura empresarial aportada confirmó la versión 46; no se puede
asegurar que la PC o el servidor estén en 49 sin comprobarlos después del pase.
Esta nube no tiene acceso directo al teléfono ni a la PC anfitriona del usuario.

1. Actualizar primero la instancia de pruebas usada por el teléfono.
2. Recargar sus pantallas; si conserva recursos antiguos, cerrar y volver a abrir
   la pestaña y actualizar la página.
3. Abrir la cámara → Información del escáner. Debe mostrar `20261018-49`.
4. Probar una etiqueta horizontal, otra girada y un código con ceros iniciales.
   Comprobar consulta automática y Leer ahora, sin guardar conteos de prueba reales.
5. Anotar motor, resolución, fps y disponibilidad de zoom/linterna. Variaciones
   entre teléfonos son capacidades del dispositivo, no necesariamente diferencias
   de configuración del servidor. El acceso móvil necesita HTTPS confiable.
6. Tras el pase empresarial, repetir esa comprobación en
   `https://apps.flexnetuio.com:8443/app/`.

Las pruebas con video sintético no certifican la velocidad física en todos los
móviles, iluminación, distancias ni Safari real. La comprobación de campo sigue
siendo necesaria.

## Fotos, nombres y ayudas

- **Ver fotos guardadas:** consultar evidencias ya registradas; permite gestionar
  imágenes independientemente de un conteo.
- **Fotos para este conteo · opcional:** seleccionar fotos nuevas que se guardarán
  con las unidades o mediante **Guardar solo fotos · sin unidades**.
- **Tomar foto / Elegir de la galería:** captura nueva frente a archivos existentes.
- En ingreso de bultos, **Capturar del visor** usa la cámara abierta y
  **Cámara del teléfono** abre la aplicación del equipo. Son dos formas de tomar
  una foto, con una explicación visible; Galería elige archivos existentes.
- **Consulta previa** sustituye la expresión Cacería. El menú muestra
  **Indicadores** en lugar de KPIs.

Las acciones habituales incluyen comentarios al mantener el cursor sobre ellas.
Se conservan las ayudas específicas existentes y se añaden a controles dinámicos.
Los textos de contexto siguen visibles en móvil, donde no existe cursor. El
observador procesa controles nuevos o cambiados; no recorre la página completa
cada vez que se actualiza el reloj.

## Datos y conexiones

No hay tablas, columnas, credenciales o dependencias nuevas. Las opciones e IDs
se guardan en el borrador de la recepción y su auditoría. Las imágenes siguen
fuera de MySQL. Se conserva Google/HMAC, permisos, clasificación histórica,
deduplicación y reintentos protegidos de fotos. No cambia Apache ni el puerto
empresarial 3002 o su entrada HTTPS 8443.

## Actualizar las pruebas de la PC conservando el túnel activo

Ejecutar **en PowerShell de Windows**, desde el repositorio de la PC anfitriona:

```powershell
git pull --ff-only origin desarrollo-local; if ($LASTEXITCODE -eq 0) { .\scripts\publicar_pruebas.ps1 -Accion preparar }
```

`-Accion preparar` actualiza la aplicación de pruebas y conserva volúmenes y
claves; retorna antes de iniciar o reiniciar el contenedor del túnel. Si el túnel
ya está activo se mantiene su proceso y enlace. El mensaje sobre no abrir un
enlace se refiere a que esta acción no crea uno nuevo. No ejecutar `iniciar` para
este paso si se quiere evitar un reinicio del túnel. Esta acción no garantiza
permanencia de una URL temporal ni recupera un túnel que ya estuviera detenido.
Si el móvil usa otro proyecto local, comprobar su dirección y actualizar ese
proyecto: no basta con actualizar una instancia diferente.

## Pase empresarial

Esta publicación en GitHub no actualiza automáticamente el servidor. El pase
usa la rutina existente: descarga dependencias antes, pausa solo iv-itsanet,
respalda base/archivos/configuración privada, aplica el commit probado y verifica
salud y página. Preparar una pausa operativa. No ejecutar pruebas sobre producción.

En la terminal **Linux @apps**, una sola línea:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin --tags && revision_itsanet="$(git rev-parse 'itsanet-20261018-correo-camara-49^{commit}')" && git show "$revision_itsanet:scripts/actualizar_produccion.sh" > /tmp/itsanet-pase49.sh && bash /tmp/itsanet-pase49.sh "$PWD" "$revision_itsanet"
```

Después recargar, comprobar la versión del lector, sesión, una recepción existente,
conteos, fotos y el borrador. La verificación de una conexión Google no envía correo.
No reintentar entregas históricas sin revisar antes Enviados.

## Evidencia de validación

- Runner general: 1.179 pruebas aprobadas (690 Python y 489 JavaScript).
- MySQL desechable: 46 pruebas de fotos, correo y concurrencia; otra prueba real
  con dos supervisores confirma que uno guarda y el otro recibe conflicto 409.
- Tras los ajustes finales: 31 pruebas focales Python aprobadas y una condición
  MySQL omitida en SQLite; esa condición se ejecutó y aprobó en MySQL.
- Navegador Chromium y MySQL propios: editar redacción, marcar/quitar imágenes,
  ocultar fotos/totales, abrir registro de fotos y volver, miniaturas autenticadas,
  móvil de 390 px sin desbordamiento, consulta manual y apagado sin nuevos conteos.
- ZXing real con video sintético vertical: códigos horizontales, girados y con
  ceros iniciales; respaldo manual cuando el detector nativo no reconoce.
- Compilación del frontend y coherencia del grafo de imports/cache verificadas.

Las conexiones Google del usuario, el teléfono físico y la ejecución del pase
empresarial no se sustituyen por estas pruebas aisladas. No se enviaron correos
ni se accedió a carpetas operativas durante la validación.
