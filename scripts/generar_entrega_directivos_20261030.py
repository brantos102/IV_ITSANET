"""Informe breve, manual de usuarios ilustrado y réplica técnica, sin acceso a producción."""
from pathlib import Path
import argparse
import base64
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('cierre',ROOT/'scripts/generar_cierre_documental_20261029.py')
D=importlib.util.module_from_spec(s);s.loader.exec_module(D)
M=D.M;T,L,C,K=D.T,D.L,D.C,D.K
FECHA='30 de octubre de 2026'
ASSETS={
 'movil':('v69/Cantidad-movil-sin-flechas.png','Validación por SKU en móvil · pruebas v69'),
 'camara':('v64/camara-390x844.png','Captura de evidencia · pruebas v64'),
 'correo':('v65/adjuntos-nombres-conservados.png','Selección y nombre por adjunto · pruebas v65'),
 'supervisor':('v65/avisos-supervisor-movil.png','Revisión de PNC y evidencia pendiente · pruebas v65'),
 'admin':('admin_42.png','Administración de conexiones y reglas · pruebas v42'),
 'presencia':('v64/coordinacion-1.png','Aviso de otro operario validando el SKU · pruebas v64')}


def foto(key,clase=''):
    ruta,caption=ASSETS[key]
    raw=(SALIDA/'capturas'/Path(ruta).name).read_bytes()
    data='data:image/png;base64,'+base64.b64encode(raw).decode()
    return '<figure class="captura '+clase+'"><img src="'+data+'" alt="'+caption+'"><figcaption>'+caption+'</figcaption></figure>'


ARBOL='''RAIZ / CLIENTE / MARCA / RECEPCION
├── INFORMES
└── EMBARQUE (si aplica)
    ├── PRE-INGRESO · PANORAMICAS · FOTOS-FINALES
    ├── BULTOS / Bulto… / Caja…
    └── PRODUCTOS · PNC · SOBRANTES · FALTANTES / SKU'''


def recursos():
    return T(['Mecanismo','Cómo funciona','Alcance'],[
      ['Conservación local','Original retenido durante la transferencia; después de confirmar Drive se conserva miniatura y puede liberarse el original local.','Reduce la retención duplicada de originales; requiere protección y retención en Drive.'],
      ['Vistas y consultas','Recepciones: respuesta paginada, predeterminada de 50. Galería con consultas limitadas y miniaturas.','La paginación de la respuesta no implica que todas las consultas internas lean solo 50 filas.'],
      ['Actualización coordinada','Canal compartido por recepción/página, invalidación por revisión y consulta alternativa cada 4 s. Las páginas ocultas detienen su canal.','Evita refrescos completos innecesarios; 4 s es configuración de respaldo, no latencia garantizada.'],
      ['Persistencia','Proyección de estado por SKU, transacciones e identidad estable de operaciones. Pool SQL con comprobación y reciclaje.','Facilita lectura y reintentos; requiere dimensionar conexiones y carga real.'],
      ['Procesos externos','Estados durables de fotos y entregas en SQL, con intentos y revisión.','Un proceso pendiente se distingue de una operación confirmada.']])


