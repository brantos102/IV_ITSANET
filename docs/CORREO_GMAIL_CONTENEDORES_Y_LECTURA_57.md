# Correo, contenedores y lectura del packing list · versión 57

19/10/2026, Ecuador. Interfaz `20261019-57`.
Pase: `itsanet-20261019-correo-contenedores-57`.

## Envío del supervisor y respuesta al correo original

El envío directo de correos nuevos continúa utilizando MailApp desde la cuenta
que ejecuta el despliegue Apps Script del remitente elegido. La dirección escrita
en una ficha no concede autorización para enviar como esa persona. Cada cuenta
debe verificar su conexión y Google debe confirmar ese mismo remitente. La
opción de envío personal debe estar habilitada por ADMIN.

La versión 57 añade **Buscar correo original en mi Gmail** dentro del correo
editable de cada packing list/embarque. El supervisor busca por asunto, código,
remitente u otros criterios de Gmail, lee una vista de texto y selecciona el
mensaje original. El correo completo y sus adjuntos originales se abren en Gmail
con **Abrir correo completo en Gmail**. La aplicación devuelve hasta 15 resultados
por consulta; se puede acotar la búsqueda. La vista de texto se limita a 60.000
caracteres y no ejecuta HTML recibido por correo.

Después de seleccionar el mensaje, el borrador conserva su asunto con `Re:` y
su hilo. Se sugieren los destinatarios del remitente original cuando el borrador
no tiene destinatarios; el supervisor debe revisarlos. No se añade automáticamente
a todos los participantes del hilo. Los adjuntos de la respuesta son los informes
revisados de ese grupo, no los adjuntos del correo original.

El envío por Gmail API utiliza `threadId`, `In-Reply-To`, `References` y el asunto
original. Se comprueban la cuenta, el mensaje y el hilo antes del intento de
envío; se conserva el identificador confirmado de la nueva respuesta. No hay
conversión silenciosa a correo nuevo si falta esta capacidad. El acuse durable
existente se escribe antes de enviar: una confirmación interrumpida exige revisar
Enviados antes de repetir. El cierre y cada correo de un lote conservan sus
confirmaciones independientes.

**Preparar correo nuevo** desvincula explícitamente el hilo. Las entregas ya
confirmadas mantienen su contenido histórico y no se reescriben.

### Habilitación opcional en Google, una vez por cuenta

El supervisor usa la aplicación desde el navegador; no instala un servidor ni
introduce HMAC en cada dispositivo. La conexión Google pertenece a su cuenta y
la clave compartida se conserva cifrada en el servidor. No se solicita la
contraseña de Gmail.

Para habilitar la lectura y respuesta desde ITSANET:

1. Abrir Apps Script con la cuenta del supervisor. Conservar sus propiedades
   `SERVIDOR_HMAC`, carpeta Drive y el despliegue `/exec` existentes.
2. Actualizar **Proxy.gs** y **Servidor.gs** e incorporar **Gmail.gs** de esta
   versión. Conservar **Clientes.gs** y la configuración existente.
3. Mostrar `appsscript.json` en la configuración del editor. Para esta opción,
   copiar allí el contenido de `apps-script/proxy/appsscript-gmail.json`.
   **Es una plantilla del único manifiesto `appsscript.json`, no un segundo
   manifiesto para añadir al proyecto.** Añade solamente los scopes Gmail de
   lectura y envío a los permisos existentes; no solicita borrar ni administrar
   el buzón. Si el proyecto tiene otros permisos o dependencias propios, TI debe
   conservarlos y añadir ambos scopes.
4. En el proyecto Google Cloud asociado, comprobar que **Gmail API** esté
   habilitada. No se añaden Cloud Run, Cloud SQL ni facturación Firebase.
5. Ejecutar **verificarGmailServidor**, aceptar los permisos con esa cuenta y
   comprobar que devuelve su dirección. La comprobación no envía correo. Las
   políticas de Google Workspace pueden requerir autorización del administrador.
6. Publicar una **Nueva versión** del mismo despliegue, ejecutado como **Yo**.
   No cambiar su URL, carpeta ni clave por esta mejora.
7. En ITSANET → **Mi cuenta y correo**, verificar y guardar la conexión propia.
   Dejar la clave vacía conserva la existente. Después, elegir el mensaje
   original en el correo de cada grupo y revisar destinatarios y documentos.

