# Supervisión, correo e informes por packing list

Entrega `itsanet-20261017-supervision-informes`, frontend `20261017-36`.
Conserva las recepciones, usuarios, archivos, secretos cifrados y conteos existentes.
No importar la base ni la recepción de pruebas en producción.

## Activar el envío desde cada supervisor

La cuenta que solicita el nuevo envío es su remitente. Un Apps Script desplegado
por otra persona no puede enviar como ese supervisor cambiando el campo «De».
Cada supervisor necesita su puente autorizado una sola vez; ADMIN guarda la URL
`/exec` y la clave compartida cifrada en el servidor. No se solicita HMAC en cada
correo ni se incorpora a la página o al código fuente. Conservar la clave existente
si coincide con `SERVIDOR_HMAC`; no es necesario generar otra.

1. ADMIN verifica que el supervisor esté activo, con su correo correcto y único en
   Usuarios. En la política de correo debe estar permitido el correo personal
   autorizado. «Personal» significa el correo de su ficha, incluido el corporativo.
2. Con esa cuenta Google, actualizar juntos [Proxy.gs](../apps-script/proxy/Proxy.gs)
   y [Servidor.gs](../apps-script/proxy/Servidor.gs), conservando
   [Clientes.gs](../apps-script/proxy/Clientes.gs) actualizado y las propiedades
   `SERVIDOR_HMAC` y `CARPETA_EVIDENCIAS`. Ejecutar `verificarGoogleServidor` y
   aceptar los permisos de cuenta, Drive y correo. No pegar secretos en registros.
3. Apps Script → Implementar → Administrar implementaciones → editar la aplicación
   web existente → **Nueva versión** → implementar. Ejecutar como la cuenta del
   supervisor y mantener el acceso que permite al servidor invocar el puente
   firmado. Guardar el archivo en el editor no actualiza el `/exec` publicado.
4. ADMIN guarda y verifica la conexión de **esa cuenta** en Drive y envío de correo.
   Los campos secretos vacíos conservan el valor guardado. Copiar archivos a Drive
   con otro puente no demuestra que la conexión de correo de esta cuenta coincida.
5. Antes de cerrar y enviar, ITSANET comprueba el remitente y la capacidad del
   puente publicado. Una combinación antigua de Proxy/Servidor se identifica con
   una instrucción de actualizar ambos archivos; la recepción permanece abierta.
   Confirmar destinatarios y formato antes de continuar.

Google debe confirmar remitente y destinatarios para marcar la entrega como
ENTREGADA. Una operación de Drive confirmada no equivale a correo enviado.
Una confirmación interrumpida queda en REVISION: revisar Enviados antes de decidir;
no se reenvía automáticamente porque podría duplicarse el mensaje.

En **Entregas y errores** o **Entregas e imágenes pendientes**, el supervisor ve
actualización automática cada cinco segundos, remitente, destinatarios, estado,
ayuda e intentos. **Enviar último informe desde mi correo** recupera la entrega
más reciente con su cuenta autorizada, conserva el informe y exige confirmar que
no fue enviado. No crea otro cierre ni otra versión. ADMIN resuelve duplicados y
anulaciones; los supervisores no editan claves ni conexiones desde esa vista.

## Evidencias y carpetas

Las nuevas copias usan esta estructura:

```text
CARPETA_EVIDENCIAS / CLIENTE / MARCA / RECEPCIÓN
  RECEPCION / TIPO DE FOTO
  VALIDACION / SKU / TIPO DE FOTO
  FALTANTE / SKU / TIPO DE FOTO
  SOBRANTE / SKU / TIPO DE FOTO
  PNC / SKU / TIPO DE FOTO
  INFORMES / archivos emitidos
```

Cada categoría y subcarpeta se crea al guardar contenido. Comprobar una recepción
solo prepara cliente, marca y recepción; no crea categorías vacías. Las carpetas
vacías antiguas no se borran automáticamente para proteger el contenido existente.
El puente conserva un registro técnico de entregas para evitar correos duplicados.

Las fotos de SKU tienen código y secuencia. Antes del cierre pueden incluir el
identificador técnico de copia; el manifiesto final conserva su orden y nombre.
Una foto compartida utiliza un binario y accesos directos para los otros códigos.
Cada enlace de evidencia apunta al SKU y categoría correspondientes: nunca se
reutiliza la carpeta del primer SKU como enlace de los demás.

