"""Manual y presentación técnicos estáticos. No conecta con servicios ni importa la app."""
from pathlib import Path
import ast
import argparse
import base64
import importlib.util
import json
from html import escape as E

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('documental', ROOT/'scripts/generar_presentacion_tecnica_20261027.py')
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
T, L, C = B.tabla, B.lista, B.codigo
FECHA = '28 de octubre de 2026'
REF = B.REVISION

USOS = {
'operadores':'Identidad, hash de credencial, rol, habilitación y firma de registros.',
'sesiones':'Sesiones locales y vencimiento; referencia al operador.',
'productos':'Maestro de productos y estado de verificación del catálogo.',
'producto_codigos':'Códigos alternativos asociados al SKU del maestro.',
'recepciones':'Cabecera del modelo inicial de recepción; compatibilidad.',
'packing_items':'Líneas del packing del modelo inicial; compatibilidad.',
'pallets':'Pallets del modelo inicial; compatibilidad.',
'scan_events':'Eventos del modelo inicial; compatibilidad.',
'skus_pendientes':'Productos por resolver del modelo inicial; compatibilidad.',
'auditoria':'Auditoría del modelo inicial; compatibilidad.',
'app_recepciones':'Cabecera operativa, cliente, bultos, estado, fechas, orígenes y embarques.',
'app_lineas':'Líneas originales del packing, orden, SKU, cantidad y columnas adicionales.',
'app_skus':'Proyección de esperado/contado y distribución por pallet y origen.',
'app_calidad_skus':'Clasificación y datos de calidad relacionados con el SKU operativo.',
'app_presencias':'Operador/dispositivo activo y última actividad dentro de una recepción.',
'app_informes':'Versiones de informe, tipo, huella de datos, estado y autoría.',
'app_auditoria_general':'Acciones generales, referencias y datos de auditoría del aplicativo.',
'app_eventos':'Libro de eventos operativos: conteos, cero, anulaciones y motivos.',
'app_huellas':'Huellas del packing para reconocer contenido previamente cargado.',
'app_archivos':'Metadatos de archivos, SHA-256, tamaño y referencias confirmadas de Drive.',
'app_archivo_identidades':'Secuencia y procedencia de fotografías, independientes del ID remoto.',
'app_archivo_skus':'Relación entre un archivo y uno o varios SKU sin duplicar su contenido.',
'app_config':'Configuraciones, reservas de identidad y credenciales de integración cifradas.',
'app_entregas':'Cola durable de entregas, instantánea de datos, intentos y resultado.',
'app_ingresos':'Datos complementarios del ingreso asociados a la recepción.',
'app_unidades_logisticas':'Bultos/cajas y relación jerárquica padre-hijo.',
'app_evidencias':'Vínculo archivo-recepción-SKU-unidad-categoría y eliminación lógica.',
'app_copias_drive':'Cola y estado de copia a Drive, intentos, próximo intento y error.',
'app_stock_depot':'Caché de posiciones de stock por SKU y cliente.',
'app_impresiones':'Trabajos de impresión, estación, reserva y seguimiento de estado.'}


def diccionario():
    salida=[]
    for cls in ast.parse((ROOT/'app/models.py').read_text()).body:
        if not isinstance(cls, ast.ClassDef): continue
        nombre=next((ast.literal_eval(n.value) for n in cls.body if isinstance(n,ast.Assign)
                     and any(isinstance(t,ast.Name) and t.id=='__tablename__' for t in n.targets)),None)
        if not nombre: continue
        campos=[]; restricciones=[]
        for n in cls.body:
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__table_args__' for t in n.targets):
                restricciones.append(ast.unparse(n.value))
            if not (isinstance(n,ast.AnnAssign) and isinstance(n.value,ast.Call) and ast.unparse(n.value.func)=='mapped_column'): continue
            call=n.value
            fks=[a for a in call.args if isinstance(a,ast.Call) and ast.unparse(a.func)=='ForeignKey']
            campos.append({'nombre':n.target.id,'anotacion':ast.unparse(n.annotation),
                'tipoSQL':', '.join(ast.unparse(a) for a in call.args if a not in fks) or 'Inferido de anotación / clave externa',
                'opciones':{k.arg:ast.unparse(k.value) for k in call.keywords},
                'referencias':[ast.literal_eval(a.args[0]) for a in fks],
                'ondelete':[ast.literal_eval(k.value) for a in fks for k in a.keywords if k.arg=='ondelete']})
        salida.append({'tabla':nombre,'clase':cls.name,'uso':USOS[nombre],'campos':campos,'restricciones':restricciones})
    por_campo={(t['tabla'],f['nombre']):f for t in salida for f in t['campos']}
    def resolver(f, vistos=()):
        if not f['tipoSQL'].startswith('Inferido'): return f['tipoSQL']
        if f['referencias'] and f['referencias'][0] not in vistos:
            ref=f['referencias'][0]
            destino=por_campo.get(tuple(ref.split('.')))
            if destino: return resolver(destino, vistos+(ref,))
        return next((tipo for token,tipo in [('int','Integer'),('str','String'),('bool','Boolean'),('datetime','DateTime'),('float','Float')] if token in f['anotacion']), 'Inferido')
    for t in salida:
        for f in t['campos']: f['tipoSQLResuelto']=resolver(f)
    return salida


def arbol_drive():
    return C('''CARPETA_RAIZ_CONFIGURADA/
└── CLIENTE/                         (si está definido)
    └── MARCA/                       (si está definida)
        └── CODIGO_RECEPCION/
            ├── INFORMES/            (al subir un informe)
            └── EMBARQUE/            (cuando la evidencia tiene embarque)
                ├── PRE-INGRESO/
                ├── PANORAMICAS/
                ├── FOTOS-FINALES/
                ├── BULTOS/
                │   └── BultoNN_recepcion_embarques/
                │       └── CajaNN_codigo/       (si aplica)
                ├── PRODUCTOS/SKU/
                ├── PNC/SKU/
                ├── SOBRANTES/SKU/
                └── FALTANTES/SKU/''')