Sin esta habilitación siguen disponibles los correos nuevos y la copia manual.
Para responder manualmente, abrir el correo original en Gmail, pulsar Responder,
pegar el contenido preparado y adjuntar los informes. Abrir Gmail o copiar el
contenido no registra por sí solo un envío.

## Lectura del archivo y contenedores recibidos

El lector identifica `Numerodepieza` y el contenedor del producto. Cuando una
tabla lateral repite FACTURA, DETALLE o BL, no reemplaza los campos de la tabla
de productos. **Embarque tiene prioridad sobre BL**; descripción y factura se
toman de sus columnas de producto. Se conserva el mapeo explícito cuando no es
ambiguo y se puede seleccionar la columna de contenedor en el formato de carga.

Un archivo con dos embarques no se importa dos veces. Sus filas conservan su
embarque y el cierre permite elegir correo por embarque, por packing list o
consolidado. Los SKU compartidos requieren revisar el reparto, como en la versión
56. No se decide la procedencia física de un conteo a partir de una coincidencia
de SKU.

En la vista previa aparece una selección de contenedores. Se seleccionan solo
los realmente recibidos; las cantidades y embarques se recalculan desde esas
filas, conservando su número original. El total del archivo completo sigue
visible como referencia y el panel indica por separado lo que se guardará.
Dejar todos seleccionados conserva la carga completa. No se dan por recibidos
automáticamente todos los contenedores de una distribución mensual.
Al seleccionar parte del archivo, las fórmulas de las filas seleccionadas se
exportan como valores de origen para evitar referencias a contenedores excluidos;
se conserva la expresión original como metadato de la línea.

### Revisar una recepción que ya existe

En la recepción → **Herramientas → Revisar embarques del Excel**, se compara la
identificación guardada con la columna Embarque de las filas originales. La
revisión es de lectura hasta pulsar **Corregir identificación logística** y
confirmar la comparación. Nunca reimportar el mismo packing list para corregir
sus metadatos: eso podría sumar cantidades.

La corrección comprueba SKU y cantidad de cada fila. Corrige únicamente embarque,
contenedor y factura verificables; mantiene cantidades, conteos, SKU, origen,
filas y documentos anteriores. Si hay una fila que no coincide con el origen,
una versión concurrente distinta o una entrega pendiente, la operación se
bloquea. La revisión registrada invalida la reutilización de informes anteriores.

Después de corregir, revisar agrupación/repartos de correos y **Fotos → Actualizar
carpetas por embarque** antes de generar documentos nuevos. Una asignación
fotográfica cuyo embarque ya no corresponde pasa a requerir revisión; no se
convierte en evidencia de otro embarque. No se borran fotos ni se reenvían
correos históricos. Esta revisión no recorta cantidades declaradas si la
recepción existente incluía más contenedores de los que llegaron: esa situación
requiere una conciliación operativa independiente.

## Distribución opcional por contenedor

En la recepción → **Herramientas → Contenedores y bultos**, o desde el correo
editable → **Distribución por contenedor**, añadir los contenedores recibidos:

- Número real, por ejemplo `ABCU1234567`.
- Rango de bultos, por ejemplo `E01` hasta `E60`: total calculado de 60 bultos.
- Posición final, por ejemplo `CALLEKL` o una ubicación de piso.
- Embarque o embarques correspondientes. Si el contenedor figura en las líneas
  de origen, la asignación debe coincidir con ellas.

La interfaz asigna C1, C2… según el orden. Permite hasta 50 contenedores, rechaza
duplicados y rangos superpuestos, y usa versión más bloqueo de la recepción para
evitar sobrescribir cambios ajenos. Guardar el mismo contenido de nuevo no añade
otra auditoría. La distribución no crea bultos físicos, no registra conteos y no
marca mercancía como recibida o validada.

Los correos incluyen una sección **Distribución y ubicación por contenedor**.
Los nuevos Excel incluyen **CONTENEDORES** cuando hay datos pertinentes. Cada
documento y correo de embarque incluye únicamente su distribución; el consolidado
incluye las distribuciones de las filas que agrupa. Se conserva el bloque
operativo anterior para compatibilidad con borradores existentes.

## Fotos y presentación

