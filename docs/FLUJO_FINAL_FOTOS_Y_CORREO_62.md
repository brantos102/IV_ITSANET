# Versión 62 · recepción, fotografías y correo al ejecutivo

Esta revisión conserva los conteos, anulaciones, packing lists originales y documentos históricos. No modifica las cantidades de recepciones existentes. No necesita cambios de esquema MySQL.

## Fotografías y carpetas

Al crear la recepción se registra una tarea durable de preparación. Google la ejecuta en segundo plano, cuando están registrados sus datos de ingreso o su packing list y existe conexión del responsable. Sin conexión, queda pendiente: nunca se anuncia una carpeta inexistente como confirmada.

```text
CLIENTE / MARCA / CÓDIGO DE RECEPCIÓN
  RB63196
    SOBRANTES / SKU
    FALTANTES / SKU
    PNC / SKU
    PRODUCTOS / SKU
    BULTOS / Bulto… / Caja…
    PRE-INGRESO
    FOTOS-FINALES
    PANORAMICAS
  OTRO-EMBARQUE
    …
```

Cada embarque es hijo directo de la recepción. PRODUCTOS guarda fotos de SKU sin novedad; el tipo de foto «adicional» no crea un conteo ni convierte un SKU declarado en adicional. Una foto de SKU vinculada a un bulto conserva además ese vínculo dentro de su destino. Otras evidencias de recepción usan OTRAS-EVIDENCIAS cuando corresponde.

COMPARTIDAS identifica fotos expresamente comunes a varios embarques. POR-ASIGNAR conserva las fotos históricas cuyo embarque es ambiguo: no se atribuyen a un embarque por suposición. Los nombres problemáticos se normalizan conservando una huella para evitar colisiones.

Antes de guardar se muestra la ruta del lote y cada imagen. «Revisar imagen y elegir carpeta» permite asignar un destino por fotografía con su vista previa. Para prerecepción se limpia el vínculo a SKU y bulto. Las fotografías guardadas muestran su clasificación, ruta esperada y estado de organización. Editar vínculo también permite revisar la imagen.

Las imágenes conservan identificador, secuencia y auditoría. Al reorganizar una foto confirmada se reutiliza su fileId; se conserva un acceso desde la carpeta anterior y no se vuelve a subir el binario. Las cantidades no cambian. Para recepciones anteriores: Fotos → Actualizar carpetas por embarque; revisar la propuesta y confirmar. No se ejecuta una reorganización masiva sobre registros de producción durante la actualización.

La carpeta madre confirmada por esta versión conserva su ID si después se añade un embarque o se cambia la marca. El puente comprueba que el nombre corresponde al código de esa recepción.

## Redactar y enviar

1. Abrir Correo final editable. El encabezado identifica recepción, cliente–marca y grupo. «Elegir embarque / packing list» permite revisar si se reporta separado o consolidado.
2. Revisar Para: **ejecutivo de cuenta asignado**. Los destinatarios se guardan por grupo; no se deducen ni se copian automáticamente del PDF de ejemplo.
3. Buscar el mensaje original en **mi Gmail**, por asunto y fechas, o elegir correo nuevo. La vista permite consultar el texto y abrir el mensaje completo con sus adjuntos en Gmail. La búsqueda no envía, borra ni marca mensajes y el buzón no se replica en MySQL.
4. Editar el cuerpo directamente. Se pueden añadir o eliminar textos y secciones, usar negrita y listas. Los bloques de cifras, documentos, distribución y fotografías se reconstruyen con los datos guardados; una edición del HTML no puede sustituir cantidades calculadas ni insertar fotos ajenas. Las cantidades se corrigen en el conteo, conservando su auditoría.
5. Registrar prerecepción y seleccionar/ordenar miniaturas. El orden inicial es prerecepción → observaciones → novedades con sus fotos. Las tablas se actualizan si cambian los conteos; no queda una diferencia antigua dentro de un cuerpo ya editado.
6. Preparar / actualizar documentos **dentro del modal**. Se reutilizan las revisiones vigentes y cada archivo se descarga desde la misma redacción.
7. Enviar correo → revisar remitente, ejecutivo, hilo, documentos y miniaturas → confirmar. La aplicación registra una entrega durable y el resultado se consulta en Entregas. «Programado» no equivale a enviado; solo el acuse de Google confirma el envío.

El botón del borrador reporta el grupo revisado sin cambiar el estado ni las cantidades de la recepción. **Finalizar** conserva el proceso de cierre completo y su revisión de todos los grupos. Las entregas de informe pendientes, aunque su recepción siga abierta, se pueden consultar y resolver desde Entregas.

Se bloquea el envío cuando faltan documentos, sus datos cambiaron, hay imágenes sin copiar u organizar, el hilo pertenece a otra cuenta o existe otra entrega activa. Dos confirmaciones simultáneas de la misma revisión reutilizan una entrega. Una confirmación interrumpida exige revisar Enviados; no se repite automáticamente.

Guardar, copiar, descargar HTML y descargar miniaturas notifican su resultado. HTML incorpora miniaturas locales; si una no está disponible se informa para corregir la selección. Descargar o copiar no exige cerrar ni modifica una cola de correo. Si se enviará manualmente, resolver antes cualquier entrega automática pendiente en Entregas para evitar duplicados. Algunos clientes de correo omiten imágenes pegadas: el ZIP incluye los JPEG para insertarlos y el HTML para revisión.

Los avisos de productos pendientes en Depot se mantienen como validación interna. **No aparecen en el cuerpo del correo al ejecutivo**.

## Cuenta propia de supervisores y administradores

