# Versión 59 · Enlaces claros de evidencias en el correo

19 de octubre de 2026 · Ecuador.

El correo enumeraba carpetas de cada SKU con el mismo texto «Consultar carpeta de
evidencias». Aunque apuntaban a ubicaciones distintas, la presentación impedía
identificar su destino. Se elimina esa enumeración del correo.

El bloque **Evidencias en Drive** muestra:

- Una carpeta principal: **Carpeta del embarque RB63196**, cuando se confirma su
  carpeta específica; en otro caso, **Carpeta de la recepción [código]**, identificada
  como tal. No se inventan URLs a partir del nombre del embarque.
- **Sobrantes y adicionales**, **Faltantes** y **PNC**, solo cuando esas carpetas
  existen y sus enlaces están confirmados dentro del ámbito del correo.

Un correo individual de embarque tiene como máximo cuatro accesos en ese bloque.
Si un packing list contiene varios embarques, o el supervisor elige consolidar,
las categorías se identifican con el nombre de su embarque. Una lista parcial no
incluye categorías globales que puedan mezclar otras listas. Los enlaces por SKU
se mantienen en Excel y los enlaces individuales de las fotografías conservan
su función; no se incluyen como una lista repetida de carpetas en el encabezado.

## Actualizar carpetas antiguas sin mover fotos

En **Preparar correo de recepción**, pulsar **Actualizar enlaces de Drive**.
Se consulta una sola vez el árbol conocido de la recepción, en una petición
firmada al puente del responsable. Se reutilizan los prefijos al buscar carpetas.
No crea carpetas, mueve originales, sube imágenes ni envía correo. Si aún no hay
carpeta principal confirmada, usar primero **Verificar carpeta de recepción**,
la acción existente que prepara esa carpeta y programa las fotos pendientes.

Una carpeta inexistente no aparece en el correo. No se crean categorías vacías
para completar la presentación. Las consultas repetidas durante 30 segundos
reutilizan el índice; fuera de ese intervalo requieren otra pulsación explícita.
Abrir o renderizar un correo no realiza llamadas a Google.

El índice ocupa una única fila `app_config` por recepción, con un máximo de 512
rutas. Se actualiza esa misma fila; no se almacena contenido multimedia ni se
crean filas por fotografía, SKU o pulsación. Los registros de conteo y entrega no
se modifican. Se rechazan carpetas fuera de las rutas solicitadas, respuestas
con otra raíz y URLs que no correspondan a carpetas Drive.

## Aplicación

1. Aplicar el commit probado de la versión 59 mediante el pase de producción
   con respaldo existente; conserva la dirección HTTPS actual.
2. Actualizar **Servidor.gs** de `apps-script/proxy/Servidor.gs` en el Apps Script
   del responsable Drive. Publicar **Nueva versión** del mismo despliegue `/exec`.
   Conservar HMAC, URL, manifiesto y archivos Gmail/Proxy actuales. Esta mejora
   utiliza los permisos Drive existentes; no agrega permisos Gmail.
3. Recargar ITSANET con **Ctrl+F5** y abrir el correo correspondiente al packing
   list o embarque. Pulsar **Actualizar enlaces de Drive**, revisar el bloque y
   guardar el borrador antes de copiar, descargar o enviar.

Hasta actualizar el puente y comprobar los enlaces, los datos antiguos muestran
únicamente la carpeta principal confirmada. Los correos ya enviados o declarados
como enviados conservan su contenido histórico; para un nuevo envío se revisa un
borrador actual, sin alterar ni reenviar automáticamente el correo anterior.

## Comprobaciones

Pruebas con Google simulado: resolución de padres y categorías sin crear ni mover,
operación firmada, permisos de supervisor y bloqueo de operarios, separación por
embarque, packing list con varios embarques, rechazo de rutas ajenas, caché sin
crecimiento por consulta y conservación de enlaces por SKU en Excel. Se validó
la vista de supervisor en Chromium a 390 px: cuatro accesos, actualización,
guardado y contenido HTML/texto. Las pruebas no acceden al Drive empresarial ni
envían correos reales.