**Fotos de un SKU** muestra únicamente vínculos directos de ese producto,
incluida su clasificación histórica. No mezcla automáticamente panorámicas ni
fotos de otros SKU del bulto. El resumen guardadas/copiadas/pendientes tiene el
mismo alcance. **Ver fotos de la recepción completa** cambia el alcance por una
acción explícita. Las correcciones vigentes de vínculos tienen prioridad sobre
los enlaces antiguos de la bitácora.

Los nombres nuevos empiezan por propósito, cliente y recepción, seguidos del
grupo cuando aporta información y de la revisión: por ejemplo
`Validacion_CLIENTE_REC-EMB-A-19-10-2026_R0013.xlsx`. Ya no repiten código de
recepción, packing list y embarque cuando son iguales ni añaden otra fecha/hora
al final. Dos packing lists del mismo embarque conservan su diferenciación
`PL01`/`PL02`. Fecha/hora y autor completos permanecen en los metadatos del
informe. Los archivos anteriores no se renombran.

El encabezado distingue operación/perfil y concentra utilidades en
**Herramientas**, con descripciones al colocar el cursor. Conserva menú,
usuario, tema y avance; se comprobó a 390 píxeles de ancho.

## Arquitectura y almacenamiento

Se conserva Apache/HTTPS 8443 → FastAPI/systemd 3002 → MySQL, sin un servicio
nuevo ni cambios de tablas. La distribución utiliza una configuración pequeña
por recepción. El borrador guarda solo la referencia y cabeceras básicas del
mensaje elegido; no replica cuerpos, adjuntos ni bandejas Gmail en MySQL.
Las llamadas Gmail son explícitas y no se hacen al escanear productos.

Gmail API se invoca desde Apps Script mediante el token OAuth de la cuenta
ejecutora. El servidor firma peticiones con HMAC; el navegador no recibe esa
clave ni el token Google. Las consultas Gmail verifican la cuenta propia y su
unicidad; el operario no puede consultar buzones. Las imágenes siguen usando
el almacenamiento y cola Drive existentes, sin nuevos binarios en MySQL.

## Pase y validación empresarial

La publicación del repositorio y las pruebas aisladas no despliegan Apps Script
ni actualizan el servidor empresarial. En Linux `@apps`, usar el procedimiento
de pase existente con respaldo y comprobación de salud:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin desarrollo-local --tags && bash scripts/actualizar_produccion.sh "$PWD" "$(git rev-parse itsanet-20261019-correo-contenedores-57^{commit})"
```

Mantener el acceso `https://apps.flexnetuio.com:8443/app/`. Ejecutar el pase en
una ventana operativa: el script detiene brevemente solo la app, respalda y
comprueba su arranque. No copia bases de pruebas ni modifica Apache o TLS.
Después recargar las pantallas. Los nuevos permisos Gmail requieren además los
pasos de Google anteriores; instalar Python/HTML no autoriza un buzón.

Comprobar con el supervisor propietario: conexión y remitente, búsqueda/lectura,
selección de hilo, destinatarios y documentos. El primer envío real requiere
confirmación operativa del supervisor y comprobación de Enviados y de Entregas.
Las pruebas automatizadas y de navegador utilizan Google simulado y MySQL
aislado: no demuestran que una cuenta empresarial ya haya autorizado Google.

### Comprobaciones realizadas

- Suite general: 1.301 pruebas aprobadas, incluidas las suites del puente Google,
  navegador y servidor. La comprobación del nombre se actualizó al nuevo sufijo
  de revisión; los documentos históricos mantienen sus sufijos originales.
- Casos nuevos sobre MySQL aislado: 20 aprobados, incluida la protección frente
  a un snapshot antiguo que intenta sobrescribir el hilo elegido por otro
  supervisor.
- Comprobaciones adicionales de los flujos afectados: 45 aprobadas y cuatro
  omitidas por requerir condiciones específicas de MySQL o conexión externa.
- Chromium, 390 píxeles: edición de contenedores, rangos, galería y resumen por
  SKU, selección explícita de recepción completa, Gmail simulado, asunto del
  hilo y navegación sin desborde horizontal.
- Generador real de Excel con API/MySQL aislados: dos documentos por embarque,
  con sus filas y contenedores separados. No se enviaron correos, no se
  modificó Drive ni se probaron impresoras reales.