Johnny Barahona (`johnnybarahona51@gmail.com`), Inventario (`inventarioopuio@itsanet.com`) y F. Morales (`fmorales@itsanet.com`) pueden usar la misma función si su ficha activa tiene el rol y correo correctos y cada persona autoriza su propio despliegue. La revisión no crea ni cambia sus fichas automáticamente.

ADMIN → Operación diaria → Remitente de informes → Revisar cuentas muestra ficha, conexión guardada y capacidades publicadas. Cada persona puede autorizarse en Mi cuenta y correo; el compositor también ofrece Conectar mi correo. Los secretos se guardan cifrados en el servidor y no se devuelven al navegador.

Una prueba de Apps Script que devuelve `bespinoza@itsanet.com` solo acredita esa cuenta. No acredita a los demás remitentes. Entrar con Google al aplicativo es opcional y es independiente de autorizar Drive/Gmail para informes.

Para cada cuenta:

- Actualizar **juntos** Proxy.gs, Clientes.gs, Servidor.gs y Gmail.gs del proyecto propio con los archivos de `apps-script/proxy/`.
- Usar los scopes de `appsscript-gmail.json` en el manifiesto real **appsscript.json**, incluidos gmail.readonly y gmail.send. Habilitar Gmail API en el proyecto Google Cloud **asociado a ese Apps Script**.
- Con esa persona como cuenta activa, ejecutar verificarGoogleServidor y verificarGmailServidor y aceptar la autorización. Compartir la carpeta de evidencias con esa cuenta.
- Publicar Nueva versión del mismo despliegue: Ejecutar como Yo; URL /exec. Conservar su SERVIDOR_HMAC y no reutilizar el /exec de otro supervisor cambiando solo el texto del remitente.
- Guardar y verificar la conexión en Mi cuenta; comprobar acceso a mi Gmail y buscar el correo desde una recepción. El diagnóstico de lectura no envía correo ni asegura por sí solo la cuota disponible al enviar.

Para la cuenta personal @gmail.com, la configuración OAuth del proyecto debe admitir usuarios externos; un proyecto limitado al dominio corporativo no la autoriza. La política Workspace y la autorización se verifican con TI si Google las rechaza.

La versión publicada devuelve `versionCodigo: 20261021-62` y capacidad `carpetasRecepcion62`. La consulta del buzón verifica primero el perfil Gmail de la persona y no necesita abrir la carpeta Drive. Los puentes anteriores mantienen su comprobación compatible hasta actualizarse. El diagnóstico permite identificar API desactivada, permisos, autorización, política, buzón, cuota y problemas de red sin mostrar tokens. La conexión y los envíos reales de estas personas deben validarse en sus sesiones: las pruebas de esta entrega usan Google simulado.

## Posición, bitácora e informes

Se escribe o selecciona una sola posición final. `BM-A-010-01` se interpreta como Nave BM, Literal A, Columna 010, Nivel 01, sin perder ceros. Una nota de lectura confirma el desglose; ya no aparecen cinco casillas de captura. El pallet continúa siendo independiente y no se impone DP.

Ubicaciones generales como CALLEKL se conservan; no se inventa su desglose Depot. Un CSV que requiere una posición completa avisa de campos pendientes. Una posición con segmentos de más no se recorta silenciosamente. La hoja REV incorpora la posición final sugerida; las hojas de detalle ya la incluyen.

ADICIONALES contiene exclusivamente SKU fuera del packing list de la recepción. Los sobrantes de SKU declarados permanecen en su validación y no se duplican en esa hoja. Lista y bitácora permiten filtrar adicionales. Detalle e historial muestran nombre del operario, observación y acceso a corrección según permisos. La opción «No apareció» se retira del registro visible; los ceros se registran en el conteo y los históricos se conservan.

ADMIN dispone de secciones de configuración, indicador de cambios pendientes y resultado visible al guardar. Altas y cambios de repositorios/estaciones se guardan al confirmar su formulario; no eliminan fotos ni archivos existentes.

## Pase a producción

Publicar primero los archivos Google de esta versión por cuenta. Usar después `scripts/actualizar_produccion.sh` con el **commit completo probado**, siguiendo su respaldo privado y pausa de servicio. El procedimiento no sobrescribe la configuración local ni borra registros. No ejecutar pytest contra la base de producción.

Después, recargar la aplicación y revisar una recepción de prueba: carpeta/embarque, prerecepción, corrección de posición, documentos, redacción, destinatario y acceso Gmail propio. La reorganización de fotos históricas requiere revisar su propuesta. El código y las pruebas de esta revisión no han desplegado ni alterado el servidor corporativo.

## Validación de esta entrega

- Batería general: **1.393 pruebas aprobadas**, incluyendo JavaScript/Apps Script y 837 pruebas Python.
- MySQL en base exclusiva de revisión: **23 aprobadas**, incluyendo dos confirmaciones concurrentes, recuperación de entregas y bloqueo de informes con conteos históricos sin packing list.
- Chromium, escritorio y 390 px: cuerpo libre guardado; permisos del operario; Enviar visible para supervisión; HTML descargado; posición única y desglose; vista previa de destinos; subida de prerecepción con miniatura incorporada; Excel preparado y descargado dentro del modal; cuentas y guardado en administración.
- Google simulado: identidad propia, búsqueda sin depender de Drive, MIME de respuesta, documentos e imágenes, acuse e idempotencia. No se enviaron correos reales ni se comprobaron buzones corporativos durante estas pruebas.

Los tests usan bases SQLite temporales o MySQL exclusivo de revisión. El PDF se utilizó como referencia de presentación; no se importaron sus destinatarios, cantidades ni instrucciones como registros de recepción.