La galería filtra por clasificación y SKU y ofrece los enlaces confirmados a sus
carpetas. Las miniaturas se cargan bajo demanda y las páginas son acotadas.
**Revisar envío a Drive → Reintentar** actualiza las fotos antiguas pendientes o
reubica las confirmadas por su identificador, sin volver a subir el binario.
Vincular otra evidencia a una imagen copiada programa también su nueva ubicación.
Las imágenes pendientes permanecen temporalmente en disco; solo se retira esa
copia local después de confirmar Drive. MySQL conserva referencias y auditoría.

## Clientes, conteos y listas

El cliente de una nueva recepción se elige en un menú. **Gestionar clientes**
permite al supervisor autorizado agregar clientes y editar los requisitos de pallet
y posición. Los formatos y columnas son operativos. ADMIN mantiene las conexiones,
credenciales, política general y asignación de permisos.

**Editar conteo** está disponible en Recepción actual y al filtrar novedades;
**Corregir conteo**, en la ficha de validación; también hay edición en Bitácora.
Con varios registros del mismo SKU se elige el registro que se corrige, no se
sustituye silenciosamente el total. Se exige un motivo, se conserva la clasificación
física y se verifica que otro operador no haya cambiado el conteo. Anulación y
sustitución se guardan juntas: un error revierte ambas.

La bitácora muestra conteos activos. **Mostrar anulados para auditoría** revela
originales y compensaciones; estos no se suman como sobrantes. El filtro de estado
usa la situación actual del SKU. «Sin buscar» puede no tener eventos de conteo;
la tabla de Recepción actual permite localizar esos SKU.

Cuando un SKU pertenece a varios packing lists se selecciona su origen. El
reparto entre listas pendientes muestra una propuesta para confirmar; guarda todas
sus partes juntas y no duplica las unidades PNC. Un exceso real exige confirmación.
Antes de enviar se deben asignar a su lista los conteos antiguos de SKU compartidos
que quedaron sin origen, usando Editar conteo. Se conservan sus registros de auditoría.

## Formato y tamaño del informe

El supervisor confirma **formato original**, **columnas adicionales** o **auditoría**.
Los dos formatos para cliente generan un archivo independiente por cada packing
list, con sus filas, cantidades, pallets, observaciones y evidencia. El original
conserva las columnas existentes y el encabezado previo a la tabla. El ampliado
agrega las columnas faltantes de validación. La auditoría conserva el detalle
completo y la bitácora. Las listas idénticas siguen teniendo archivos identificables
por su origen; el servidor rechaza archivos faltantes o duplicados por lista.

En el archivo proporcionado, `VW_REC0001.xlsx`, hay 7 filas en REV y un MAESTRO de
16.675 filas. La búsqueda de la columna **ok** consulta ese maestro; no indica si
la cantidad física coincide. La exportación sustituye esa búsqueda por `ok` o
`N/D` según la existencia en el catálogo Depot local del mismo cliente. El conteo
físico tiene columnas independientes. Actualizar el catálogo antes de enviar; no
se crean SKU automáticamente por mostrar N/D. Las fórmulas ordinarias compatibles
se conservan; el informe no depende de la hoja MAESTRO incrustada.

La prueba con el adjunto generó una hoja REV con sus 7 filas, sin MAESTRO: 11.613
bytes frente a 4.220.355 bytes de entrada. Es una comprobación de formato con
cantidades de prueba, no un informe operativo enviado al cliente.

Las nuevas instantáneas de cierre se comprimen sin pérdida con comprobación de
integridad. ADMIN → Uso de almacenamiento permite consultar y compactar las
instantáneas históricas en lotes de hasta 20. Repetir hasta terminar; no toca tareas
en procesamiento, fotos, informes originales ni auditoría. La cifra de ahorro es
lógica; el archivo físico de MySQL puede conservar espacio para reutilizarlo.

## Comprobación y producción

Las pruebas automáticas cubren corrección atómica, reparto, permisos, selección del
remitente, confirmación de correo, compresión, archivos por lista y enlaces compartidos.
Se comprueba además MySQL en una base desechable y la interfaz móvil en Chromium.
Resultado: 997 pruebas de la suite aprobadas; 58 pruebas de integración contra
MySQL y 16 focales aprobadas. La revisión móvil comprobó corrección de conteo,
PNC, listas separadas, filtros, auditoría y galería. La compilación del frontend
también pasó. Los dobles de Google no demuestran entrega real ni permisos del
Drive empresarial.

Seguir [CIERRE_VALIDACION_Y_PASE.md](CIERRE_VALIDACION_Y_PASE.md) para actualizar
el servidor conservando los datos. Después de publicar también el puente Google,
validar remitente y Drive y enviar una prueba autorizada. Solo entonces reintentar
la entrega elegida de producción; comprobar Enviados, destinatario y carpetas reales.