def secciones(inv, tablas):
    return [
    ('alcance','1. Identificación y alcance',
     '<p class="lead">IV ITSANET (Ingreso &amp; Validación Itsanet) es una aplicación web para recepción y validación física de mercadería, registro de evidencias, trazabilidad por ítem, generación de informes y entrega de correo.</p>'+
     T(['Control','Referencia'],[['Documento','ITSANET-MT-20261028 · revisión 1.1'],['Fecha',FECHA+' · America/Guayaquil'],['URL operativa','https://apps.flexnetuio.com:8443/app/'],['Código funcional documentado','v69 · recursos 20261024-69'],['Commit funcional',C(REF)],['Estado operativo','En línea, confirmado por el responsable el 28/10/2026.']])+
     '<p>El manual combina revisión estática del código de referencia y salidas de terminal del servidor compartidas el 27/10/2026. El inventario de tablas describe el modelo declarado; no es una extracción del esquema productivo. La revisión Git instalada, el nombre del esquema, las versiones efectivas de Python/Apache y los parámetros privados se cotejan en el inventario de operación.</p>'),
    ('arquitectura','2. Arquitectura y comunicación',B.arquitectura()+
     '<p>El navegador carga HTML, CSS y JavaScript bajo <code>/app/</code>. Las solicitudes de registro y consulta llegan al backend por la publicación HTTPS de Apache. Uvicorn ejecuta la aplicación ASGI de FastAPI; esta verifica sesión, permisos y reglas y utiliza SQLAlchemy/PyMySQL para persistir en MySQL.</p>'+
     T(['Enlace','Protocolo / destino','Responsabilidad'],[['PC / handheld → Apache','HTTPS · apps.flexnetuio.com:8443','Certificado, publicación y acceso web.'],['Apache → Uvicorn','Backend en puerto 3002','Enrutamiento hacia interfaz y API; conservar esquema HTTPS y transmisión SSE.'],['FastAPI → MySQL','SQLAlchemy + PyMySQL','Transacciones, consultas, integridad y colas durables.'],['Backend → Google','HTTPS · OAuth, Drive API y Gmail API','Autorización, copia de evidencias y entrega del correo.'],['Backend → Depot','API HTTPS, si está habilitada','Consulta del catálogo/stock y caché local.']])+
     '<p>Las directivas efectivas de proxy, el certificado y sus vencimientos se administran en Apache. La escucha local de un puerto no demuestra su accesibilidad desde Internet.</p>'),
    ('tecnologia','3. Lenguajes, componentes y código fuente',
     T(['Capa','Tecnología','Función'],[['Backend','Python','Reglas de negocio, persistencia, permisos e integraciones.'],['API','FastAPI 0.143.0 + Pydantic 2.13.5','Rutas HTTP, validación de solicitudes y respuestas.'],['Servidor de aplicación','Uvicorn 0.53.0','Servidor ASGI; no sustituye la publicación Apache.'],['Acceso a datos','SQLAlchemy 2.1.4 + PyMySQL 1.1.1','ORM y conector del motor MySQL.'],['Interfaz','HTML5, CSS y JavaScript modular','Pantallas de PC/handheld, captura, validación y actualización de vistas.'],['Archivos','SheetJS, openpyxl, Pillow, jsPDF','Excel, imágenes, documentos y etiquetas.'],['Códigos de barras','JsBarcode / ZXing','Generación CODE128 y lectura compatible.'],['Construcción y pruebas','Node.js, esbuild, pytest','Preparación de recursos y verificación; Node no es el backend productivo de esta aplicación.']])+
     '<p>Las versiones anteriores son dependencias declaradas en el repositorio; no se presentan como una lectura de paquetes instalados en producción. SQLite, Firebase y Apps Script permanecen como opciones de desarrollo/compatibilidad; la arquitectura corporativa documentada usa Apache y MySQL.</p>'+
     C('''IV_ITSANET/
├── app/main.py              # FastAPI, arranque y recursos /app/
├── app/config.py            # Parámetros y rutas
├── app/db.py                # Motor, sesiones y ajustes SQL
├── app/models.py            # Modelo relacional
├── app/routers/             # Endpoints y permisos
├── app/services/            # Operación, archivos y Google/Depot
├── firebase/public/         # HTML, CSS, módulos JS y service worker
├── scripts/                 # Actualización, respaldo y diagnóstico
├── tests/                   # Verificaciones aisladas
├── requirements.txt         # Dependencias Python
└── package.json             # Herramientas y dependencias JS''')),
    ('infraestructura','4. Servidor e infraestructura observada',
     T(['Elemento','Valor / situación observada'],[['Host / IP local','apps · 192.168.4.94 · interfaz ens160'],['MySQL local','8.0.46-0ubuntu0.24.04.4 · comentario Ubuntu'],['Servicio de aplicación','iv-itsanet.service · Uvicorn en 0.0.0.0:3002'],['Publicación','Apache2 en *:8443 · itsanet-app-8443.conf'],['Archivo del virtual host','/etc/apache2/sites-enabled/itsanet-app-8443.conf'],['MySQL','127.0.0.1:3306; listener adicional 127.0.0.1:33060'],['Recursos, captura del 27/10','4 CPU lógicas; 11 GiB RAM, 9,6 GiB disponibles; raíz 73 GB, 50 GB disponibles.'],['Servicios compartidos','Apache 80/443 para Data Sync; contenedor itsanet-data-sync saludable, 127.0.0.1:8080.'],['Otros servicios','SSH 22; pm2-root.service habilitado pero inactivo/dead en la consulta.'],['Filtrado','UFW inactivo; existen reglas nftables gestionadas por Docker.']])+
     '<p>El resultado de versión MySQL identifica la instancia local consultada. La conexión efectiva de la aplicación se define en <code>VAL_DATABASE_URL</code>; el esquema y usuario se mantienen en configuración protegida. El valor de capacidad es una medición puntual, no una garantía de capacidad futura.</p>'+
     '<p>El servidor es compartido: las actualizaciones del aplicativo deben conservar MySQL, los otros virtual hosts y el contenedor Data Sync. Revisar la exposición de 3002 conforme a la política de red, dado que el binding observado es 0.0.0.0.</p>'),
    ('datos','5. Modelo de datos e integridad',
     '<p>El modelo declara <b>30 tablas</b>. Las tablas <code>app_*</code> conservan la operación web actual; las tablas iniciales de recepción coexisten para compatibilidad. <code>operadores</code>, <code>sesiones</code> y el maestro de productos son componentes compartidos. No eliminar tablas de compatibilidad sin revisar sus consumidores y migración.</p>'+
     C('''app_recepciones.codigo
├── app_lineas             (packing original y orden)
├── app_skus               (estado agregado por SKU)
│   └── app_calidad_skus
├── app_eventos            (libro de registros y correcciones)
├── app_unidades_logisticas (bultos y cajas)
├── app_archivos
│   ├── app_archivo_identidades
│   ├── app_archivo_skus
│   ├── app_evidencias     (SKU, categoría y unidad)
│   └── app_copias_drive
├── app_informes / app_entregas
└── app_presencias / app_ingresos / app_impresiones

operadores → sesiones y presencias
productos → producto_codigos
app_stock_depot: clave compuesta SKU + cliente''')+
     L('InnoDB y utf8mb4 definidos para las tablas MySQL; claves primarias, claves externas e índices según el modelo.','Cantidades: DECIMAL(14,3); precios: DECIMAL(14,4). SQLAlchemy devuelve estos valores a Python como float según la configuración declarada; deben conservarse las validaciones de suma y exportación.','Fechas: DATETIME con milisegundos en MySQL. La sesión SQL utiliza UTC; la presentación operativa usa America/Guayaquil.','Modo SQL estricto: STRICT_ALL_TABLES y NO_ENGINE_SUBSTITUTION. Pool con pre-ping; valores predeterminados: tamaño 5, overflow 5, reciclaje 3600 s.','El identificador del evento permite reconocer reintentos. Las correcciones conservan motivo y registro compensatorio; app_skus es una proyección recalculable de eventos.','Las relaciones CASCADE se documentan en el diccionario: una eliminación de cabecera puede afectar hijos. Las intervenciones directas en SQL requieren revisión y respaldo.')+
     '<p>El árbol resume relaciones funcionales; el diccionario indica cuáles están declaradas como claves externas. La bitácora de aplicación no equivale a almacenamiento inmutable frente a un administrador de base de datos.</p>'),
    ('tablas','6. Inventario funcional de las tablas',
     T(['Tabla','Responsabilidad'],[[f'<code>{E(x["tabla"])}</code>',E(x['uso'])] for x in tablas])+
     '<p>Las extensiones JSON conservan mapas, columnas adicionales y estados que no se fijan en columnas escalares. El manejo de estos contenidos se realiza mediante servicios de la aplicación, preservando compatibilidad y versiones de sus estructuras.</p>'),
    ('evidencias','7. Ciclo de vida de las imágenes y evidencias',
     '<p>Los bytes del archivo se almacenan fuera de MySQL. La base conserva identidad, tamaño, SHA-256, autoría, clasificación, vínculos al registro y estado de copia. Una misma imagen puede justificar varios SKU mediante asociaciones y accesos directos, sin crear un archivo físico por cada vínculo.</p>'+
     T(['Paso','Procesamiento','Registro principal'],[['1. Captura','Cámara/galería; selección de recepción, embarque, SKU y categoría.','Borrador del navegador cuando es posible.'],['2. Guardado','Archivo operativo y metadatos; vinculación con bulto/SKU/incidencia.','app_archivos, app_evidencias y asociaciones.'],['3. Programación','Persistencia de la carga pendiente y del destino.','app_copias_drive.'],['4. Transferencia','OAuth; reserva de ID remoto; carga multipart; comparación MD5 remoto con contenido.','Drive API + datos de la cola.'],['5. Confirmación','Guardar ID, enlace y destino comprobado. Conservar miniatura.','drive_id / drive_url y estado COPIADA.'],['6. Recuperación','Reintento con identidad estable; errores de cuenta/permisos pasan a revisión.','Intentos, próximo intento, error y monitor.']])+
     '<p>Estados de copia: <code>PENDIENTE</code>, <code>PROCESANDO</code>, <code>COPIADA</code>, <code>REVISION</code> y <code>ELIMINADA</code>. Una miniatura visible no confirma la copia a Drive. La aplicación comprueba además la ubicación vigente; mover o renombrar carpetas fuera del flujo puede producir una revisión del destino.</p>'+
     C('''VAL_DATA_DIR/
├── app_archivos/ID_ARCHIVO     # contenido local retenido
├── app_miniaturas/ID_ARCHIVO   # vista previa
├── secretos/integraciones.key # clave de cifrado, acceso restringido
├── uploads/                   # archivos de entrada según flujo
├── exports/                   # salidas según flujo
└── fotos/                     # rutas de compatibilidad''')+
     '<p>Tras confirmar Drive puede liberarse el original local y conservarse su miniatura. La recuperación de evidencias requiere una política propia de Drive, además del respaldo del servidor. El archivo de configuración protegido y la clave de cifrado forman parte del respaldo seguro.</p>'),
    ('drive','8. Organización de carpetas en Google Drive',arbol_drive()+
     '<p>El árbol muestra rutas posibles, no carpetas creadas de forma anticipada. <b>La preparación consulta las rutas existentes; la subida materializa únicamente la ruta utilizada.</b> Si una carga falla después de crear su ruta, puede quedar una carpeta sin contenido; no existe una garantía transaccional entre MySQL y Drive ni una limpieza automática de todas las carpetas históricas.</p>'+
     L('Cliente y marca son segmentos opcionales. También puede reutilizarse una carpeta de recepción ya identificada y validada.','Si no hay embarques definidos, la categoría queda directamente bajo la recepción. Con embarques, la evidencia común puede quedar en COMPARTIDAS; la evidencia que requiere asignación puede quedar en POR-ASIGNAR.','Las rutas de SKU pueden incluir BULTOS/Bulto…/Caja… cuando existe vínculo con una unidad logística. OTRAS-EVIDENCIAS cubre los tipos sin categoría específica.','INFORMES se ubica directamente bajo la recepción en el servicio de Google Drive API.','Cuando una imagen documenta varios destinos, se crean accesos directos al archivo. No confundir un acceso directo con una copia independiente.','Se reservan IDs antes de subir, se reutilizan en reintentos y se rechazan rutas ambiguas con carpetas duplicadas. Los enlaces se guardan con su referencia de evidencia.')+
     '<p>Ejemplo de vínculo: recepción → embarque → PNC → SKU → imagen. La evidencia identifica la condición PNC y el registro de cantidades identifica unidades/pallet/posición; el nombre de la carpeta no sustituye estos datos. No borrar carpetas vacías históricas sin contrastar referencias y accesos directos.</p>'),
    ('google','9. Autorización Google, correo y catálogo',
     '<h3>Google central</h3><p>El cliente OAuth web central se configura con su origen HTTPS y URI de retorno exactos. El flujo emplea PKCE S256 y estado de uso único. El código incluye el retorno <code>/api/auth/google/callback</code>; el valor registrado debe coincidir con la configuración efectiva. Los permisos operativos de Gmail/Drive se distinguen del acceso de usuario al aplicativo.</p>'+
     T(['Integración','Identidad y alcance'],[['Gmail','Cada remitente autoriza su propia cuenta; permisos gmail.readonly y gmail.send.'],['Drive','Cuenta operativa autorizada por ADMIN; permiso drive. El acceso de ejecutivos/clientes depende de los permisos reales de la carpeta.'],['Credenciales','Tokens cifrados con Fernet en app_config; clave externa integraciones.key. No se entregan al navegador.'],['Renovación','El backend renueva access tokens mediante refresh token. Revocación/cambio de cliente exige reconexión de la cuenta.'],['Compatibilidad','Apps Script se conserva como alternativa anterior; la vía central evita un despliegue individual por supervisor.']])+
     '<h3>Documentos y correo</h3><p>Los informes se versionan mediante huella y tipo. El usuario selecciona los adjuntos y sus nombres finales. La cola conserva la instantánea de entrega y su resultado. Un envío pendiente no es una confirmación: ante una respuesta interrumpida se consulta el estado y Enviados antes de repetir.</p>'+
     '<p>El informe al ejecutivo conserva la estructura original: PALLET/posición con identificadores limpios; el detalle de cantidades y PNC se agrega al final. El informe de auditoría puede incluir mayor desglose. Las cantidades se exportan como valores numéricos; las fotografías incluidas deben tener su vínculo verificado.</p>'+
     '<h3>Depot y maestro</h3><p>La API de catálogo/stock se utiliza si las credenciales están habilitadas; existe maestro local y caché. Los archivos CSV/XLSX sirven al flujo operativo de carga y revisión. La integración documentada no implica escritura automática de mercancía en Depot.</p>'),
    ('configuracion','10. Configuración, seguridad y sincronización',
     T(['Parámetro / elemento','Administración'],[['/etc/iv-itsanet.env','Archivo protegido del despliegue; no publicarlo ni reemplazarlo con una plantilla.'],['VAL_DATABASE_URL','Conexión del motor, host, puerto, esquema y usuario. Mantener la contraseña fuera de documentación y Git.'],['VAL_DATA_DIR','Ruta persistente para archivos y clave. Valor predeterminado en el código: data/ del repositorio.'],['VAL_DB_POOL_SIZE / VAL_DB_POOL_RECYCLE','Pool SQL: predeterminados 5 y 3600 segundos. Ajustar con medición de carga.'],['VAL_SESSION_HOURS','Sesión local: predeterminado 12 horas; revisar valor efectivo.'],['VAL_COOKIE_SECURE','Cookie segura según HTTPS/configuración; conservar el esquema correcto en el proxy.'],['DEPOT_*','URL, usuario, clave, rutas y caché; secretos gestionados en el servidor.']])+
     L('Roles de aplicación: OPERADOR, SUPERVISOR y ADMIN; las autorizaciones se validan en el servidor. ADMIN funcional no equivale a root del sistema operativo.','La credencial local se conserva como hash PBKDF2-HMAC-SHA256 con sal. La sesión utiliza token aleatorio y cookie HttpOnly / SameSite=Lax.','La clave externa de integraciones se protege con permisos restringidos. Su pérdida impide recuperar las credenciales cifradas existentes.','La actualización de vistas combina SSE por recepción con consulta alternativa de 4 segundos. El proxy debe permitir conexiones continuas.','La presencia informa quién trabaja sobre el SKU; no sustituye los controles de concurrencia e idempotencia. Preservar borradores al actualizar vistas.','La política institucional define exposición de red, accesos, retención y renovaciones. Los controles descritos no constituyen certificación normativa ni garantía de alta disponibilidad.')),
    ('mantenimiento','11. Calendario de mantenimiento',
     '<p>Las siguientes frecuencias constituyen el plan preventivo recomendado. Su ejecución debe registrarse con fecha, responsable, resultado y acciones pendientes. La programación automática y la retención se verifican en el servidor antes de considerarlas implantadas.</p>'+
     T(['Frecuencia','Actividad','Responsable funcional'],[['Diaria / inicio de jornada','Acceso, pendientes de fotos/correos, errores, catálogo y disponibilidad.','Administrador funcional / supervisor.'],['Diaria','Verificar respaldo SQL, archivos, clave y configuración; comprobar resultado e integridad.','Administrador de infraestructura.'],['Semanal','Capacidad de disco/RAM, crecimiento, colas, errores recurrentes y registros del servicio.','Infraestructura + mantenedor.'],['Mensual','Usuarios/roles, cuentas sin uso, permisos Drive, dependencias y vencimiento de certificado.','Infraestructura + mantenedor + ADMIN.'],['Trimestral','Ensayo de restauración aislada y revisión de capacidad y continuidad.','Infraestructura + mantenedor.'],['Antes y después de cada cambio','Pruebas, respaldo, revisión Git, aplicación controlada y verificación funcional.','Mantenedor + infraestructura + supervisor.']])+
     '<h3>Actualización del aplicativo</h3>'+L('Reproducir y corregir en un entorno separado; verificar cantidades, reportes, fotos y permisos afectados. No ejecutar pruebas contra producción.','Registrar commit completo y ventana del cambio. Usar scripts/actualizar_produccion.sh según su procedimiento; no reinstalar el servicio desde la plantilla servicio.sh.','El actualizador prepara dependencias antes de la parada y respalda datos/configuración; luego reinicia la aplicación y verifica respuesta.','Comprobar acceso, una operación representativa, informes y las integraciones que cambien. Conservar borradores/fotos pendientes del navegador.','Documentar resultado y recuperación prevista. Volver al código anterior no restaura la base de datos.')+
     '<p>No actualizar dependencias directamente a la última versión en producción. La evolución V2 se desarrolla aparte de la línea estable: incorporación gradual de otros clientes, revisión de claves SKU, permisos, catálogos, formatos y separación de evidencias antes de cada piloto.</p>'),
    ('continuidad','12. Respaldo, recuperación y atención de incidentes',
     T(['Componente','Contenido necesario'],[['MySQL','Recepciones, eventos, usuarios, configuración, colas, estados e informes.'],['VAL_DATA_DIR','Archivos operativos retenidos, miniaturas y datos locales persistentes.'],['Clave y configuración','integraciones.key y entorno protegido, con acceso y copia separados conforme a la política.'],['Código','Commit compatible, dependencias y configuración del servicio.'],['Google Drive','Retención, permisos y recuperación de evidencias/documentos externos.']])+
     '<p>Recomendación: respaldo diario y antes de cada cambio, con copia fuera del servidor y ensayo trimestral. La institución define retención, RPO (pérdida tolerable) y RTO (tiempo de recuperación). El respaldo previo al pase incluido en el código no acredita por sí solo un respaldo diario programado.</p>'+
     L('Registrar hora, recepción/SKU, usuario, acción, error y alcance. Preservar evidencia sin incluir credenciales.','Distinguir red/DNS, Apache, Uvicorn, MySQL y proveedor externo mediante consultas de diagnóstico.','Ante datos duplicados o cruzados, restringir la operación afectada y revisar eventos; evitar correcciones directas de SQL sin análisis.','Ante fotos pendientes, conservar el original y reintentar con la identidad registrada. Ante correo pendiente, verificar confirmación y Enviados.','Restaurar primero en un entorno aislado; validar cantidades, usuarios, archivos y lectura de evidencias. Coordinar cualquier recuperación productiva y su impacto.')),
    ('diagnostico','13. Consultas de operación y diagnóstico',
     '<p>Ejecutar en la terminal SSH del servidor por personal autorizado. Estas consultas no actualizan ni reinician servicios. Revisar los registros antes de compartirlos y retirar secretos si aparecen.</p>'+
     C('''hostname
date -Is
systemctl is-active iv-itsanet apache2 mysql
systemctl show iv-itsanet -p WorkingDirectory -p FragmentPath
sudo ss -lntp '( sport = :3002 or sport = :8443 or sport = :3306 )'
sudo apache2ctl configtest
sudo apache2ctl -S
curl --connect-timeout 5 --max-time 15 -sS -i http://127.0.0.1:3002/health
curl --connect-timeout 5 --max-time 15 -sS -i https://apps.flexnetuio.com:8443/health
sudo journalctl -u iv-itsanet --since "30 minutes ago" -n 80 --no-pager
uptime
free -h
df -h /
sudo mysql -N -e "SELECT VERSION(), @@version_comment;"''')+
     T(['Resultado','Área de revisión'],[['Falla acceso directo a 3002','Aplicación, servicio, configuración o dependencia SQL.'],['3002 responde; HTTPS no responde','Apache, certificado, proxy o conectividad.'],['Servidor responde; dispositivo no conecta','Red usuaria, DNS, confianza TLS y petición fallida en navegador.'],['Solo falla Google','OAuth, permisos, cuenta, salida de red o cuota; conservar pendientes.']])+
     '<p>Consultar la revisión instalada desde el WorkingDirectory efectivo con <code>git rev-parse HEAD</code>. El nombre del esquema y las tablas efectivas se obtienen con una sesión SQL autorizada: <code>SELECT DATABASE();</code>, <code>SHOW TABLES;</code> y <code>SHOW CREATE TABLE nombre_tabla;</code>. No publicar la URI de conexión.</p>'),
    ('diccionario','14. Diccionario técnico del modelo',
     '<p>Extraído estáticamente de <code>app/models.py</code>. Se incluyen campos, tipos declarados, claves y referencias. Los tipos omitidos en mapped_column se infieren de la anotación o de la columna referenciada. CANTIDAD = DECIMAL(14,3), PRECIO = DECIMAL(14,4), FECHA = DATETIME(3) en MySQL y JSON_MAPA = JSON. Las restricciones adicionales se incluyen por tabla.</p>'+
     ''.join(render_tabla(x) for x in tablas)),
    ('referencias','15. Referencias y conservación de la documentación',
     T(['Componente','Archivo de referencia'],[['Arranque / configuración','app/main.py · app/config.py'],['Conexión / modelo','app/db.py · app/models.py'],['Archivos / Drive','app/services/archivos.py · drive.py · google_drive_api.py'],['Clasificación y rutas','app/services/fotos_embarques.py · fotos_identidad.py'],['Autorización y correo','app/services/google_cuentas.py · google_gmail_api.py · app/routers/google_auth.py'],['Entregas / permisos','app/services/entregas.py · app/security.py · app/routers/'],['Mantenimiento','scripts/actualizar_produccion.sh · respaldo_produccion.py · estado_produccion.py'],['Infraestructura recibida','docs/infraestructura/SERVIDOR_APACHE_MYSQL_20261027.md']])+
     '<p>Actualizar este manual al cambiar el modelo, las integraciones, la infraestructura o los procedimientos. Conservar el historial documental y la referencia Git de cada liberación. El inventario técnico JSON adjunto permite contrastar tablas, campos y dependencias sin exponer datos operativos ni credenciales.</p>')]