def informe():
    return [
    ('operacion','1. Una operación conectada de principio a fin',
     '<p class="lead">IV ITSANET (Ingreso &amp; Validación Itsanet) reúne el registro físico, la revisión y la entrega documental en una misma herramienta, accesible desde computador y handheld.</p>'+
     T(['Etapa','Resultado operativo'],[['Recepción','Registro de cliente, fecha, embarques, bultos y estado; búsqueda y filtros para seguimiento.'],['Packing list','Carga de líneas y cantidades esperadas, conservando el origen y el orden del archivo.'],['Validación','Lectura por escáner o cámara; cantidad, pallet y posición asociados al registro.'],['Avance y coordinación','Consulta de avance y responsables; presencia de otro operario sobre el mismo SKU.'],['Novedades','Faltantes, sobrantes y PNC con unidades, observación y evidencia vinculada.'],['Revisión y entrega','Carpetas, fotos finales, documentos seleccionados y correo con estado de confirmación.']])+
     '<div class="fotos dos">'+foto('movil')+foto('camara')+'</div>'+
     '<p class="nota-captura">Capturas de pruebas con datos sintéticos; ilustran funciones del código de referencia, no una recepción productiva actual.</p>'),
    ('roles','2. Responsabilidades visibles por rol',
     T(['Rol','Trabajo dentro del aplicativo'],[['Operario','Seleccionar recepción, escanear, contar, ubicar, registrar condición/novedad e imágenes y consultar su bitácora.'],['Supervisor','Revisar avance, cantidades y PNC; verificar evidencia; gestionar correcciones autorizadas; preparar informes y confirmar entrega al ejecutivo.'],['Administrador','Gestionar usuarios/roles, catálogo, reglas e integraciones; revisar procesos, errores y pendientes; coordinar mantenimiento con el responsable técnico.']])+
     '<p>El avance permite identificar el trabajo registrado y quién intervino. El aviso de presencia ayuda a coordinar conteos simultáneos; la validación de versiones e identificadores de operación protege los registros ante conflictos y reintentos.</p>'+
     foto('presencia','franja')+
     '<div class="fotos dos">'+foto('supervisor')+foto('admin')+'</div>'+
     '<p class="nota-captura">Las funciones disponibles dependen de los permisos asignados. ADMIN del aplicativo no equivale a administrador del servidor.</p>'),
    ('evidencias','3. Evidencias, carpetas y comunicación final',
     '<p>La evidencia se clasifica por recepción, embarque, categoría y SKU cuando corresponde. Antes de entregar se revisan las fotos finales, los pendientes y sus enlaces. Una miniatura visible no sustituye la confirmación de copia en Drive.</p>'+C(ARBOL)+
     '<p>Las rutas se crean al utilizarse; no se precrean todas las categorías. Se contemplan evidencias compartidas y pendientes de asignación. Una carga interrumpida puede dejar una ruta vacía que requiere revisión.</p>'+
     foto('correo','ancha')+
     '<p>El usuario elige los informes, revisa su contenido y conserva el nombre final de cada adjunto. El envío utiliza la cuenta Gmail autorizada. Ante una entrega pendiente se revisan el estado y Enviados antes de repetir.</p>'),
    ('continuidad','4. Funcionamiento técnico y continuidad',
     '<p>La publicación utiliza Apache HTTPS; FastAPI/Uvicorn ejecuta la aplicación y MySQL conserva la operación. Drive almacena evidencias e informes. El diseño combina miniaturas, consultas limitadas y actualización por recepción para reducir trabajo y transferencia innecesarios.</p>'+
     T(['Aspecto','Situación documentada'],[['Disco del servidor','Captura del 27/10/2026: raíz de 73 GB, 19 GB usados y 50 GB disponibles, uso 28 %. Son cifras del servidor compartido, no del consumo exclusivo de IV ITSANET.'],['Validación simultánea','Presencia por SKU, controles de concurrencia e idempotencia y actualización de vistas. No se dispone de una prueba productiva que certifique un número máximo de usuarios simultáneos.'],['Mantenimiento','Revisión diaria de pendientes/disponibilidad; capacidad semanal; accesos y dependencias mensuales; restauración de prueba trimestral y respaldo antes de cada cambio.'],['Protección y respaldo','Roles, credenciales protegidas y trazabilidad. Respaldar SQL, archivos, clave y configuración; Drive requiere su propia política de retención.'],['Evolución','Mantener la línea actual estable y preparar V2 para otros clientes, validando separación de datos, reglas y documentos.']])+
     '<p>La efectividad se demuestra con controles y registros verificables. Las mejoras porcentuales de tiempo, ahorro de disco atribuible a la aplicación y capacidad de concurrencia se cuantifican con mediciones comparables; no se asignan cifras sin evidencia.</p>'+
     '<p>Agradecemos al equipo de Ingresos, Inventarios y Slotting por su apoyo en las pruebas de uso y en la definición del flujo de trabajo. La documentación adjunta reúne el detalle técnico y los pasos de operación para dar continuidad al aplicativo.</p>')]


