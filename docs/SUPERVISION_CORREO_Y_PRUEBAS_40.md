# Supervisión y correo revisable · versión 40

Candidato final `itsanet-20261018-supervision-correo-final`, interfaz `20261018-40.1`. Esta versión se valida en el entorno aislado; el pase del servidor real requiere ejecutar el actualizador desde ese servidor. No importar datos, usuarios ni conexiones del entorno de pruebas.

## Cuentas y autorización de Google

En **Usuarios**, ADMIN puede editar la ficha y abrir **Configurar Google** para verificar y guardar el `/exec` del supervisor y su clave HMAC. La cuenta del perfil debe coincidir con la cuenta Google ejecutora. La clave guardada se conserva si se deja vacía. El guardado se audita con la identidad real del administrador y el destinatario de la configuración.

Google requiere que cada propietario autorice sus permisos una vez. ADMIN puede preparar su configuración, pero no sustituir ese consentimiento cambiando la dirección del remitente. El supervisor no necesita acceso a las conexiones base.

Las contraseñas de acceso se guardan como hash; no existe una contraseña original recuperable. **Restablecer contraseña**, exclusivo de ADMIN, reemplaza la clave, cierra las sesiones del usuario y conserva los conteos. La contraseña nueva no se guarda en auditoría ni se devuelve en el listado de usuarios. El usuario puede cambiarla desde Mi cuenta.

Actualizar juntos `apps-script/proxy/Proxy.gs` y `Servidor.gs` en cada proyecto; publicar Nueva versión del mismo despliegue `/exec`, conservando `Clientes.gs`, las propiedades, `SERVIDOR_HMAC` y la carpeta matriz. La nueva capacidad `correoEditable` evita que un puente antiguo sustituya silenciosamente la redacción aprobada.

## Correo final

**Recepción actual → Informes → Correo final editable** genera una vista con las cantidades actuales, sobrantes, faltantes, PNC, otras incidencias, observaciones y fotografías. Las tablas salen de los datos registrados; solo son editables asunto, destinatarios y redacción. Guardar vuelve a calcular la vista. Los cambios concurrentes impiden enviar una versión obsoleta.

Al finalizar, primero se archiva el XLSX de cada embarque. Después aparece la revisión del correo con los archivos descargables. La redacción aprobada se congela en la entrega; los textos de los envíos confirmados permanecen consultables.

Si Google no está configurado o no confirma la conexión, se puede **continuar con envío manual**: se cierra la recepción con documentos archivados y no se programa correo automático. También se puede recuperar un envío pendiente desde **Entregas → Revisar correo final · copiar o enviar**. Esta es la única acción principal de revisión: todos los reenvíos pasan por el correo editable y los documentos; se retiró el acceso anterior que saltaba esa revisión.

**Copiar correo completo** conserva tablas y enlaces mediante el portapapeles enriquecido, con alternativa compatible con HTTP de la red local. **Descargar correo HTML** conserva el documento fuera de la app. **Copiar asunto y destinatarios** facilita completar esos campos. **Abrir Gmail** abre la redacción; hay que pegar el contenido y adjuntar los XLSX descargados. Outlook admite la misma copia. Las fotos conservan sus permisos de Drive: la copia manual no publica imágenes privadas.

La preparación manual detiene los envíos automáticos pendientes para evitar duplicados. Si un envío está procesándose o su resultado es ambiguo, primero se debe revisar Enviados. **Ya lo envié desde mi correo · registrar** conserva una declaración del supervisor, claramente distinta de un acuse de Google. Copiar, descargar o abrir Gmail no acredita envío. Si no hay conexión con el servidor, solo se puede usar un HTML o correo previamente guardado; no se inventan los conteos actuales.

## Operación y etiquetas