def render_tabla(x):
    filas=[]
    for f in x['campos']:
        opts=f['opciones']; claves=[]
        if opts.get('primary_key')=='True': claves.append('PK')
        if opts.get('unique')=='True': claves.append('UNIQUE')
        if f['referencias']: claves.append('FK → '+', '.join(f['referencias']))
        if f['ondelete']: claves.append('ON DELETE '+', '.join(f['ondelete']))
        if opts.get('index')=='True': claves.append('Índice')
        filas.append([E(f['nombre']),'<code>'+E(f['tipoSQLResuelto'])+'</code><br><small>'+E(f['anotacion'])+'</small>',E('; '.join(claves) or '—')])
    return '<article class="entidad"><h3>'+E(x['tabla'])+'</h3><p>'+E(x['uso'])+'</p>'+T(['Campo','Tipo / anotación','Claves / referencia'],filas)+(''+C('\n'.join(x['restricciones'])) if x['restricciones'] else '')+'</article>'


CSS = B.CSS + '''
.documento .lead{font-size:20px}.entidad{margin:28px 0}.entidad h3{color:#176b79;border-bottom:2px solid #c7dfe6;padding-bottom:8px}.entidad small{font-size:11px}.documento code{overflow-wrap:anywhere}.documento table{table-layout:fixed}.documento td,.documento th{overflow-wrap:anywhere}.documento h2{line-height:1.25}.documento pre{white-space:pre-wrap}.top .logo{object-fit:contain}.slide .tabla{overflow:auto}.documento header small{color:#bbd7e6}.indice-pdf{display:none}
@media print{@page{size:A4;margin:16mm 14mm 18mm}.indice-pdf{display:block}.indice-pdf a{display:block;padding:3mm 0;font-size:11pt;border-bottom:1px solid #dce5ef}.documento section{break-before:page}.documento .entidad{break-before:auto}.documento .entidad h3,.documento .entidad>p{break-after:avoid}.documento table{font-size:8.2pt}.documento td,.documento th{padding:2mm}.documento pre{font-size:8pt;line-height:1.5}.documento .arquitectura{grid-template-columns:repeat(4,minmax(0,1fr))}.documento .nodo strong{font-size:11pt}.documento .nodo small{font-size:8pt}.documento p,.documento li{font-size:10pt}.documento header{padding:0 0 6mm}.documento header small{color:#526781}.documento #diccionario{break-before:page}.documento .entidad p{font-size:9pt}.documento .entidad{margin:5mm 0}.slide .tabla{overflow:visible}}
'''