def usuarios():
    return [
    ('operario','1. Operario: validar y respaldar el registro',
     L('Ingresar con la cuenta propia y seleccionar recepción/embarque. Confirmar que el código corresponde a la mercadería.','Escanear con el lector físico o pulsar Cámara. Revisar el SKU y la cantidad esperada; la lectura por sí sola no guarda el conteo.','Ingresar cantidad, pallet y posición. Para declarar cero, registrar observación y confirmar; el cero no borra cantidades anteriores.','Registrar condición física, unidades PNC y observación cuando corresponda. Adjuntar la fotografía desde el flujo de fotos del registro y revisar su clasificación.','Guardar y consultar la bitácora. Si aparece otro operario en el SKU, coordinar las unidades y pallets antes de continuar. Ante conflicto, revisar la versión; no repetir con otra identidad para forzar el guardado.')+
     '<div class="fotos dos">'+foto('movil')+foto('camara')+'</div>'+
     '<p>No eliminar borradores o fotos pendientes del navegador como solución genérica. Informar al supervisor si un registro o imagen requiere revisión.</p>'),
    ('supervisor','2. Supervisor: revisar, corregir y entregar',
     L('Registrar o revisar la recepción y sus bultos/embarques. Cargar el packing list con el formato correcto y comprobar que las cantidades/orígenes corresponden.','Consultar avance y responsables. Revisar faltantes, sobrantes y PNC por registro, no solo por el total del SKU.','Verificar pallet/posición, observaciones e imágenes. Si la novedad requiere evidencia y no la tiene, solicitar su registro antes de entregar.','Gestionar correcciones según permisos, dejando motivo y trazabilidad. Revisar estados de copia y enlaces de carpeta/fotos finales.','Preparar documentos y descargarlos para revisión. Seleccionar adjuntos, editar el nombre de cada archivo y revisar destinatarios.','Enviar desde la cuenta autorizada y verificar confirmación. Si queda pendiente, revisar la entrega y Enviados antes de volver a intentar.')+
     '<div class="fotos dos">'+foto('supervisor')+foto('correo')+'</div>'),
    ('admin','3. Administrador: cuentas, configuración y seguimiento',
     L('Registrar o mantener usuarios, roles y habilitación con el alcance aprobado. Revisar cuentas sin uso y conservar la autoría de los registros.','Mantener el catálogo y revisar avisos de actualización. Validar reglas y formatos antes de cambiarlos.','Configurar Google/Depot y carpetas operativas con credenciales protegidas. La cuenta que autoriza Gmail determina el remitente real.','Revisar monitor de procesos, intentos y errores. Recuperar pendientes con la identidad existente; no crear duplicados para ocultar una falla.','Escalar problemas de servicio, red, SQL o certificado al responsable de infraestructura; coordinar cambios y respaldos. La administración funcional no requiere modificar directamente datos SQL.')+
     foto('admin','ancha')+
     '<p>No publicar claves, tokens, archivos de entorno ni capturas con credenciales. Los permisos de los enlaces Drive deben corresponder a sus destinatarios.</p>'),
    ('revision','4. Revisión final y solución de pendientes',
     T(['Comprobación','Acción'],[['Cantidades y ubicación','Revisar registro, origen, pallet/posición y cantidad PNC antes de preparar el informe.'],['Imágenes','Comprobar guardado, clasificación, copia confirmada, enlace y fotos finales.'],['Carpetas','Revisar la recepción/embarque correcto. No borrar rutas históricas sin contrastar referencias.'],['Documentos','Revisar números, novedades y adjuntos seleccionados con sus nombres finales.'],['Correo','Confirmar destinatarios, cuenta autorizada y resultado de entrega.'],['Incidencia','Registrar fecha, recepción/SKU, acción y error; compartir evidencia sin secretos.']])+C(ARBOL)+
     '<p>El árbol resume rutas posibles; cliente/marca/embarque dependen del contexto. INFORMES se ubica bajo la recepción. Las categorías solo se materializan cuando se utilizan.</p>'+
     '<p>Capturas incluidas: interfaz de pruebas v42/v64/v65/v69, con datos sintéticos. La configuración actual puede mostrar variantes visuales conservando el flujo documentado. Referencia funcional: v69.</p>')]


EXTRA_CSS='''
.fotos{display:flex;gap:18px;align-items:flex-start;justify-content:center;flex-wrap:wrap}.fotos>figure{flex:1;min-width:180px}.captura{margin:18px 0;text-align:center}.captura img{max-width:100%;height:310px;object-fit:contain;border:1px solid #dce5ef;border-radius:8px}.captura.ancha img{height:auto;max-height:400px;width:100%;object-fit:contain}.captura.franja{height:95px;overflow:hidden;text-align:left}.captura.franja img{height:auto;width:100%;border:0}.captura.franja figcaption{position:relative}.captura figcaption,.nota-captura{font-size:12px!important;color:#526781}.documento .lead{font-size:19px}.documento .captura.franja{margin-bottom:18px}
@media(max-width:600px){.fotos{flex-direction:column}.fotos>figure{width:100%}.captura img{height:auto;max-height:500px}.captura.franja{height:70px}}
@media print{.captura{margin:3mm 0;break-inside:avoid}.captura img{height:68mm;max-width:100%}.captura.ancha img{max-height:78mm;width:100%}.captura.franja{height:16mm;margin:3mm 0}.captura.franja img{height:auto}.fotos{display:flex;flex-wrap:nowrap;gap:4mm}.fotos>figure{min-width:0;width:50%}.captura figcaption,.nota-captura{font-size:7.5pt!important}.documento .lead{font-size:12pt}.documento section>p{font-size:9.5pt}}
'''


