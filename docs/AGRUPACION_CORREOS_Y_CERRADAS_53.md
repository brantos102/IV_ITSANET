# Correos por packing list o embarque y revisión de recepciones cerradas

19/10/2026, Ecuador. Interfaz `20261019-53`.
Publicación: `itsanet-20261019-agrupacion-correos-53`.

## Qué cambia

El supervisor elige al comenzar la finalización:

| Elección | Resultado |
|---|---|
| Un correo por packing list | Cada archivo de origen tiene su correo y su Excel. |
| Un correo por embarque | Las filas se agrupan por su campo Embarque. Un archivo con dos embarques produce dos correos. Un mismo embarque presente en dos archivos produce un correo con ambos documentos correspondientes. |

Se cierra una sola recepción completa, después de revisar los correos de todos
los grupos. Cada correo permite revisar destinatarios, redacción, novedades,
fotos y documentos propios. La preparación no inicia descargas automáticas.

La consulta del servidor empresarial confirmó `40ba756` (versión 51). La versión
52 publicada en GitHub todavía no estaba instalada. Este pase incorpora ambas
mejoras; no hace falta instalar primero la 52.

## Recepción cerrada ISZ-RAISZ04520-16-10-2026

El correo histórico se conserva tal como fue preparado. Una actualización no
puede convertirlo en dos mensajes ya enviados ni modificar su historial.

Después del pase y de recargar con **Ctrl+F5**:

1. Abre la recepción y **Informes → Correo final editable**.
2. Elige la revisión actual en lugar del correo original archivado.
3. En **Elegir: por packing list o por embarque**, selecciona **Un correo por
   cada packing list**. Deben aparecer **PRINCIPAL** y **RAISZ04520**, según los
   archivos efectivamente registrados en esa recepción.
4. Selecciona **Preparar documentos de esta revisión** y revisa cada tarjeta.
   Puedes editar, copiar o descargar cada borrador con su documento.
5. **Ver el correo original archivado** permite consultar el mensaje anterior.

Esta revisión no reabre la recepción, no cambia sus conteos, no reemplaza la
entrega original ni programa un reenvío. Los nuevos borradores de una recepción
histórica se preparan para revisión y copia manual; no representan un nuevo
acuse de entrega.

## Archivo con varios embarques

Se utiliza el campo Embarque de cada fila importada. El nombre del archivo o
del packing list no se interpreta como prueba de que todas sus filas pertenecen
a un único embarque.

- Si faltan embarques en algunas filas, el supervisor debe asignarlos. Puede
  aplicar el mismo código a las filas sin dato de un archivo. La asignación se
  guarda para el informe y conserva intacta la fila de origen.
- Si un SKU aparece en varios embarques dentro del mismo packing list, se
  muestra una propuesta de distribución. El supervisor revisa y confirma sus
  cantidades físicas, incidencias, unidades PNC, pallets y observaciones.
- Las sumas deben conservar el conteo y la calidad registrados. El reparto
  sirve para presentar los informes; no añade ni modifica eventos de conteo.
- Si otro usuario cambia los datos después de la revisión, se exige actualizar
  el plan o el informe correspondiente. Un cambio de cantidad o calidad que
  invalide el reparto bloquea su uso hasta revisarlo.
- Los adicionales se asignan explícitamente a un grupo. Las fotografías de un
  SKU compartido que no identifican su embarque requieren selección expresa;
  se conservan en Drive y no se atribuyen automáticamente a una novedad.

Al dividir un archivo en varios embarques, sus fórmulas de origen se presentan
como los valores importados. Así se evita que apunten a filas de otro embarque.
El packing list almacenado conserva sus fórmulas originales. La exportación por
packing list mantiene el comportamiento previo.

## Descarga y entrega

**Informes → Descargar informe** permite obtener el resultado actualizado con
la recepción abierta o cerrada. Los documentos vigentes se reutilizan si sus
datos y presentación coinciden. Un cambio real genera otra versión numerada.
Puedes descargar todos en un ZIP temporal o seleccionar un grupo. El ZIP no se
almacena como otro informe en la base de datos.

En un cierre nuevo se revisa cada correo antes de la confirmación final. Se
conserva el estado individual de los mensajes; los confirmados se omiten en
reintentos. Ante un acuse incierto de Google, se debe revisar Enviados antes de
solicitar otra entrega.

## Almacenamiento y compatibilidad

No hay nuevas tablas, dependencias, claves HMAC ni cambios de Apache/TLS. El
plan usa la configuración ya existente por recepción. Se conserva una sola
entrega con su instantánea comprimida por cierre, estados por correo y
referencias a los archivos. No se duplican fotografías binarias en MySQL.
La primera generación con los nuevos metadatos puede crear una versión nueva;
las siguientes reutilizan el documento vigente cuando corresponde.

## Pase a producción

Mantener el acceso **https://apps.flexnetuio.com:8443/app/**. Ejecutar esta
**única línea en Linux @apps**, coordinando una pausa de registros. El
procedimiento existente obtiene respaldo privado de base, archivos y entorno,
actualiza únicamente el servicio `iv-itsanet` y verifica salud e interfaz. Si
falla el arranque, intenta volver al código anterior sin reemplazar la base.

```bash
cd ~/bryan/IV_ITSANET && git fetch origin --tags && revision_itsanet="$(git rev-parse 'itsanet-20261019-agrupacion-correos-53^{commit}')" && git show "$revision_itsanet:scripts/actualizar_produccion.sh" > /tmp/itsanet-pase53.sh && bash /tmp/itsanet-pase53.sh "$PWD" "$revision_itsanet"
```

La salida debe confirmar **Código instalado**, **Respaldo privado** y salud de
servicio e interfaz. Después recargar con Ctrl+F5 y comprobar acceso, recepción,
conteos y los correos de cada grupo. No se importan usuarios, recepciones,
credenciales ni volúmenes del entorno de pruebas. Publicar el código en GitHub
no ejecuta este pase en el servidor empresarial.

## Verificación

- Suite general: 1.225 pruebas correctas.
- MySQL aislado: 19 pruebas correctas de agrupación, recepción cerrada, envío
  separado y concurrencia de cierre; no se envió correo real.
- Pasada final de agrupación: 5 pruebas correctas, incluyendo bloqueo de un
  reparto que quedó desactualizado por cambios de cantidad o calidad.
- Chromium con MySQL aislado: recepción histórica simulada con PRINCIPAL y
  RAISZ04520, dos correos y dos documentos sin alterar su entrega original;
  vista móvil de 390 px sin desbordamiento.
- Chromium: un archivo con dos embarques y un SKU compartido; reparto 4+4
  unidades y 1+1 PNC, revisión de dos correos, una sola recepción cerrada y
  ausencia de descargas automáticas.
- Comprobación adicional del Excel por embarque: cantidades, calidad,
  observaciones y valores de origen separados; 29 pruebas de gestión correctas.

Los datos de estas comprobaciones son simulados. El contenido real de la
recepción empresarial se comprueba después del pase, desde su interfaz.