JS_DOC = '''
const q=document.querySelector('#buscar'),sec=[...document.querySelectorAll('.contenido section')];
function buscar(){let t=q.value.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();sec.forEach(s=>{s.hidden=!s.textContent.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().includes(t);});}
q.oninput=buscar;document.querySelector('#limpiar').onclick=()=>{q.value='';buscar();};
document.querySelector('#imprimir').onclick=()=>window.print();
document.querySelector('#descargar').onclick=()=>{const d=document.documentElement.cloneNode(true);d.querySelectorAll('.contenido section').forEach(s=>s.hidden=false);d.querySelector('#buscar').setAttribute('value','');const u=URL.createObjectURL(new Blob(['<!doctype html>\\n'+d.outerHTML],{type:'text/html;charset=utf-8'}));const a=document.createElement('a');a.href=u;a.download='Manual-tecnico-ITSANET-20261028.html';a.click();setTimeout(()=>URL.revokeObjectURL(u),3000);};
'''


def manual(inv, tablas):
    ss=secciones(inv, tablas)
    indice=''.join('<a href="#'+i+'">'+t+'</a>' for i,t,_ in ss)
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IV ITSANET · Manual técnico</title><style>'+CSS+'</style></head><body class="documento"><header><small>IV ITSANET · Documentación técnica · 20261028</small><h1>Manual técnico</h1><p class="sub">Ingreso &amp; Validación Itsanet · Arquitectura, datos, integraciones y mantenimiento</p><div class="herramientas"><button id="imprimir">Imprimir / PDF</button><button id="descargar">Descargar HTML</button></div></header><main><nav><b>Contenido</b><input id="buscar" aria-label="Buscar en el manual" placeholder="Buscar tabla o componente"><button id="limpiar">Ver todo</button>'+indice+'</nav><div class="contenido"><div class="indice-pdf"><h2>Contenido</h2>'+indice+'</div>'+''.join('<section id="'+i+'"><h2>'+t+'</h2>'+c+'</section>' for i,t,c in ss)+'</div></main><script>'+JS_DOC+'</script></body></html>'