- Pallets: letras y números; `.` para subpallet y `-` para varios pallets. Ejemplos: `B02`, `DP`, `B02.1`, `B02-B03`. Se rechazan comillas, barras, guiones bajos y separadores vacíos. Las rutas de conteo, corrección y unidad logística comparten esta regla. El CSV para Depot detecta registros históricos inválidos e indica el SKU y pallet a corregir; no adivina su valor.
- **Recepción actual** permite plegar la lista y abrir directamente Bitácora. Las tablas tienen desplazamiento propio y encabezados fijos.
- Las fotos de los modales usan miniaturas autenticadas y se amplían dentro de la aplicación. La tabla de archivos de Drive permite filtrar nombre/SKU/ruta y consultar estado, carpeta y vista previa; se actualiza mientras está abierta.
- **Guía de fotos** muestra el orden: recepción exterior, packing inicial, apertura con packing, validación por SKU, novedades y estado final. Usa las recomendaciones configuradas. Se conservan las rutas por cliente, marca, recepción y SKU; no se crean subcarpetas ADICIONAL dentro del SKU.
- Bultos: vista previa de las primeras etiquetas disponible antes de generar el lote. Código `A01`, `B02`, etc., y CODE128 con el mismo dato.
- Producto: plantilla estándar 100 × 50 mm con fuentes compactas y espacio para serie y su código de barras. Cantidad inicial 1, editable; copias independientes. Navegador, ZPL y puente respetan esa cantidad.
- La cabecera de todas las páginas incorpora **Catálogo** y **Etiqueta por código** para SUPERVISOR/ADMIN. El catálogo se actualiza mediante las conexiones Depot guardadas; imprimir desde el catálogo no requiere crear una recepción ni importar un packing list.
- **Gestionar clientes** permite corregir el nombre visible, ocultar una entrada o elegir el destino para recepciones nuevas. No cambia identificadores históricos de Depot ni mezcla recepciones. Revisar si `VENTURA/VW` representa una marca antes de considerarlo duplicado.

## Pruebas de supervisores desde casa

Conviene usar un servicio de pruebas independiente, por ejemplo puerto **3003**, manteniendo producción en **3002**. El puerto por sí solo no aísla los datos: deben ser distintos la base MySQL, el directorio de archivos, los secretos de sesión, el usuario de base de datos y las conexiones Google. El Compose de desarrollo existente ya impone base y volúmenes independientes y publica solo en loopback.

Para acceso desde casa, la opción preferida es la VPN corporativa con HTTPS para la app de pruebas. Si se usa un dominio, debe publicar únicamente ese servicio detrás del proxy HTTPS y autenticación; no abrir MySQL ni sustituir el puerto de producción. La cámara del navegador requiere HTTPS fuera de localhost.

Crear cuentas de prueba individuales para supervisores; no copiar contraseñas ni una base de producción. Usar una carpeta Google de pruebas y destinatarios de prueba explícitos. El catálogo puede replicarse con una conexión de lectura autorizada; no habilitar cargas de stock reales desde el entorno de pruebas. Recorrido sugerido: dos embarques, SKU compartido, faltante/sobrante/PNC, corrección de pallet, fotos y carpeta, dos tipos de etiquetas, exportación independiente, correo manual y envío directo confirmado.

La publicación externa requiere el dominio o acceso VPN del servidor elegido. No se configura automáticamente ni se considera validada desde un enlace localhost.

## Validación del candidato

- Suite completa: **1.080 pruebas aprobadas** (611 Python y 469 JavaScript).
- MySQL 8.4, base desechable separada: **22 pruebas finales aprobadas** del correo, perfiles, restablecimiento, clientes, pallets y códigos de recepción de hasta 60 caracteres. La clave interna del borrador usa un identificador fijo de 39 caracteres y no requiere alterar el esquema. Además se verificó el recorrido previo de operación, fotos, etiquetas y cuentas con 64 casos; hay casos compartidos y no deben sumarse como pruebas distintas.
- Revisión final SQLite de correo y recuperación: **36 pruebas aprobadas**; sintaxis, imports y referencias del navegador: **52 comprobaciones aprobadas** (incluidas en la suite general).
- Chromium en 390 × 844: 28 SKU, cabeceras fijas, bitácora, etiquetas antes de imprimir, cantidad editable y serie con barras, correo con datos reales y copia enriquecida por HTTP, descarga real de XLSX, declaración manual y herramientas de catálogo desde Mi cuenta. La búsqueda de catálogo de ese recorrido usó un resultado simulado; no consultó Depot real.
- Chromium adicional: foto guardada realmente en el servidor aislado, vista previa y ampliación en modales, tabla de archivos y cierre manual con XLSX archivado, recepción cerrada y envío automático detenido.

Estos resultados no acreditan una impresión física en Zebra ni un correo real enviado por Google. El puente se verificó con servicios simulados. La autorización de cada propietario, publicación de Apps Script, acceso a la carpeta real y prueba de correo a un destinatario elegido deben comprobarse en el entorno que se publique.

La revisión final de la interfaz `40.1` unifica el acceso desde Entregas: ya no existe un botón de reenvío que omita la vista del correo y sus documentos. El navegador comprobó el cambio de destinatarios y una sola solicitud después de confirmar; Google se simuló y no se envió correo real. Un correo en procesamiento muestra su redacción congelada. Los estados manuales se presentan como «por enviar» o «envío declarado», sin confundirlos con una cancelación operativa.
