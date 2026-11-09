"""Contenido técnico de entrega, sin notas internas de liberación.

Describe el modelo del repositorio; no consulta ni altera la base corporativa.
"""
from html import escape as E
import re


def diccionario_detallado(M, tablas):
    articulos = []
    for tabla in tablas:
        filas = []
        for campo in tabla['campos']:
            opciones = campo['opciones']
            pk = opciones.get('primary_key') == 'True'
            nullable = opciones.get('nullable', str(not pk and 'None' in campo['anotacion']))
            claves = ['PK'] if pk else []
            if campo['referencias']:
                claves.append('FK → ' + ', '.join(campo['referencias']))
            if campo['ondelete']:
                claves.append('ON DELETE ' + ', '.join(campo['ondelete']))
            if opciones.get('unique') == 'True':
                claves.append('UNIQUE')
            if opciones.get('index') == 'True':
                claves.append('Índice')
            filas.append([
                '<code>' + E(campo['nombre']) + '</code>',
                E(campo['tipoSQLResuelto']),
                'Sí' if nullable == 'True' else 'No',
                E(opciones.get('default', '—')),
                E('; '.join(claves) or '—'),
            ])
        articulos.append('<article class="entidad"><h3>' + E(tabla['tabla']) + '</h3><p>' +
                         E(tabla['uso']) + '</p>' +
                         M.T(['Campo', 'Tipo declarado', 'NULL', 'Valor inicial ORM', 'Claves / índice'], filas) +
                         (M.C('\n'.join(tabla['restricciones'])) if tabla['restricciones'] else '') + '</article>')
    return ('<p>Diccionario obtenido de <code>app/models.py</code>. NULL se deriva de la anotación '
            'Mapped y de nullable cuando está declarado. Los valores iniciales son del ORM: '
            'no implican DEFAULT en el DDL de MySQL. Los tipos CANTIDAD, PRECIO, FECHA y JSON_MAPA '
            'representan DECIMAL(14,3), DECIMAL(14,4), DATETIME(3) y JSON en MySQL. '
            'Las claves compuestas, restricciones e índices adicionales figuran al pie de cada tabla.</p>' +
            ''.join(articulos))


def relaciones(M, tablas):
    filas = []
    for tabla in tablas:
        pk = [f['nombre'] for f in tabla['campos'] if f['opciones'].get('primary_key') == 'True']
        for campo in tabla['campos']:
            for referencia in campo['referencias']:
                unico = pk == [campo['nombre']] or campo['opciones'].get('unique') == 'True'
                filas.append([
                    '<code>' + E(referencia) + '</code>',
                    '<code>' + E(tabla['tabla'] + '.' + campo['nombre']) + '</code>',
                    '1 → 0..1' if unico else '1 → 0..N',
                    E(', '.join(campo['ondelete']) or 'Sin cascada SQL declarada'),
                ])
    return ('<p>Las relaciones siguientes son claves externas declaradas. La cardinalidad se expresa '
            'desde el registro padre hacia sus hijos. Una FK con NULL permite que el hijo no tenga padre asignado. '
            'CASCADE propaga la eliminación física; la anulación de un conteo utiliza un evento compensatorio.</p>' +
            M.T(['Clave referenciada', 'Campo dependiente', 'Padre → hijos', 'ON DELETE'], filas) +
            '<h3>Asociaciones resueltas por la aplicación</h3>' +
            M.T(['Asociación', 'Regla de enlace'], [
                ['Líneas, SKU y eventos', 'recepcion + sku; origen identifica el packing list dentro de la recepción. Las columnas SKU de estos registros no son FK al maestro global.'],
                ['Anulación de eventos', 'app_eventos.anula_a identifica app_eventos.id; el servicio verifica que el evento pertenezca a la operación y no haya sido anulado. No existe FK SQL en este campo.'],
                ['Autoría de registros', 'app_eventos.usuario y otras firmas textuales guardan la identidad operativa. No son FK a operadores; se conserva la firma histórica.'],
                ['Relaciones de códigos', 'producto_relaciones usa PK compuesta (cliente, codigo), un SKU canónico y cantidad_referencia. El SKU es un enlace lógico sin FK a productos.'],
                ['Archivo con varios SKU', 'app_archivo_skus tiene PK (archivo_id, sku); archivo_id es FK y sku es enlace contextual. No duplica el contenido binario.'],
                ['Huellas y recepción', 'app_huellas.recepcion es una referencia lógica indexada. No es FK SQL.'],
                ['Información JSON', 'Mapas de pallet/origen, parámetros y datos de colas se validan en los servicios; no tienen restricciones referenciales internas del motor.'],
            ]) + '<h3>Relaciones representativas</h3>' + M.C('''app_recepciones.codigo  1 ─── N app_lineas.recepcion
app_recepciones.codigo  1 ─── N app_skus.recepcion
app_skus.id             1 ─── 0..1 app_calidad_skus.sku_id
app_recepciones.codigo  1 ─── N app_eventos.recepcion
app_archivos.id         1 ─── N app_evidencias.archivo_id
app_archivos.id         1 ─── 0..1 app_copias_drive.archivo_id
app_unidades_logisticas.id 1 ─── N app_unidades_logisticas.padre_id
operadores.id           1 ─── N sesiones.operador_id

Relación funcional de conteo: recepción + SKU + origen + pallet
Relación funcional de escaneo: cliente + código leído → SKU canónico'''))