def slides():
    K=B.caja
    return [
    ('IV ITSANET','Arquitectura y operación técnica', '<h1>Plataforma de validación física</h1><p class="grande">Recepciones, conteos, evidencias e informes desde PC y handheld.</p><div class="grid">'+K('Python + FastAPI','Reglas, permisos, API y procesos.')+K('Apache + MySQL','Publicación corporativa y persistencia transaccional.')+K('Google central','Evidencias en Drive y entrega con Gmail.')+'</div><p>'+FECHA+' · Código de referencia v69.</p>'),
    ('Arquitectura','Comunicación entre las capas',B.arquitectura()+'<div class="grid dos">'+K('Persistencia','SQLAlchemy + PyMySQL; datos y estados en MySQL.')+K('Servicios externos','Google Drive / Gmail y consulta Depot por HTTPS.')+'</div><div class="banda">https://apps.flexnetuio.com:8443/app/</div>'),
    ('Tecnologías y código','Interfaz web y backend central',T(['Componente','Implementación'],[['Interfaz','HTML, CSS y JavaScript modular; cámara, escáner y galería.'],['Aplicación','Python · FastAPI · Pydantic · Uvicorn ASGI.'],['Datos','SQLAlchemy · PyMySQL · MySQL.'],['Documentos / imágenes','SheetJS · openpyxl · Pillow · jsPDF · JsBarcode / ZXing.'],['Mantenimiento','Git · systemd · scripts de respaldo y actualización.']])+'<div class="banda">app/ → backend · firebase/public/ → interfaz · scripts/ → operación · tests/ → verificación aislada.</div>'),
    ('Infraestructura corporativa','Inventario observado del servidor',T(['Elemento','Valor'],[['Host','apps · IP local 192.168.4.94'],['Publicación','Apache2 · HTTPS 8443'],['Aplicación','iv-itsanet.service · Uvicorn 3002'],['Motor local','MySQL 8.0.46 · 127.0.0.1:3306'],['Capacidad puntual','4 CPU lógicas · 11 GiB RAM · 50 GB disponibles en raíz.'],['Convivencia','Apache 80/443 y Data Sync en Docker 127.0.0.1:8080.']])+'<p class="mini">Inventario recibido el 27/10/2026. Versión local del motor confirmada; esquema y revisión instalada se cotejan en configuración de operación.</p>'),
    ('Modelo relacional','30 tablas declaradas en el código', '<div class="grid">'+K('Operación','app_recepciones, app_lineas, app_skus y app_eventos.')+K('Evidencia','app_archivos, app_evidencias, asociaciones y app_copias_drive.')+K('Gestión','Usuarios/sesiones, informes, entregas, impresión y auditoría.')+'</div>'+T(['Relación','Propósito'],[['Recepción → línea → SKU → evento','Packing original, cantidades y registro de cada operación.'],['Archivo → evidencia → copia','Autoría, clasificación, enlace y estado de transferencia.'],['Recepción → informe → entrega','Documento versionado y resultado del envío.']])+'<p class="mini">Las tablas iniciales se conservan para compatibilidad. El manual incluye el diccionario de campos y claves.</p>'),
    ('Integridad y coordinación','Controles del registro operativo','<div class="grid">'+K('Cantidades','DECIMAL en SQL; cero explícito, observación y validaciones de registro.')+K('Reintentos','Identidad estable de operación; correcciones con motivo y compensación.')+K('Trabajo simultáneo','Presencia por SKU, control de versiones y refresco SSE con alternativa de 4 s.')+'</div><div class="banda">Trazabilidad: recepción → embarque → SKU → cantidad → pallet/posición → condición → evidencia → informe.</div><p>PNC registra las unidades y evidencia que justifican la condición de producto no conforme.</p>'),
    ('Evidencias multimedia','Guardar y confirmar son etapas distintas','<div class="flujo">'+''.join('<div class="paso"><b>'+n+'</b><span>'+t+'</span></div>' for n,t in [('01','Capturar y clasificar'),('02','Guardar en servidor'),('03','Programar copia SQL'),('04','Subir y comprobar Drive'),('05','Conservar enlace confirmado')])+'</div>'+T(['Control','Resultado'],[['ID reservado y checksum','Reintento controlado y comprobación de contenido.'],['Pendientes / revisión','Errores e intentos visibles; se conserva el trabajo pendiente.'],['SQL + archivos + Drive','Metadatos, miniaturas y originales según etapa de retención.']])+'<p class="mini">Una miniatura no acredita la copia. La retención de Drive forma parte de la continuidad.</p>'),
    ('Carpetas y vínculos','Rutas creadas al utilizarse',C('RAIZ / CLIENTE / MARCA / RECEPCION\n├── INFORMES\n└── EMBARQUE\n    ├── PRE-INGRESO · PANORAMICAS · FOTOS-FINALES\n    ├── BULTOS / Bulto… / Caja…\n    └── PRODUCTOS · PNC · SOBRANTES · FALTANTES / SKU')+'<div class="banda">Preparar consulta; subir crea la ruta utilizada. Una evidencia con varios destinos utiliza accesos directos.</div><p class="mini">Segmentos opcionales según contexto; COMPARTIDAS/POR-ASIGNAR cuando corresponde. Una carga fallida puede dejar una ruta vacía; no borrar carpetas históricas sin revisar referencias.</p>'),
    ('Google y entrega de informes','Autorización central y estados recuperables','<div class="grid">'+K('OAuth','PKCE S256, cuenta autorizada y renovación de tokens en servidor.')+K('Drive','Cuenta operativa; evidencia copiada y vínculo verificado.')+K('Gmail','Remitente propio autorizado; selección y nombre final por adjunto.')+'</div><div class="banda">Tokens cifrados en SQL · clave externa protegida · pendiente no equivale a enviado.</div><p>Informe ejecutivo con identificadores limpios y detalle final de unidades/PNC. Depot se consulta según habilitación y se conservan archivos del flujo operativo.</p>'),
    ('Seguridad y administración','Permisos y secretos por capa','<div class="grid">'+K('Aplicación','Roles OPERADOR, SUPERVISOR y ADMIN; permisos en servidor.')+K('Identidad','Credencial con hash y sal; sesión con cookie HttpOnly.')+K('Infraestructura','HTTPS, servicio systemd, configuración protegida y privilegios SQL.')+'</div>'+T(['Activo','Protección / administración'],[['/etc/iv-itsanet.env','Conexiones privadas; fuera del repositorio y documentos.'],['integraciones.key','Copia protegida necesaria para descifrar tokens.'],['Servidor compartido','Conservar virtual hosts, servicios y datos de otras aplicaciones.']])+'<p class="mini">Los controles descritos requieren políticas de acceso, retención y continuidad de la organización.</p>'),
    ('Mantenimiento y continuidad','Calendario preventivo y cambios controlados',T(['Frecuencia recomendada','Actividad'],[['Diaria','Acceso, catálogo, pendientes, errores y respaldo.'],['Semanal','Capacidad, crecimiento y fallas recurrentes.'],['Mensual','Accesos, permisos Drive, TLS y dependencias.'],['Trimestral','Restauración aislada y continuidad.'],['Cada cambio','Pruebas, commit, respaldo, ventana y verificación.']])+'<div class="banda">Respaldar SQL + archivos + configuración + clave; proteger también Drive. Retención, RPO y RTO se fijan en la política de continuidad.</div>'),
    ('Evolución y conservación','Línea estable y desarrollo V2','<div class="grid">'+K('Mantener','Correcciones verificadas, versiones identificadas y documentación vigente.')+K('Recuperar','Respaldo comprobable y ensayo aislado; retorno de código distinto de restauración SQL.')+K('Ampliar','V2 para otros clientes de bodega con permisos, catálogos y reglas propios.')+'</div><div class="banda">La ampliación requiere validar identidad de SKU, separación de datos, evidencias, destinatarios e informes antes de cada piloto.</div><p>Referencia técnica: manual, diccionario de 30 tablas e inventario JSON.</p>')]