def doc(nombre,titulo,ss,corto=False):
    h=D.documento(nombre,titulo,ss).replace('29 de octubre de 2026',FECHA).replace('20261029','20261030').replace('revisión 1.1','revisión 1.3')
    h=h.replace('</style>',EXTRA_CSS+('</style>' if not corto else '@media print{.indice-pdf{display:none}.documento section:first-of-type{break-before:auto}}'+ '</style>'))
    if corto:
        h=h.replace('Documentación técnica','Informe de funcionamiento').replace('Arquitectura, datos, integraciones y mantenimiento','Operación, responsabilidades y continuidad')
        # El informe breve inicia directamente en su primera sección, sin índice impreso.
        a=h.index('<div class="indice-pdf">');b=h.index('</div>',a)+len('</div>');h=h[:a]+h[b:]
    return h


def main():
    global SALIDA
    p=argparse.ArgumentParser();p.add_argument('--salida',type=Path,required=True);a=p.parse_args();SALIDA=a.salida;SALIDA.mkdir(parents=True,exist_ok=True);(SALIDA/'capturas').mkdir(exist_ok=True)
    for ruta,_ in ASSETS.values():
        target=SALIDA/'capturas'/Path(ruta).name
        if not target.exists():
            origen=ROOT/'docs/entrega-directivos-20261030/capturas'/Path(ruta).name
            if not origen.exists():origen=Path('/workspace/revisiones')/ruta
            target.write_bytes(origen.read_bytes())
    (SALIDA/'Informe-final-IV-ITSANET.html').write_text(doc('Informe-final-IV-ITSANET.html','Informe final del aplicativo',informe(),True))
    (SALIDA/'Manual-usuarios-IV-ITSANET.html').write_text(doc('Manual-usuarios-IV-ITSANET.html','Manual de usuarios · IV ITSANET',usuarios()))
    inv=M.B.inventario();M.FECHA=FECHA
    secciones=M.secciones(inv,M.diccionario())
    for i,(key,title,body) in enumerate(secciones):
        if key=='infraestructura':body+='<h3>Gestión de recursos y validación simultánea</h3>'+recursos()+'<p>El consumo exclusivo del aplicativo y el ahorro de espacio no se midieron. La captura de disco del 27/10 es del servidor compartido. El número de usuarios concurrentes soportado requiere una prueba de carga representativa, con latencia P95, errores, conexiones SQL y CPU/RAM/IO observados.</p>'
        if key=='evidencias':body+='<div class="fotos dos">'+foto('movil')+foto('camara')+'</div><p class="nota-captura">Interfaz de pruebas con datos sintéticos, v69/v64.</p>'
        if key=='google':body+=foto('correo','ancha')+'<p class="nota-captura">Selección independiente de documentos en interfaz de pruebas v65.</p>'
        if key=='configuracion':body+=foto('admin','ancha')+'<p class="nota-captura">Administración de pruebas v42; los campos secretos no contienen credenciales.</p>'
        secciones[i]=(key,title,body)
    (SALIDA/'Manual-tecnico-IV-ITSANET.html').write_text(doc('Manual-tecnico-IV-ITSANET.html','Manual técnico · IV ITSANET',secciones))
    correo='''Asunto: Entrega de IV ITSANET | Manuales e informe final

Estimados,

Comparto la documentación final de IV ITSANET (Ingreso & Validación Itsanet), aplicativo en operación para la recepción y validación física de mercadería desde computador y handheld.

La solución integra el registro de recepciones, carga del packing list, conteo por SKU y ubicación, seguimiento del avance por operario y registro de novedades con evidencia. El supervisor puede revisar cantidades, carpetas y fotografías finales, preparar los informes y gestionar su envío al ejecutivo de cuenta. La administración mantiene usuarios, permisos, catálogo e integraciones, con seguimiento de procesos y pendientes.

Adjunto el informe final y los manuales técnico y de usuarios, con capturas y responsabilidades por rol. Se documentan la arquitectura Apache, FastAPI/Uvicorn y MySQL, las evidencias en Drive, la gestión del disco, la actualización de vistas y el mantenimiento. La presentación interactiva complementa el recorrido de uso.

Agradezco al equipo de Ingresos, Inventarios y Slotting por su apoyo en las pruebas y en la definición del flujo de trabajo. Su participación ha sido clave para ajustar la herramienta a la operación diaria.

Quedo atento a las observaciones de cierre y a la coordinación de la continuidad y mantenimiento del aplicativo.

Documentación y presentación: https://github.com/brantos102/IV_ITSANET/tree/desarrollo-local/docs/entrega-directivos-20261030

Saludos cordiales,
[Nombre y cargo]
'''
    (SALIDA/'Correo-entrega-IV-ITSANET.txt').write_text(correo)
    print(json.dumps({'salida':str(SALIDA),'documentos':3,'capturas':len(ASSETS)}))


if __name__=='__main__':main()
