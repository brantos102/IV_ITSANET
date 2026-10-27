"""Expediente documental de entrega, mantenimiento y evolución V2.

Genera HTML estático. No importa la app ni accede a SQL, Google o secretos.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import re

RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('documentacion_tecnica', RAIZ/'scripts/generar_presentacion_tecnica_20261027.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
E, tabla, lista, codigo = base.E, base.tabla, base.lista, base.codigo
ID = 'ITSANET-TI-ENT-20261027'


def secciones_mantenimiento():
    return [
      ('gobierno','Gobierno y distribución de responsabilidades',
       '<p>El mantenimiento se organizará en tres frentes: administración funcional del aplicativo, operación de infraestructura por TI y mantenimiento del código por el responsable técnico designado. Reingeniería valida los cambios del proceso. Las personas, suplencias, horarios y tiempos de atención se formalizan en el acta.</p>'+
       tabla(['Frente','Responsable por rol','Alcance'],[
        ['Administración funcional','ADMIN del aplicativo y supervisor','Usuarios/roles autorizados, catálogo, seguimiento de pendientes, revisión de evidencia e informes y auditoría diaria.'],
        ['Infraestructura y continuidad','TI','Servidor, Apache/TLS, MySQL, systemd, accesos, capacidad, respaldos y recuperación.'],
        ['Código y correcciones','Ingeniero / mantenedor designado','Diagnóstico, corrección, pruebas, documentación, control de versiones y asistencia al pase.'],
        ['Proceso y cambios funcionales','Reingeniería + Operaciones','Requisitos, reglas por cliente, validación del flujo e indicadores.'],
        ['Aprobación del cambio','Responsable que designe la institución','Autorizar el pase a producción con evidencia y ventana acordada.']])+
       '<p>ADMIN del aplicativo no equivale a administrador root del servidor. Las claves y permisos técnicos se transfieren por el canal institucional seguro; no se incluyen en el expediente ni en el acta descargable.</p>'+
       '<div class="banda">Este es el esquema de mantenimiento propuesto para la entrega. No acredita un contrato de soporte 24×7, un SLA aprobado ni la ejecución de respaldos programados que todavía no se hayan verificado.</div>'),
      ('rutina','Rutinas preventivas y evidencia de ejecución',
       tabla(['Frecuencia propuesta','Actividad','Responsable','Evidencia a conservar'],[
        ['Diaria / inicio de jornada','Verificar acceso, pendientes de Drive/correo, errores del monitor y actualización del catálogo.','ADMIN + supervisor','Revisión registrada, pendientes asignados y cierre de incidencias.'],
        ['Diaria, según horario que apruebe TI','Comprobar respaldo SQL/archivos/configuración y disponibilidad del servicio.','TI','Log de respaldo, fecha, tamaño, integridad y ubicación protegida.'],
        ['Semanal','Revisar espacio, crecimiento, errores recurrentes, colas y cuentas operativas.','TI + ADMIN','Registro de capacidad y acciones de corrección.'],
        ['Mensual','Revisar usuarios/roles, cuentas sin uso, permisos de Drive, vencimiento de TLS y dependencias del código.','TI + mantenedor + ADMIN','Revisión de accesos, próximos vencimientos y plan de cambios.'],
        ['Trimestral o frecuencia institucional','Ensayar restauración en entorno aislado y revisar continuidad/capacidad.','TI + mantenedor','Resultado de recuperación, tiempos y consistencia de archivos/enlaces.'],
        ['Antes y después de cada pase','Respaldo, pruebas, revisión aprobada, verificación de servicio y operación.','TI + mantenedor + supervisor','Ticket de cambio, SHA, respaldo, pruebas y comprobación posterior.']])+
       '<p>TI debe aprobar e implementar el calendario efectivo. En el código está documentado el respaldo previo al pase; este documento no demuestra que exista ya un respaldo diario automático.</p>'+
       '<p>Los certificados y autorizaciones OAuth se revisan antes del vencimiento. No se rotan claves de integraciones sin un procedimiento que conserve la capacidad de descifrar las credenciales existentes.</p>'),
      ('correctivo','Mantenimiento correctivo e incidentes',
       '<p>Todo incidente debe registrar fecha/hora, recepción/SKU cuando corresponda, usuario/rol, acción, resultado esperado, mensaje de error, estado de imágenes/correo y referencia del proceso. Adjuntar evidencia técnica sin contraseñas, tokens ni contenido innecesario de clientes.</p>'+
       tabla(['Prioridad propuesta','Ejemplo','Tratamiento inicial'],[
        ['Crítica','Indicio de pérdida, cruce de información, cantidades duplicadas o indisponibilidad general.','Restringir la operación afectada, preservar evidencia y escalar a TI/mantenedor. No reparar con SQL manual ni reiniciar repetidamente sin diagnóstico.'],
        ['Alta','Falla de fotos, generación de informe o correo que bloquea una recepción.','Revisar monitor, permisos, cuenta y conectividad. Conservar originales y registro del envío.'],
        ['Normal','Problema de presentación, consulta o mejora que no altera la integridad.','Registrar, reproducir en pruebas, priorizar y planificar una corrección.']])+
       '<h3>Procedimiento</h3>'+lista('Abrir el incidente y delimitar el impacto. Consultar estado de servicio, procesos y eventos.','Reproducir con datos sintéticos en el entorno de pruebas; distinguir error de aplicación, configuración, red o servicio externo.','Definir corrección y caso de verificación. Revisar impacto sobre datos, formatos y compatibilidad.','Aplicar por cambio controlado; comprobar cantidades, evidencias e informes del alcance afectado.','Cerrar con causa, cambio aplicado, evidencia y medidas para evitar repetición.')+
       '<p>Si Gmail no confirmó un envío, revisar Enviados y la referencia de entrega antes de reintentarlo. Una fotografía pendiente debe recuperarse o reintentarse con su identificador, sin generar duplicados ni descartar el original.</p>'+
       '<p>Los tiempos de respuesta y solución los fija TI según criticidad, horario y recursos disponibles; no se asignan minutos u horas contractuales en esta entrega.</p>'),
      ('cambios','Actualizaciones de código y control de cambios',
       lista('Mantener una referencia Git del código aprobado y registrar el commit completo de cada pase.','Preparar y probar la corrección en entorno aislado. No ejecutar pruebas con VAL_TEST_DATABASE_URL apuntando a producción.','Validar el flujo con Operaciones/Reingeniería cuando cambien reglas o reportes.','Coordinar ventana y pausa; comprobar ruta, servicio, versión y respaldo.','Usar scripts/actualizar_produccion.sh con la revisión aprobada. El procedimiento prepara dependencias antes de la parada y conserva respaldo privado.','Verificar aplicación, acceso, SQL, una operación representativa y, si aplica, fotos/documentos/correo. Recargar PC y handheld sin borrar los borradores del navegador.','Registrar resultado y retorno de código si corresponde. No confundir retorno de código con restauración SQL.')+
       '<p>No actualizar paquetes en producción directamente a «la última versión». Revisar cambios y vulnerabilidades, fijar versiones compatibles, probar y ejecutar el pase aprobado. Los archivos requirements.txt y package.json documentan las dependencias de referencia.</p>'+
       '<p>Una migración futura debe incluir compatibilidad, ensayo con copia autorizada, respaldo y estrategia de recuperación. No borrar ni reinterpretar los eventos históricos para adaptar un formato nuevo.</p>'),
      ('recuperacion','Respaldo, recuperación y continuidad',
       tabla(['Elemento a proteger','Contenido / razón'],[
        ['MySQL','Datos de recepción, eventos, usuarios, configuración, estados de fotos e informes/entregas.'],
        ['VAL_DATA_DIR','Archivos operativos y miniaturas conservadas localmente.'],
        ['integraciones.key y entorno protegido','Descifrado de credenciales y configuración de conexiones.'],
        ['Código y dependencias','Referencia compatible con el esquema y el funcionamiento recuperado.'],
        ['Drive','Retención y recuperación de fotografías/documentos, incluidas evidencias cuyo original local se liberó tras confirmar la copia.']])+
       '<p>Propuesta inicial: respaldo diario y antes de cada cambio; retención, copia separada del servidor y frecuencia de ensayos a aprobar por TI. La recuperación debe probar SQL, archivos, clave y lectura de evidencias, no solo el arranque de la página.</p>'+
       '<p>TI establecerá RPO (pérdida de datos tolerable) y RTO (tiempo objetivo de recuperación). Se registran los valores aprobados y el resultado del ensayo en el acta. El código de respaldo del pase comprueba integridad; no sustituye esa definición institucional.</p>'+
       '<p>Ante una falla: preservar evidencia, identificar el último respaldo consistente, aislar el entorno de restauración, restaurar la combinación compatible, contrastar cantidades/archivos y coordinar el retorno operativo. No restaurar SQL sobre producción sin el control del cambio y del impacto.</p>'),
      ('evolutivo','Mantenimiento evolutivo y preparación de la V2',
       '<p>La versión actual se mantendrá como línea estable durante la preparación de la V2. Las correcciones de producción se registran, prueban y liberan de forma controlada; el trabajo experimental de incorporación de clientes se realiza en un entorno separado.</p>'+
       lista('Mantener un registro de requisitos y defectos, con responsable, prioridad y versión objetivo.','Separar correcciones de integridad de mejoras de experiencia o nuevas reglas por cliente.','Actualizar la documentación de arquitectura, parámetros y reportes en cada liberación.','Revisar capacidad y crecimiento con mediciones reales antes de ampliar clientes/usuarios.','Validar el piloto de cada cliente antes de habilitarlo en producción; conservar el histórico vigente.')+
       '<p>La V2 es una evolución planificada. Las fechas, clientes de la primera etapa, alcance definitivo y recursos se acuerdan con TI, Reingeniería y Operaciones.</p>'),
    ]


def seccion_v2():
    return ('v2','Proyección V2: incorporación de otros clientes de la bodega',
      '<p>Se continuará trabajando en una <b>V2 orientada a incorporar la operación de otros clientes presentes en bodega</b>. El objetivo es reutilizar el flujo de recepción, evidencia y entrega, adaptando catálogos, reglas, documentos y responsables por cliente, y preservando la operación y los datos actuales.</p>'+
      '<div class="banda">Estado: evolución prevista, pendiente de levantamiento y validación. La existencia actual de campos y reglas por cliente no acredita una segregación multicliente completa ni autoriza incorporar clientes sin comprobarla.</div>'+
      tabla(['Línea de evolución','Trabajo previsto','Criterio de aceptación'],[
       ['Separación de información','Validar visibilidad y permisos por cliente en API, interfaz, fotos, exportaciones y auditoría.','Un usuario solo accede al alcance autorizado; no hay cruces de enlaces, archivos o datos.'],
       ['Catálogos e identidad del producto','Evaluar SKU/códigos iguales entre clientes, claves y contexto de búsquedas.','El mismo SKU en dos clientes conserva catálogo, cantidades y evidencia independientes.'],
       ['Reglas operativas','Parametrizar packing list, unidades, bultos, posiciones, incidencias y validaciones por cliente.','Cada flujo coincide con el procedimiento aprobado de ese cliente.'],
       ['Informes y correo','Plantillas, destinatarios del ejecutivo, nombres de adjuntos y distribución.','Cada cliente recibe solo su grupo, formato y documentos validados.'],
       ['Drive e integraciones','Organización, propiedad/permisos y configuración de cuentas/Depot según el diseño aprobado.','Enlaces válidos y acceso autorizado sin compartir evidencia de otro cliente.'],
       ['Indicadores y capacidad','Tableros por cliente, recepción, ítem e incidencia; medir carga, tiempos y crecimiento.','Indicadores reproducibles desde los eventos y capacidad validada con carga representativa.']])+
      '<h3>Secuencia propuesta</h3>'+tabla(['Etapa','Resultado'],[
       ['1. Levantamiento','Clientes priorizados, responsables y diferencias del flujo actual.'],
       ['2. Diseño técnico','Modelo de acceso/datos, identidad de SKU y configuración por cliente.'],
       ['3. Construcción y pruebas','Catálogos/formatos, pruebas de segregación, concurrencia, evidencias e informes.'],
       ['4. Piloto de un cliente','Validación conjunta de Operaciones, Reingeniería y TI.'],
       ['5. Despliegue gradual','Habilitación por grupos con monitoreo y criterios de retorno.']])+
      '<p>No se comprometen fechas ni se identifica un cliente piloto sin acuerdo. La aceptación de la versión actual se registra por separado de la autorización del proyecto V2.</p>')


def informe(inv):
    anteriores = base.secciones_documento(inv)
    resumen = ('objeto','Objeto, control documental y alcance de entrega',
       tabla(['Campo','Referencia'],[['Documento',ID+' · Revisión documental 1.0'],['Fecha de preparación',base.FECHA+' · America/Guayaquil'],['Sistema','ITSANET IMS · recepción y validación física'],['Versión funcional de referencia','v69 · recursos 20261024-69'],['Commit funcional', '<code>'+base.REVISION+'</code>'],['Destinatarios','TI, Reingeniería, Operaciones y administrador designado'],['Estado','Expediente para transferencia y recepción formal mediante acta.']])+
       '<p>Se entrega la documentación técnica de la solución implementada para dejar constancia de su arquitectura, componentes, reglas, integraciones, operación, mantenimiento y evolución prevista. El responsable informa que el aplicativo se encuentra en producción; el acta incorpora la revisión efectivamente instalada y la comprobación del inventario del servidor.</p>'+
       '<p>El alcance comprende el registro de recepciones, packing lists, conteos por ítem, pallets/posiciones, incidencias/PNC, evidencias fotográficas, informes y preparación/envío al ejecutivo de cuenta, con usuarios, supervisión y auditoría de aplicación.</p>'+
       '<p>La recepción documental no equivale por sí sola a una firma de aceptación técnica. Las personas responsables, observaciones, verificaciones del entorno y firmas se consignan en el acta adjunta.</p>')
    alcance = ('implementado','Matriz de implementación y constancia de funcionalidad',
       tabla(['Componente implementado','Resultado / control','Referencia de código'],[
        ['Recepciones','Cliente/marca, fecha/hora original, estado, búsqueda y filtros.','recepciones.html; recepciones_listado.py'],
        ['Conteo por ítem','Registros con cantidad, pallet, posición, autor y origen.','validar.html; conteo.js; app_modelo.py'],
        ['Registro cero v69','Mismo flujo Guardar conteo, observación y confirmación; conserva cantidades anteriores.','CONTEO_CERO_Y_CANTIDADES_69.md'],
        ['Calidad/PNC','Unidades afectadas por registro, condición, evidencia y trazabilidad.','calidad.py; detalle-registros.js'],
        ['Correcciones y concurrencia','Original compensado, motivo, control de estado, presencia y actualización de vistas.','correcciones.py; cambios_recepcion.py'],
        ['Fotografías y Drive','Previsualización, clasificación, copia con estados/confirmaciones y rutas bajo demanda.','google_drive_api.py; carpetas_recepcion.py'],
        ['Informes v68','Números calculables, filas conservadas, identificadores limpios y detalle final por pallet/PNC.','informe.js; ubicaciones-informe.js'],
        ['Correo','Edición, selección/nombres de adjuntos, vínculo al original y confirmación de entrega.','correo_redactado.py; correo_envio.py; google_gmail_api.py'],
        ['Bultos y etiquetas','Gestión del total con protección de unidades usadas; rangos de impresión y código escaneable.','etiquetas-bultos.js; servicios de ingreso/impresión'],
        ['Administración y monitoreo','Usuarios/roles, reglas, catálogo, eventos y estados de procesos.','ajustes.py; procesos.py; routers de administración']])+
       '<p>Las funcionalidades se describen conforme al código entregado. La validación de la instalación vigente se completa en el servidor y queda asociada al acta; no se sustituyen registros productivos por datos de prueba.</p>')
    validacion = ('validacion','Validación, entregables y recepción técnica',
       '<p>La evidencia de desarrollo de v69 registra 1.530 pruebas generales aprobadas (920 Python y 610 JavaScript/Apps Script). La suite final app.test.mjs, que incorpora dos casos nuevos, registra 141 casos aprobados; se documentan además 53 pruebas en MySQL aislado, comprobaciones finales de cero y 89 comprobaciones de páginas. Estas cifras corresponden a ejecuciones de desarrollo, no a una certificación del servidor productivo.</p>'+
       '<p>La validación de navegador cubrió escritorio/móvil, cero con observación, cancelación, historial, modal de corrección, protección de rueda/flechas y conservación de PNC previa. Los reportes v68 se comprobaron con generación XLSX, otra biblioteca de lectura y descarga desde navegador.</p>'+
       tabla(['Entregable','Contenido / identificación'],[
        ['Informe técnico de entrega','Arquitectura, implementación, datos, integraciones y controles.'],
        ['Plan de mantenimiento','Responsabilidades, rutinas, incidentes, cambios y recuperación.'],
        ['Acta de entrega y recepción','Inventario observado, responsables, evidencias, observaciones y firmas.'],
        ['Inventario JSON','30 tablas y 191 declaraciones de rutas del código; no es inventario de la BD instalada.'],
        ['Código de referencia','Repositorio Git y snapshot v69, identificados con su SHA.'],
        ['Manifiesto de integridad','SHA-256 de los archivos entregados; no sustituye una firma institucional.']])+
       '<h3>Comprobación de recepción</h3>'+lista('Cotejar URL, revisión instalada, servicio y motor MySQL de la instancia utilizada.','Revisar configuración efectiva de Apache/TLS y permisos de conexión del aplicativo.','Verificar acceso de roles y una operación representativa con cantidades/evidencias/informe.','Identificar respaldos, clave de recuperación y evidencia de ensayo; asignar responsables.','Registrar observaciones y su tratamiento antes de dar conformidad a los puntos pendientes.')+
       '<p>Credenciales, secretos, respaldos productivos y llaves no forman parte del paquete documental. Su acceso/custodia se transfiere de forma segura y se deja la referencia institucional en el acta, sin copiar sus valores.</p>')
    mantenimiento = ('mantenimiento','Modelo de mantenimiento del aplicativo',
       '<p>La continuidad del aplicativo se sostendrá con administración funcional diaria, mantenimiento de infraestructura por TI y correcciones/evolución del código mediante el mantenedor designado. Reingeniería y Operaciones validarán los cambios del flujo.</p>'+
       tabla(['Modalidad','Forma de trabajo'],[['Preventivo','Revisión de pendientes, catálogo, accesos, capacidad, certificados, dependencias y respaldos.'],['Correctivo','Incidente documentado, diagnóstico, reproducción en pruebas, corrección y verificación.'],['Evolutivo','Requisitos priorizados, diseño, pruebas, piloto y liberación controlada; incluye la V2.']])+
       '<p>El plan adjunto define rutinas y roles. La periodicidad propuesta, responsables nominales, suplencias, horarios, retención y objetivos de recuperación se acuerdan y registran en el acta de recepción.</p>'+
       '<p>Las actualizaciones se realizan por revisión Git aprobada, con el actualizador y respaldo. El mantenimiento no debe recurrir a modificar cantidades mediante SQL manual, borrar eventos históricos ni reintentar correos sin comprobar su estado.</p>')
    tecnicas = [s for s in anteriores if s[0] not in ('resumen','guion','fuentes','operacion')]
    fuentes = next(s for s in anteriores if s[0]=='fuentes')
    return [resumen, alcance, *tecnicas, mantenimiento, seccion_v2(), validacion, fuentes]


def documento(nombre, titulo, subtitulo, secciones):
    indice=''.join('<a href="#'+i+'">'+str(n)+'. '+re.sub(r'^\d+\.\s*','',t)+'</a>' for n,(i,t,_) in enumerate(secciones,1))
    cuerpo=''.join('<section id="'+i+'"><h2>'+str(n)+'. '+re.sub(r'^\d+\.\s*','',t)+'</h2>'+c+'</section>' for n,(i,t,c) in enumerate(secciones,1))
    script=base.JS_DOCUMENTO.replace('Documento-de-apoyo-ITSANET-20261027.html',nombre).replace(r'<!doctype html>\\n',r'<!doctype html>\n')
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+E(titulo)+'</title><style>'+base.CSS+'@page{size:A4 portrait;margin:16mm}</style></head><body class="documento"><header><div class="eyebrow" style="color:#90d3ca">'+ID+' · Rev. documental 1.0</div><h1>'+E(titulo)+'</h1><p class="sub">'+E(subtitulo)+'</p><p>'+base.FECHA+' · Código funcional de referencia v69</p></header><main><nav aria-label="Contenido"><label for="buscar"><b>Buscar</b></label><input id="buscar" type="search" placeholder="MySQL, mantenimiento, V2…"><div class="herramientas"><button id="limpiar">Limpiar</button><button id="expandir">Abrir detalles</button></div><div class="indice">'+indice+'</div><div class="herramientas"><button id="imprimir">Imprimir / PDF</button><button id="descargar">Descargar HTML</button></div><p id="estado" class="mini" role="status">Documento autónomo. Sin conexiones a producción.</p><a href="index.html">Expediente completo</a></nav><div class="contenido"><p id="vacio" hidden>No hay secciones coincidentes.</p>'+cuerpo+'</div></main><script>'+script+'</script></body></html>'


def campo(clave, titulo, grande=False):
    return '<label class="campo"><span>'+titulo+'</span>'+('<textarea rows="3" data-campo="'+clave+'"></textarea>' if grande else '<input data-campo="'+clave+'" autocomplete="off">')+'</label>'


def acta():
    pagina1='<section><h1>Acta de entrega y recepción técnica</h1><p><b>'+ID+'-ACTA · Revisión 1.0</b><br>ITSANET IMS · Código de referencia v69 / '+base.REVISION[:12]+'</p><p>Se deja constancia de la entrega del expediente técnico y de la revisión indicada a continuación. Los acuerdos, observaciones y conformidades son los que completen y firmen las partes; esta plantilla no acredita aceptación por sí sola.</p><h2>1. Identificación e inventario observado</h2><div class="campos">'+''.join(campo(k,t) for k,t in [
       ('fecha','Fecha de revisión/recepción'),('lugar','Lugar / área'),('entrega','Ingeniero / responsable que entrega'),('recibe','Responsable TI que recibe'),('ri','Responsable de Reingeniería'),('admin','Administrador del aplicativo designado'),('suplente','Suplente / contacto de soporte'),('revision','Commit efectivamente instalado'),('mysql','Versión de la instancia MySQL usada por la app'),('apache','Versión Apache / virtual host de referencia'),('servicio','Servicio y ruta efectiva del aplicativo'),('certificado','Referencia y vencimiento del certificado')])+'</div><p><b>URL documentada:</b> '+E(base.URL)+'<br><b>Puertos documentados:</b> Apache 8443 / Uvicorn 3002. Validar configuración efectiva y exposición con TI.</p><p class="nota">No registrar contraseñas, tokens ni claves privadas. Para accesos/custodia usar la referencia del repositorio seguro institucional.</p></section>'
    checks=[('documentos','Informe, plan de mantenimiento e inventario recibidos.'),('codigo','Revisión/snapshot de código identificados y accesibles.'),('accesos','Roles y acceso técnico revisados sin copiar secretos.'),('operacion','Operación representativa, cantidades, PNC e informe contrastados.'),('imagenes','Estado de fotografías, miniaturas y enlaces revisado.'),('correo','Cuenta autorizada, adjuntos y confirmación del correo revisados cuando aplique.'),('respaldo','Respaldo y custodia de recuperación identificados.'),('restauracion','Evidencia de restauración en entorno aislado revisada o pendiente registrada.')]
    pagina2='<section><h2>2. Entregables y verificaciones</h2><p>Marcar únicamente lo comprobado y anotar evidencias/observaciones. Una casilla no equivale a firma electrónica.</p><div class="checks">'+''.join('<label><input type="checkbox" data-campo="check_'+k+'"> '+t+'</label>' for k,t in checks)+'</div><h2>3. Mantenimiento y continuidad acordados</h2><div class="campos">'+''.join(campo(k,t) for k,t in [
        ('rutinas','Responsables de rutina diaria y revisión semanal'),('horarios','Horario y canal de atención / escalamiento'),('backups','Frecuencia, retención y ubicación de respaldo'),('custodia','Referencia segura de custodia de accesos/clave'),('rpo','RPO aprobado / fecha de ensayo'),('rto','RTO aprobado / resultado de ensayo')])+'</div>'+campo('evidencias','Referencias de pruebas, tickets, respaldos y anexos revisados',True)+'</section>'
    pagina3='<section><h2>4. Observaciones y conformidad</h2>'+campo('observaciones','Observaciones, pendientes, responsables y fecha acordada de atención',True)+'<label class="campo"><span>Resultado de la recepción</span><select data-campo="resultado"><option value="">Seleccionar al revisar</option><option>Recepción documental; verificación técnica pendiente</option><option>Recepción técnica con observaciones registradas</option><option>Conformidad técnica del alcance revisado</option></select></label><h2>5. Continuidad de trabajo en V2</h2><p>Se prevé continuar la V2 para incorporar otros clientes presentes en bodega. Clientes prioritarios, segregación de información, reglas, formatos, recursos, piloto y fechas se definirán con TI, Reingeniería y Operaciones. Esta acta no declara esas funcionalidades como implementadas ni compromete un cronograma no aprobado.</p>'+campo('acuerdos_v2','Acuerdos de levantamiento y responsables para V2',True)+'<h2>6. Firmas y constancia institucional</h2>'+tabla(['Responsable','Nombre / firma / fecha'],[['Entrega técnica','________________________________________'],['Recepción TI','________________________________________'],['Validación Reingeniería / Operaciones','________________________________________'],['Administrador designado','________________________________________']])+'<p>Archivar el acta firmada y los anexos según el procedimiento institucional. El JSON o HTML guardado es una copia local de trabajo y no sustituye el documento firmado.</p></section>'
    css='''body{font:15px/1.45 system-ui,Arial,sans-serif;color:#142d46;background:#eef3f8;margin:0}*{box-sizing:border-box}main{max-width:1000px;margin:24px auto;padding:0 16px}section{background:white;border:1px solid #d5e0eb;border-radius:14px;padding:30px;margin-bottom:22px}h1{font-size:28px;margin:0 0 15px}h2{font-size:20px;margin:22px 0 12px}.barra{position:sticky;top:0;padding:12px 18px;background:#142d46;color:white;display:flex;gap:8px;align-items:center;flex-wrap:wrap}.barra button{padding:10px 14px;border:0;border-radius:7px;background:white;color:#142d46;font:600 13px system-ui;cursor:pointer}.barra span{font-size:12px}.campos{display:grid;grid-template-columns:1fr 1fr;gap:13px 20px}.campo{display:block;margin:9px 0}.campo span{display:block;font-size:12px;font-weight:650;margin-bottom:5px}.campo input,.campo textarea,.campo select{font:14px system-ui;width:100%;min-width:0;padding:9px;border:1px solid #b9cadb;border-radius:6px;background:#f8fafc;color:#142d46}.campo textarea{resize:vertical;min-height:65px}.checks label{display:flex;gap:10px;padding:7px 0;border-bottom:1px solid #e0e8ef}.checks input{flex:none;margin-top:4px}.nota{background:#fff7e4;padding:12px;font-size:12px}.tabla{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid #d5e0eb;text-align:left;padding:12px}th{background:#eef3f8}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:3px solid #81aaff;outline-offset:2px}@media(max-width:600px){.campos{grid-template-columns:1fr}section{padding:20px 16px}main{padding:0 8px}h1{font-size:25px}}@page{size:A4 portrait;margin:15mm}@media print{.barra{display:none!important}body{background:white;font-size:9.5pt}main{margin:0;padding:0;max-width:none}section{border:0;border-radius:0;margin:0;padding:0;break-before:page}section:first-child{break-before:auto}h1{font-size:19pt}h2{font-size:13pt;margin:4mm 0 2mm}.campos{grid-template-columns:1fr 1fr;gap:1mm 6mm}.campo{margin:2mm 0}.campo span{font-size:8.5pt}.campo input,.campo select,.campo textarea{font-size:9pt;border:0;border-bottom:1px solid #777;border-radius:0;background:white;padding:2mm;min-height:7mm}.campo textarea{height:18mm;resize:none}.checks label{padding:2mm 0}.nota{font-size:8pt;padding:2mm}table{font-size:9pt}td,th{padding:3mm}tr{break-inside:avoid}p{margin:3mm 0}}
'''
    js='''const campos=[...document.querySelectorAll('[data-campo]')],clave='itsanet.acta.entrega-ti.20261027.v1',estado=document.querySelector('#estado');const valores=()=>Object.fromEntries(campos.map(e=>[e.dataset.campo,e.type==='checkbox'?e.checked:e.value]));try{const copia=JSON.parse(localStorage.getItem(clave)||'null');if(copia&&!campos.some(e=>e.type==='checkbox'?e.hasAttribute('checked'):e.tagName==='TEXTAREA'?e.textContent.trim():e.tagName==='SELECT'?e.querySelector('option[selected]')?.value:e.getAttribute('value')))for(const e of campos){if(e.type==='checkbox')e.checked=!!copia[e.dataset.campo];else e.value=copia[e.dataset.campo]||'';}}catch{}for(const e of campos)e.addEventListener('input',()=>{try{localStorage.setItem(clave,JSON.stringify(valores()));estado.textContent='Borrador guardado en este navegador; sin firma ni envío.';}catch{estado.textContent='No se pudo guardar en el navegador; descarga una copia para conservarla.';}});function bajar(n,t,c){const u=URL.createObjectURL(new Blob([c],{type:t})),a=document.createElement('a');a.href=u;a.download=n;a.click();setTimeout(()=>URL.revokeObjectURL(u),4000);}document.querySelector('#json').onclick=()=>bajar('Acta-entrega-TI-20261027.json','application/json',JSON.stringify({documento:'ITSANET-TI-ENT-20261027-ACTA',estado:'Copia de trabajo sin firma institucional',campos:valores()},null,2));document.querySelector('#html').onclick=()=>{const d=document.documentElement.cloneNode(true);for(const e of d.querySelectorAll('[data-campo]')){const v=valores()[e.dataset.campo];if(e.type==='checkbox')e.toggleAttribute('checked',!!v);else if(e.tagName==='TEXTAREA')e.textContent=v;else if(e.tagName==='SELECT')for(const o of e.options)o.toggleAttribute('selected',o.value===v);else e.setAttribute('value',v);}bajar('Acta-entrega-recepcion-TI-20261027.html','text/html;charset=utf-8','<!doctype html>\\n'+d.outerHTML);};document.querySelector('#imprimir').onclick=()=>window.print();'''
    js=js.replace(r'<!doctype html>\\n',r'<!doctype html>\n')
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Acta de entrega y recepción · ITSANET IMS</title><style>'+css+'</style></head><body><div class="barra"><button id="imprimir">Imprimir / PDF</button><button id="html">Guardar copia HTML</button><button id="json">Exportar registro JSON</button><span id="estado" role="status">Plantilla para completar y firmar. Sin aceptación registrada.</span></div><main>'+pagina1+pagina2+pagina3+'</main><script>'+js+'</script></body></html>'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--salida',type=Path,default=RAIZ/'docs/entrega-final-ti-20261027')
    salida=p.parse_args().salida;salida.mkdir(parents=True,exist_ok=True)
    inv=base.inventario()
    docs=[('Informe-tecnico-entrega-TI-20261027.html','Informe técnico de entrega a TI','Constancia de implementación, arquitectura, componentes y evolución prevista V2.',informe(inv)),('Plan-mantenimiento-ITSANET-20261027.html','Plan de mantenimiento del aplicativo','Administración, soporte, control de cambios, respaldo y continuidad.',secciones_mantenimiento())]
    for nombre,titulo,sub,secciones in docs:(salida/nombre).write_text(documento(nombre,titulo,sub,secciones))
    (salida/'Acta-entrega-recepcion-TI-20261027.html').write_text(acta())
    (salida/'inventario-codigo-v69.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2)+'\n')
    enlaces=''.join('<article class="tarjeta"><h3>'+titulo+'</h3><p>'+texto+'</p><a class="boton" href="'+nombre+'">Abrir HTML</a></article>' for nombre,titulo,texto in [(docs[0][0],'Informe técnico','Detalle de la versión entregada y plan V2.'),(docs[1][0],'Mantenimiento','Rutinas, responsables y recuperación.'),('Acta-entrega-recepcion-TI-20261027.html','Acta de recepción','Completar evidencias, responsables y firmas.')])
    (salida/'index.html').write_text('<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Expediente de entrega final a TI · ITSANET</title><style>'+base.CSS+'</style><body class="documento"><header><h1>Expediente de entrega final a TI</h1><p>'+ID+' · '+base.FECHA+'</p><p class="sub">Implementación v69, mantenimiento y continuidad hacia la V2 para otros clientes de bodega.</p></header><main style="display:block"><section><div class="grid">'+enlaces+'</div><p>El paquete incluye PDF de los tres documentos, inventario y referencia/snapshot del código. Los HTML funcionan sin conexión y el acta se completa localmente; no envía información ni registra una firma electrónica.</p><p>La recepción se formaliza con responsables, evidencias y firmas institucionales. Las actividades de V2 se presentan como trabajo previsto.</p></section></main></body></html>')
    print('Expediente generado: '+str(salida))


if __name__=='__main__':main()