def presentacion(logo):
    ss=slides()
    cuerpo=''.join('<section class="slide '+('activa' if i==0 else '')+'" data-titulo="'+E(t)+'" aria-hidden="'+str(i!=0).lower()+'"><div class="eyebrow">IV ITSANET · '+str(i+1).zfill(2)+' / '+str(len(ss))+'</div><h2>'+t+'</h2><p class="sub">'+s+'</p>'+c+'<div class="pie">Arquitectura y mantenimiento · '+FECHA+' · '+str(i+1)+' / '+str(len(ss))+'</div></section>' for i,(t,s,c) in enumerate(ss))
    js=B.JS_PRESENTACION
    js=js.replace('Presentacion-tecnica-ITSANET-20261027.html','Presentacion-tecnica-ITSANET-20261028.html')
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IV ITSANET · Arquitectura técnica</title><style>'+CSS+'@page{size:A4 landscape;margin:10mm}</style></head><body><header class="top"><img class="logo" alt="ITSANET" src="'+logo+'"><small>Arquitectura y mantenimiento</small><div class="herramientas"><button id="notas" hidden>Notas</button><button id="pantalla">Pantalla completa</button><button id="imprimir">Imprimir / PDF</button><button id="descargar">Descargar HTML</button></div></header><main class="slides">'+cuerpo+'</main><nav class="navslides" aria-label="Diapositivas"><button id="anterior">← Anterior</button><progress id="progreso" max="'+str(len(ss))+'" value="1" aria-label="Avance"></progress><output id="contador">1 / '+str(len(ss))+'</output><button id="siguiente">Siguiente →</button><div class="puntos">'+''.join('<button data-slide="'+str(i)+'" aria-label="Diapositiva '+str(i+1)+'">'+str(i+1)+'</button>' for i in range(len(ss)))+'</div></nav><p id="estado" class="noprint mini" role="status"></p><script>'+js+'</script></body></html>'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--salida',type=Path,required=True);a=p.parse_args();a.salida.mkdir(parents=True,exist_ok=True)
    inv=B.inventario();inv.update(fecha='2026-10-28',tablasDetalle=diccionario(),infraestructuraFuente='Terminal compartida por el responsable el 27/10/2026',mysqlLocal='8.0.46-0ubuntu0.24.04.4')
    (a.salida/'Manual-tecnico-ITSANET-20261028.html').write_text(manual(inv,inv['tablasDetalle']))
    logo='data:image/png;base64,'+base64.b64encode((ROOT/'firebase/public/logo-itsa.png').read_bytes()).decode()
    (a.salida/'Presentacion-tecnica-ITSANET-20261028.html').write_text(presentacion(logo))
    (a.salida/'Inventario-tecnico-ITSANET-20261028.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2))
    print(json.dumps({'salida':str(a.salida),'tablas':len(inv['tablasDetalle']),'campos':sum(len(x['campos']) for x in inv['tablasDetalle']),'diapositivas':len(slides())}))


if __name__=='__main__': main()