def secciones(M, inv, tablas, continuidad, publicacion):
    """Compone el manual de entrega con secciones verificables y sin historial de cambios."""
    partes = {k: (t, c) for k, t, c in M.secciones(inv, tablas)}
    partes['alcance'] = ('Identificación y alcance',
        '<p class="lead">IV ITSANET (Ingreso &amp; Validación Itsanet) centraliza el ingreso '
        'y la validación física de mercadería, el registro de novedades y evidencias, '
        'la trazabilidad por ítem y la preparación de informes y correos.</p>' +
        M.T(['Elemento', 'Descripción'], [
            ['Documento', 'Manual técnico de arquitectura, datos, integraciones y mantenimiento.'],
            ['Fecha documental', '9 de noviembre de 2026 · America/Guayaquil.'],
            ['Acceso al aplicativo', 'https://apps.flexnetuio.com:8443/app/'],
            ['Arquitectura corporativa', 'Apache → Uvicorn / FastAPI → SQLAlchemy / PyMySQL → MySQL.'],
            ['Fuentes', 'Código fuente, modelos de datos, configuración de referencia y evidencia de terminal del servidor del 27/10/2026.'],
        ]) + '<p>El diccionario corresponde al modelo definido en el código fuente. '
        'Los datos de infraestructura conservan la fecha de su observación. '
        'El documento no incluye contraseñas, tokens, contenidos de las tablas ni datos personales de usuarios.</p>')
    t, c = partes['datos']
    partes['datos'] = (t, c.replace('<b>30 tablas</b>', f'<b>{len(tablas)} tablas</b>'))
    t, c = partes['tecnologia']
    partes['tecnologia'] = (t, c.replace('Las versiones anteriores son dependencias declaradas en el repositorio;',
                                       'Los números de versión de componentes corresponden a requirements.txt;'))
    partes['diccionario'] = ('Diccionario de campos, claves e índices', diccionario_detallado(M, tablas))
    partes['relaciones'] = ('Relaciones físicas y asociaciones funcionales', relaciones(M, tablas))
    partes['codigo'] = ('Procesamiento del código y transacciones',
        '<p>La interfaz es una aplicación web en HTML, CSS y JavaScript modular. '
        'El directorio firebase/public contiene sus recursos, aunque el flujo corporativo '
        'de autenticación, conteo y persistencia se atiende desde el backend Python.</p>' +
        M.T(['Componente del código', 'Uso en la operación'], [
            ['app/main.py', 'Construye FastAPI, registra rutas, sirve /app/ e inicia los trabajadores de entregas y tareas operativas.'],
            ['app/routers/app_api.py', 'Recibe consultas y registros del navegador; aplica autenticación y permisos antes de llamar a los servicios.'],
            ['app/services/app_modelo.py', 'Importa el packing, registra eventos, actualiza proyecciones, anula con motivo y recalcula SKU.'],
            ['app/services/lecturas.py', 'Resuelve códigos de catálogo por cliente/recepción y prepara lecturas para el dispositivo.'],
            ['app/db.py y app/models.py', 'Configuran motor/sesiones, tipos, transacciones, tablas, claves y restricciones.'],
            ['app/services/archivos.py', 'Guarda bytes y miniaturas de forma durable y vincula metadatos y hash al archivo.'],
            ['app/services/drive.py y google_drive_api.py', 'Resuelven carpetas, identidad remota, transferencia, verificación y recuperación.'],
            ['app/services/entregas.py y google_gmail_api.py', 'Preparan la instantánea de entrega y gestionan la cola de envío y su resultado.'],
            ['firebase/public/js/conteos-pendientes.js', 'Respalda el trabajo local y coordina reintentos con identidad estable.'],
        ]) + '<h3>Secuencia de un conteo</h3>' + M.C('''Navegador: código leído → SKU del cliente → cantidad y ubicación
    ↓ persistencia previa del trabajo en IndexedDB
Petición autenticada con idempotencyKey
    ↓ comprobación de identidad y permisos
registrar_conteo(): bloqueo de recepción y estado del SKU
    ↓ comprobación de un evento ya registrado con la misma clave
Validación de cantidad, pallet, origen, PNC y estado de recepción
    ↓ inserción de app_eventos y actualización de app_skus / calidad
COMMIT de la transacción
    ↓ respuesta del servidor y notificación de cambios
Navegador: confirma el trabajo local y actualiza la vista''') +
        '<p>El identificador de evento es PK de app_eventos. Repetir la misma petición '
        'no incrementa otra vez el total; un identificador usado por otra operación se rechaza. '
        'Los bloqueos SELECT FOR UPDATE del modelo MySQL protegen la lectura y actualización '
        'de recepción y SKU. La proyección permite consultar los totales sin sumar todo el historial '
        'en cada escaneo. Una anulación registra su referencia y compensación; '
        'recalcular_sku reconstruye el estado a partir del libro de eventos.</p>' +
        '<h3>Creación y evolución de tablas</h3><p>init_db() registra los modelos y crea las tablas ausentes. '
        'En MySQL, crear_tablas_compatibles() consulta los tipos y collations de las claves existentes '
        'para crear referencias compatibles. create_all no modifica automáticamente las columnas de '
        'una tabla ya existente. Las alteraciones explícitas se ejecutan desde funciones y scripts '
        'de mantenimiento identificados y con respaldo previo.</p>')
    partes['catalogos'] = ('Catálogo, códigos de barras, bultos e informes',
        M.T(['Proceso', 'Estructura y regla técnica'], [
            ['Importación de relaciones', 'La hoja RL_CODIGOS se valida por completo y se persiste en una transacción. La PK (cliente, codigo) separa las equivalencias; los conflictos revierten la importación.'],
            ['EAN / UPC / SKU', 'La lectura usa el cliente de la recepción. Las equivalencias UPC-A/EAN-13 requieren dígito válido; los códigos ambiguos se rechazan. Se conserva el SKU canónico para conteo, búsqueda y etiqueta.'],
            ['Unidades por empaque', 'cantidad_referencia conserva las unidades del empaque/código. Su aplicación al conteo requiere una acción explícita del operario; escanear no multiplica automáticamente.'],
            ['Bultos y subbultos', 'app_unidades_logisticas representa la jerarquía con padre_id. La unicidad por recepción/tipo/número y los controles de ocupación e impresión protegen los cambios del total.'],
            ['Impresión', 'Etiquetas de bulto completo, rangos o unidad/subbulto registrado. El código CODE128 mantiene separación respecto del texto y los demás campos; PDF/ZPL según la salida elegida.'],
            ['Filtros operativos', 'Se basan en el estado y verificación del SKU. Un cero confirmado es un registro revisado con faltante. Los filtros de novedades y avance utilizan esos mismos datos.'],
            ['Informe al ejecutivo', 'Conserva el orden y las columnas originales del packing. Los identificadores de pallet/posición se mantienen limpios y el detalle de unidades/PNC se agrega al final.'],
            ['Auditoría y agrupación de correo', 'El detalle conserva cantidades, pallet, autor y evidencias. El supervisor elige agrupación por packing list, embarque o recepción consolidada y confirma antes de continuar.'],
        ]))
    partes['eficiencia'] = ('Eficiencia de almacenamiento y actualización de vistas',
        M.T(['Mecanismo', 'Implementación y efecto'], [
            ['Proyección por SKU', 'app_skus conserva totales y distribuciones recalculables desde eventos. Evita recorrer el historial completo en cada consulta del operario.'],
            ['Índices y unicidad', 'Recepción/SKU, recepción/origen/línea, fechas y claves de cola tienen restricciones e índices declarados. El diccionario identifica cada uno.'],
            ['Actualización de vistas', 'SSE por recepción notifica cambios; la consulta alternativa mantiene la actualización cuando SSE no está disponible. La interfaz conserva los borradores de captura.'],
            ['Galería de evidencias', 'Consulta por páginas de 24 imágenes y miniaturas; limita la descarga de originales y el trabajo de renderización inicial.'],
            ['Miniaturas locales', 'Pillow genera previsualizaciones de hasta 960 × 960 píxeles, JPEG calidad 76. La caché de miniaturas se limita a 20 MiB; no es el límite de todos los archivos del aplicativo.'],
            ['Originales confirmados', 'Después de confirmar el guardado remoto, el flujo puede liberar el original local y mantener su miniatura. Una foto sin confirmación no se libera mediante ese criterio.'],
            ['Identidad de contenido', 'SHA-256 y la unicidad (recepción, tipo, sha256) reconocen contenido repetido. Los vínculos a varios SKU reutilizan el archivo.'],
            ['Pool SQL', 'pre_ping comprueba conexiones del pool y pool_recycle renueva las ociosas. El tamaño se configura conforme a la carga y límites de MySQL.'],
        ]) + '<p>Estos mecanismos reducen consultas repetidas, transferencia de imágenes y retención local de originales. '
        'La capacidad de usuarios simultáneos y los tiempos de respuesta se establecen mediante mediciones '
        'de carga del entorno de operación; no se deducen únicamente del diseño o de pruebas funcionales. '
        'Las mediciones de rendimiento se presentan por separado de este manual.</p>')
    partes['validacion'] = ('Verificación funcional y criterios de aceptación',
        '<p>La revisión técnica utiliza pruebas automatizadas del repositorio en una base temporal '
        'aislada y comprobaciones de interfaz en navegador. Verifica reglas e integridad sin registrar '
        'operaciones en la base corporativa ni enviar correos reales.</p>' +
        M.T(['Área', 'Criterio verificado'], [
            ['Acceso y roles', 'El servidor rechaza operaciones sin sesión o sin el permiso correspondiente.'],
            ['Recepción y packing', 'Conservación de líneas, orígenes y cantidades; control de cargas repetidas.'],
            ['Conteo', 'Cero confirmado, límites de cantidad, reparto por origen, PNC y corrección trazable.'],
            ['Reintento', 'La misma clave no duplica el evento ni la cantidad; se rechaza el uso de una clave ajena.'],
            ['Códigos', 'Resolución por cliente, unidades por empaque y tratamiento de equivalencias y conflictos.'],
            ['Bultos y etiquetas', 'Edición controlada, rangos y subbultos sin crear unidades solo para imprimir.'],
            ['Evidencias y Google', 'Persistencia, identidad de destino, estados de copia y tratamiento de errores mediante respuestas de servicio controladas.'],
            ['Desconexión', 'Conservación de la cola local, fotos y mismo identificador al recuperar conexión; confirmación tras respuesta del servidor.'],
            ['Documentación', '38 pasos de usuario, integridad de archivos, carga de imágenes y equivalencia HTML/PDF de la misma generación.'],
        ]) + '<p>Los resultados funcionales describen el entorno ensayado. Los controles de operación '
        'complementan esta validación con acceso HTTPS, conexión SQL, permisos externos, colas y '
        'consulta de evidencias. /health informa que la aplicación responde; por sí solo '
        'no comprueba MySQL, Google, capacidad ni tiempos de respuesta.</p>')
    partes['continuidad-dispositivo'] = ('Continuidad del trabajo en el dispositivo', continuidad)
    partes['publicacion-manuales'] = ('Publicación y mantenimiento de manuales', publicacion)
    orden = ['alcance', 'arquitectura', 'tecnologia', 'infraestructura', 'codigo', 'datos',
             'relaciones', 'tablas', 'catalogos', 'evidencias', 'drive', 'google', 'configuracion',
             'continuidad-dispositivo', 'eficiencia', 'validacion', 'mantenimiento', 'continuidad',
             'diagnostico', 'diccionario', 'publicacion-manuales', 'referencias']
    return [(k, str(i) + '. ' + re.sub(r'^\d+\.\s*', '', partes[k][0]), partes[k][1])
            for i, k in enumerate(orden, 1)]
