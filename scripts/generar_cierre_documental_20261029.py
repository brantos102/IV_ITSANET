"""Documentación de demostración, privacidad y medición. Sin acceso a producción."""
from pathlib import Path
import importlib.util
import base64
import argparse
import json
import xml.etree.ElementTree as X

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('operativa',ROOT/'scripts/generar_presentacion_operativa_final.py')
S=importlib.util.module_from_spec(s);s.loader.exec_module(S)
M=S.M;T,L,C,K=M.T,M.L,M.C,S.K
FECHA='29 de octubre de 2026'


def privacidad():
    return [
    ('marco','1. Marco de protección de datos personales en Ecuador',
     '<p>IV ITSANET trata identidades de usuarios, correo, autoría y fechas de trabajo. Las fotografías pueden contener datos personales si permiten identificar personas. SKU y cantidades de mercadería no son necesariamente datos personales por sí solos, aunque son información operativa que debe protegerse.</p>'+
     T(['Referencia','Aplicación'],[['Constitución de la República, art. 66 numeral 19','Protección de datos personales y decisión sobre su uso.'],['Ley Orgánica de Protección de Datos Personales (LOPDP)','Quinto Suplemento del Registro Oficial 459, 26/05/2021. Principios, bases de legitimación, derechos, seguridad y transferencias.'],['Reglamento General de la LOPDP, Decreto Ejecutivo 904','Tercer Suplemento del Registro Oficial 435, 13/11/2023. Desarrollo reglamentario.'],['Autoridad de control: Superintendencia de Protección de Datos Personales (SPDP)','Revisar resoluciones, criterios y disposiciones vigentes aplicables a la organización.']])+
     '<p>La ubicación en Quito no limita la aplicación nacional de este marco. Este documento describe controles técnicos y tareas de gobierno; no certifica cumplimiento integral ni sustituye el análisis del responsable del tratamiento y su asesoría especializada.</p>'+
     '<p>La consulta de los portales oficiales fue bloqueada por el entorno de generación. No se verificó la vigencia consolidada de resoluciones complementarias al 29/10/2026. Antes de aprobar la entrega normativa, contrastar el texto y normativa vigente en <a href="https://www.registroficial.gob.ec/">Registro Oficial</a> y <a href="https://spdp.gob.ec/">SPDP</a>.</p>'),
    ('controles','2. Controles implementados y evidencia técnica',
     T(['Control','Implementación de referencia','Límite / verificación'],[['Acceso por roles','OPERADOR, SUPERVISOR y ADMIN; comprobación en API.','Asignar permisos mínimos y revisar cuentas reales.'],['Credenciales','PBKDF2-HMAC-SHA256 con sal; cookie de sesión HttpOnly / SameSite=Lax.','Comprobar Secure y esquema HTTPS efectivo; no se acredita MFA.'],['Integraciones','Tokens cifrados con Fernet en SQL; clave externa protegida.','Esto no significa que toda la base o todo el disco estén cifrados.'],['Transporte','URL HTTPS publicada por Apache.','Verificar certificado vigente y confianza en handheld; revisar exposición de 3002.'],['Trazabilidad','Usuario, eventos, fechas, motivo de corrección y procesos.','No es registro WORM/inmutable frente al administrador SQL.'],['Archivos y permisos','Identidad de archivo, SHA-256 y copia Drive con checksum confirmado.','Verificar permisos reales de carpetas y destinatarios; un enlace no concede autorización por sí mismo.'],['Mediciones compartidas','Exportador con lista cerrada; omite usuario, SKU, recepción y referencias.','Persisten fechas y datos operativos agregables; tratar el JSON como información interna.']])+
     '<p>Fuentes: app/security.py, app/db.py, app/services/integraciones.py, archivos.py, google_drive_api.py y procesos.py. El inventario del servidor es evidencia compartida; la configuración efectiva debe conservarse en el control de infraestructura.</p>'),
    ('obligaciones','3. Acciones organizativas por acreditar',
     T(['Materia','Acción y evidencia pendiente'],[['Responsable y encargados','Identificar la persona jurídica que decide fines/medios y los proveedores que tratan datos por su cuenta; formalizar responsabilidades.'],['Finalidad y legitimación','Documentar finalidad de validación, auditoría y evidencias, categorías de titulares y base jurídica por tratamiento. No asumir consentimiento general como única base.'],['Información y derechos','Aviso de privacidad, destinatarios y conservación; canal y procedimiento de acceso, rectificación, eliminación y demás derechos aplicables. El flujo de derechos no está acreditado por la interfaz actual.'],['Minimización','Fotografiar mercadería; evitar rostros, identificaciones y pantallas ajenas. Limitar campos, exportaciones y acceso a evidencia.'],['Conservación','Aprobar plazos por categoría y obligaciones contractuales/legales; eliminación controlada en MySQL, servidor, Drive y respaldos. No se acredita borrado automático por plazos.'],['Análisis de riesgo','Evaluar amenazas, medidas y proporcionalidad; determinar si corresponde evaluación de impacto o delegado según la normativa aplicable.'],['Proveedores y transferencias','Revisar contrato, configuración, ubicación efectiva y mecanismos de transferencia de Google/otros proveedores.'],['Incidentes','Procedimiento de detección, contención, evaluación y notificación con responsables y plazos legales vigentes verificados.'],['Continuidad y accesos','Respaldos, ensayo de restauración, registro de revisión de usuarios y política de privilegios.']])+
     '<p>Estas acciones requieren evidencia institucional; no se marcan como cumplidas por existir Apache, MySQL o una conexión HTTPS.</p>'),
    ('google','4. Datos corporativos y servicios Google',
     '<p>Los datos operativos y metadatos se conservan en MySQL del servidor corporativo. Las evidencias e informes se copian a Google Drive y el correo se entrega mediante Gmail autorizado. Por tanto, no es correcto afirmar que toda la información permanece exclusivamente en el servidor o en Ecuador.</p>'+
     L('Inventariar qué datos se envían a Drive/Gmail y para qué finalidad.','Determinar las entidades proveedoras y condiciones contractuales aplicables, roles de tratamiento y subencargados.','Verificar ubicación efectiva y transferencias internacionales; documentar la base y salvaguardas que correspondan. No asumir residencia local por usar una cuenta corporativa.','Configurar acceso nominal o de grupos autorizados, revisar enlaces compartidos y evitar exposición pública injustificada.','Conservar permisos, trazabilidad de entregas y procedimiento de revocación/retención.','Conservar la clave de cifrado en respaldo protegido; no publicarla ni incluir tokens en presentaciones.')),
    ('presentacion','5. Demostraciones, capturas y aprobación',
     '<p>Las capturas incluidas muestran la interfaz del código en pruebas con información sintética. No constituyen evidencia de una operación productiva de hoy. Una captura productiva adicional debe revisarse antes de compartir para retirar datos personales, correos, usuarios, clientes y referencias que no sean necesarios.</p>'+
     '<p>Para la presentación: mostrar primero pantallas sin credenciales, usar una cuenta de prueba por rol, desactivar notificaciones visibles y no grabar datos identificables sin la autorización institucional y base correspondiente. El archivo HTML procesa el JSON y las capturas cargadas localmente; no los envía a un servicio remoto.</p>'+
     '<p>Cierre del control: registrar fecha de revisión, responsable del tratamiento, revisión técnica, revisión de normativa complementaria, acciones pendientes y aprobación que corresponda. No se inventan firmas ni se atribuye certificación a este expediente.</p>')]


COMANDO='''cd ~/bryan/IV_ITSANET
sudo systemd-run --quiet --wait --pipe --collect \\
  --unit="iv-itsanet-medicion-$(date +%s)" --uid="$(id -un)" \\
  --property="WorkingDirectory=$PWD" \\
  --property=EnvironmentFile=/etc/iv-itsanet.env \\
  "$PWD/.venv/bin/python" \\
  "$HOME/bryan/medicion-IV-ITSANET/exportar_mediciones_presentacion.py" \\
  --desde "2026-10-28T08:00" --hasta "2026-10-28T18:00" \\
  --salida "$HOME/bryan/medicion-IV-ITSANET/mediciones-20261028.json"'''


def guia():
    return [
    ('json','1. Obtener y cargar el JSON real',
     '<p>El JSON del monitor contiene eventos de procesos. No es un archivo Excel convertido a JSON ni contiene el tiempo total que tarda un operario en contar. La presentación utiliza duracionMs de los intentos FOTO COPIADA para calcular sus percentiles.</p>'+
     '<h3>Opción A: navegador con sesión ADMIN</h3>'+L('Entrar a https://apps.flexnetuio.com:8443/app/ con la cuenta ADMIN autorizada.','Abrir en otra pestaña: https://apps.flexnetuio.com:8443/api/operacion/procesos?limite=100 . No escribir credenciales en la URL.','Si devuelve JSON, guardar con Ctrl+S como monitor.json (archivo completo). Alternativa: F12 → Red/Network → abrir el monitor → seleccionar procesos → Copiar respuesta y guardar como texto UTF-8 con extensión .json.','No guardar ni compartir un HAR, cabeceras, cookies o tokens. Si devuelve 401/403, revisar sesión/rol; no desactivar controles.','En la diapositiva Rendimiento observado, pulsar Seleccionar archivo y elegir monitor.json. Se procesa localmente. El monitor devuelve solo una muestra limitada de eventos recientes.')+
     '<h3>Opción B: periodo definido desde VS Code conectado al servidor</h3><p>Descomprimir el paquete en el PC. En el Explorador de VS Code remoto, crear <code>/home/enicolalde/bryan/medicion-IV-ITSANET</code> y cargar allí únicamente <code>exportar_mediciones_presentacion.py</code>. No reemplazar archivos de la aplicación.</p>'+C(COMANDO)+
     '<p>Cambiar las fechas al intervalo real: hora Ecuador, inicio inclusivo y fin exclusivo; máximo 31 días. Confirmar el WorkingDirectory si el servicio usa otra ruta. Se crea un proceso transitorio de exportación con el entorno protegido y el usuario de la terminal; no reinicia iv-itsanet, Apache ni MySQL. El script abre una transacción SQL READ ONLY, aplica límite/timeout y escribe solo el JSON indicado con permiso 0600. No sobrescribe un archivo existente.</p>'+
     '<p>En el Explorador remoto de VS Code: clic derecho sobre el JSON → Descargar. Cargarlo en la diapositiva. Si <code>truncado=true</code>, reducir el periodo; no presentar la muestra como el total. Una carga pesada puede consumir recursos de lectura: usar periodos pequeños fuera del pico.</p>'),
    ('tiempos','2. Qué representan los tiempos y cómo compararlos',
     T(['Medición','Interpretación'],[['FOTO COPIADA / duracionMs','Duración del intento exitoso de verificación/copia/organización. Excluye captura, espera en cola y el ciclo completo de recepción.'],['Mediana y P95','Percentil por rango más próximo sobre intentos válidos; no son garantía de velocidad ni tiempo máximo.'],['Reintentos / organización','Un mismo archivo puede generar varias operaciones exitosas; el tamaño de muestra cuenta intentos, no fotos únicas.'],['Errores y ventanas','El exportador incluye eventos de foto/correo, pero los percentiles usan solo FOTO COPIADA con duración válida. Reportar sesgo y periodo.'],['Conteo / correo completo','No existe un cronómetro integral acreditado en el código para todo el flujo. Medir inicio/fin con protocolo homogéneo.']])+
     '<p>Para comparar revisiones anteriores, completar la plantilla CSV incluida: tarea, registros, minutos anteriores, minutos actuales, personal y condiciones. Usar comas como separador y evitar comas o saltos de línea dentro de los textos de esta plantilla simple. Conservar los inicios/finales y evidencia del cronometraje por separado. Medir la misma tarea, volumen y criterio de término. Separar conteo, evidencia y elaboración de informe. Los minutos también pueden ingresarse manualmente en la diapositiva; la fórmula no prueba causalidad.</p>'+
     '<p>No se incluyeron resultados productivos: todavía no se recibió un JSON real ni los tiempos históricos del responsable. Los campos permanecen vacíos hasta su carga.</p>'),
    ('movil','3. Preparar la demostración real en móvil o handheld',
     L('Elegir un entorno de pruebas con SQL y carpeta Drive separados. Si se demuestra en producción, obtener autorización para una recepción claramente identificada de demostración, sin reutilizar recepciones/correos de clientes. Guardar una demo sí escribe datos.','Preparar cuenta OPERADOR y cuenta SUPERVISOR/ADMIN separadas. Usar un SKU y packing de prueba concordantes. No mostrar contraseñas al público.','Conectar el dispositivo a la red autorizada y abrir https://apps.flexnetuio.com:8443/app/ en Chrome compatible. Verificar certificado confiable y permiso de cámara. No omitir alertas TLS.','Entrar con el operario, seleccionar recepción y Validar. El escáner físico debe enviar el código como teclado al campo de lectura; comprobar el sufijo Enter si el equipo lo requiere.','Alternativa: pulsar Cámara para leer el código. El lector usa BarcodeDetector cuando está disponible y respaldo ZXing local. Escanear solo consulta; el conteo se guarda al pulsar Guardar conteo.','Registrar cantidad/pallet/posición y condición. Para PNC, registrar la cantidad afectada y observación; adjuntar la foto de la mercadería en Fotos para este conteo o el flujo de evidencia correspondiente.','Guardar y revisar bitácora. En supervisión comprobar las unidades, PNC, estado de copia Drive y enlace; luego revisar el informe y sus adjuntos. No enviar un correo real de cliente durante la demo.')),
    ('pantalla','4. Mostrar el dispositivo en vivo al público',
     '<p>La presentación dispone de un botón que abre la URL real en otra pestaña. El HTML descargado no puede reflejar por sí solo la pantalla autenticada de otro dispositivo ni habilitar la cámara de ese handheld.</p>'+
     T(['Alternativa','Uso y límite'],[['Compartir pantalla desde el móvil','Utilizar la herramienta corporativa aprobada (por ejemplo, compartir pantalla en la reunión desde Android). Iniciar sesión antes y ocultar notificaciones; compartir solo lo necesario.'],['Duplicación por hardware','HDMI/USB-C o proyección compatible, si el handheld y la política de equipos lo permiten. No todos los equipos soportan salida de video.'],['PC en modo móvil','Chrome F12 → barra de dispositivos permite mostrar el diseño responsive. No acredita el lector físico ni la cámara del handheld real.'],['Depuración por USB','Solo mediante un procedimiento aprobado para el equipo; no se necesita activarla para el uso operativo normal.']])+
     '<p>Guion breve: lector físico → ficha del SKU → cantidad/ubicación → novedad PNC → fotografía → guardado → bitácora → revisión del supervisor. Si la cámara falla, consultar <code>/app/diagnostico-camara.html</code>, permisos y certificado; conservar los registros ya guardados.</p>'),
    ('capturas','5. Capturas y privacidad durante la exposición',
     '<p>La galería incorporada contiene capturas de interfaz obtenidas previamente en pruebas con datos sintéticos (v64/v69). Están etiquetadas como pruebas. Las capturas actuales pueden cargarse desde el botón local de la presentación; no se publican ni se incorporan automáticamente al HTML descargado.</p>'+
     '<p>Antes de cargar capturas actuales, ocultar datos de personas, correos, clientes y elementos ajenos a la finalidad. Las imágenes se mantienen en memoria de la página y se descartan al recargar. No enviarlas al repositorio sin revisión. El paquete no contiene contraseñas, tokens ni JSON productivo.</p>')]


def documento(nombre,titulo,ss):
    inv=M.B.inventario()
    viejo=M.secciones
    M.secciones=lambda *args:ss
    try: h=M.manual(inv,M.diccionario())
    finally:M.secciones=viejo
    return h.replace('Manual técnico',titulo).replace('Manual-tecnico-ITSANET-20261028.html',nombre).replace('20261028','20261029').replace('28 de octubre de 2026',FECHA)


def flujos_roles(path):
    S.diagramas(path);tree=X.parse(path);file=tree.getroot()
    for rol,etapas in [
      ('Operario',[
       ('Acceder con cuenta OPERADOR','operadores / sesiones; autorización en API'),
       ('Seleccionar recepción y embarque','Interfaz validar.html; contexto de origen'),
       ('Escanear código o usar Cámara','camara.js: BarcodeDetector / ZXing; consultar SKU'),
       ('Revisar presencia y datos esperados','app_presencias / app_skus'),
       ('Ingresar cantidad, pallet y posición','Cero explícito con observación; validación de versión'),
       ('Registrar condición y novedad','Cantidad PNC / observación / evidencia cuando aplica'),
       ('Capturar imagen y guardar','archivos.py / app_evidencias; cola app_copias_drive'),
       ('Guardar conteo y revisar bitácora','app_eventos; app_skus; reintento con la misma identidad'),
       ('Informar pendiente o solicitar corrección','Mantener trazabilidad; escalar al supervisor')]),
      ('Supervisor',[
       ('Acceder y revisar jornada','Rol SUPERVISOR; catálogo/avisos según permisos'),
       ('Revisar recepción y avance','Orígenes, cantidades, bultos, responsables y presencia'),
       ('Revisar diferencias y PNC','Registro específico, pallet/posición y evidencia vinculada'),
       ('Gestionar correcciones autorizadas','gestion.py / correcciones; motivo y evento compensatorio'),
       ('Comprobar fotos y enlaces','Pendientes Drive; responsable; reintento o escalar a ADMIN'),
       ('Preparar y revisar documentos','app_informes; cantidades numéricas; descarga para validar'),
       ('Seleccionar archivos y nombres finales','Sin mezclar grupos; revisar destinatarios y correo original'),
       ('Enviar con Gmail autorizado','gestion.py → entregas.py → Google API'),
       ('Confirmar entrega y cierre','app_entregas; ante pendiente revisar Enviados, sin duplicar')])]:
        d=X.SubElement(file,'diagram',name='Flujo '+rol,id='rol-'+rol)
        g=X.SubElement(d,'mxGraphModel',grid='1',gridSize='10',page='1',pageWidth='1800',pageHeight='2200');r=X.SubElement(g,'root');X.SubElement(r,'mxCell',id='0');X.SubElement(r,'mxCell',id='1',parent='0')
        for i,(a,b) in enumerate(etapas):
            c=X.SubElement(r,'mxCell',id='n'+str(i),value=str(i+1)+'. '+a+'\n'+b,vertex='1',parent='1',style='rounded=1;whiteSpace=wrap;html=0;fillColor=#eef4ff;strokeColor=#225de2;fontSize=16;spacing=14;')
            X.SubElement(c,'mxGeometry',x='100',y=str(80+i*170),width='880',height='110',**{'as':'geometry'})
            if i:
                e=X.SubElement(r,'mxCell',id='e'+str(i),edge='1',source='n'+str(i-1),target='n'+str(i),parent='1',style='edgeStyle=orthogonalEdgeStyle;endArrow=block;');X.SubElement(e,'mxGeometry',relative='1',**{'as':'geometry'})
        c=X.SubElement(r,'mxCell',id='nota',value=('Registro de consulta no equivale a guardado.\nSi hay conflicto, revisar versión antes de repetir.\nSi falta red, conservar borrador y evidencia pendiente.' if rol=='Operario' else 'Permisos se comprueban en el servidor.\nADMIN configura usuarios, OAuth y monitor.\nEl supervisor no equivale a root ni posee todos los permisos ADMIN.'),vertex='1',parent='1',style='whiteSpace=wrap;fillColor=#fff4dc;strokeColor=#d6b656;fontSize=16;spacing=16;');X.SubElement(c,'mxGeometry',x='1080',y='220',width='500',height='250',**{'as':'geometry'})
    X.indent(file);tree.write(path,encoding='utf-8',xml_declaration=True)


JS=r'''
const imgInput=document.querySelector('#capturas-locales');
imgInput.onchange=async e=>{const host=document.querySelector('#galeria-local');host.replaceChildren();for(const f of [...e.target.files].slice(0,4)){if(!/^image\/(png|jpeg|webp)$/.test(f.type)||f.size>8*1024*1024)continue;const u=URL.createObjectURL(f),img=document.createElement('img');img.src=u;img.alt='Captura seleccionada localmente por el expositor';img.className='captura';img.onclick=()=>{document.querySelector('#img-ampliada').src=u;document.querySelector('#zoom-captura').showModal();};host.append(img);}document.querySelector('#estado-capturas').textContent=host.children.length+' capturas locales en memoria; no se publican ni se incluyen en la descarga HTML.';};
document.querySelectorAll('.captura[data-origen]').forEach(img=>img.onclick=()=>{document.querySelector('#img-ampliada').src=img.src;document.querySelector('#zoom-captura').showModal();});
document.querySelector('#cerrar-zoom').onclick=()=>document.querySelector('#zoom-captura').close();
document.querySelector('#historico').onchange=async e=>{try{const f=e.target.files[0];if(!f||f.size>1024*1024)throw Error('Selecciona un CSV menor de 1 MB.');const lines=(await f.text()).replace(/^\uFEFF/,'').trim().split(/\r?\n/);if(lines[0].trim()!=='tarea,registros,minutos_antes,minutos_actual,personal,condiciones')throw Error('Utiliza la plantilla CSV incluida, separada por comas.');const rows=lines.slice(1).map(l=>l.split(','));const select=document.querySelector('#fila-historica');select.replaceChildren();rows.forEach((r,i)=>{if(r.length!==6)return;const n=Number(r[1]),a=Number(r[2]),b=Number(r[3]);if(!Number.isInteger(n)||n<=0||!Number.isFinite(a)||a<=0||!Number.isFinite(b)||b<=0)return;const o=document.createElement('option');o.textContent=r[0]||'Medición '+(i+1);o.value=JSON.stringify([n,a,b]);select.append(o);});if(!select.options.length)throw Error('No hay filas completas con mediciones positivas. No se rellenan valores ausentes.');select.onchange=()=>{const [n,a,b]=JSON.parse(select.value);document.querySelector('#registros').value=n;document.querySelector('#min-antes').value=a;document.querySelector('#min-ahora').value=b;calcular();};select.onchange();document.querySelector('#estado-historico').textContent=select.options.length+' comparaciones cargadas del archivo local.';}catch(err){document.querySelector('#estado-historico').textContent=err.message;}};
// La copia descargada excluye capturas y resultados cargados localmente.
document.querySelector('#descargar').onclick=()=>{const d=document.documentElement.cloneNode(true);d.querySelector('#galeria-local').replaceChildren();d.querySelector('#img-ampliada').removeAttribute('src');d.querySelector('#zoom-captura').removeAttribute('open');d.querySelector('#fila-historica').replaceChildren();d.querySelectorAll('input').forEach(x=>x.removeAttribute('value'));d.querySelectorAll('#met-n,#met-p50,#met-p95').forEach(x=>x.textContent='—');d.querySelector('#met-estado').textContent='Sin mediciones productivas cargadas.';d.querySelector('#detalle-muestra').textContent='No hay muestra cargada.';d.querySelector('#resultado-tiempo').textContent='Ingresa mediciones comparables para calcular tiempo por registro y diferencia porcentual.';d.querySelector('#estado-historico').textContent='Sin comparaciones cargadas.';d.querySelector('#estado-capturas').textContent='Sin capturas locales cargadas.';const u=URL.createObjectURL(new Blob(['<!doctype html>\n'+d.outerHTML],{type:'text/html;charset=utf-8'})),a=document.createElement('a');a.href=u;a.download='Presentacion-IV-ITSANET-20261029.html';a.click();setTimeout(()=>URL.revokeObjectURL(u),4000);};
document.querySelector('#mediciones').addEventListener('change',async e=>{try{const f=e.target.files[0];if(!f||f.size>10*1024*1024)return;const j=JSON.parse(await f.text());const periodo=j.periodo?('Periodo Ecuador: '+j.periodo.desde+' → '+j.periodo.hastaExclusivo+' (fin exclusivo). '):'Periodo no declarado en el JSON; muestra reciente del monitor. ';document.querySelector('#detalle-muestra').textContent=periodo+(j.truncado?'ATENCIÓN: muestra truncada, reducir el periodo. ':'')+'Fuente: '+(j.fuente||'monitor de procesos')+'.';}catch{document.querySelector('#detalle-muestra').textContent='No se pudo interpretar la muestra.';}});
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--salida',type=Path,required=True);a=p.parse_args();a.salida.mkdir(parents=True,exist_ok=True)
    M.FECHA=FECHA
    inv=M.B.inventario();inv.update(fecha='2026-10-29',tablasDetalle=M.diccionario())
    manual=M.manual(inv,inv['tablasDetalle']).replace('20261028','20261029').replace('revisión 1.1','revisión 1.2').replace('Manual-tecnico-ITSANET-20261029.html','Manual-tecnico-IV-ITSANET-20261029.html')
    (a.salida/'Manual-tecnico-IV-ITSANET-20261029.html').write_text(manual)
    (a.salida/'Guia-demostracion-y-mediciones-IV-ITSANET.html').write_text(documento('Guia-demostracion-y-mediciones-IV-ITSANET.html','Guía de demostración y mediciones',guia()))
    (a.salida/'Proteccion-datos-Ecuador-IV-ITSANET.html').write_text(documento('Proteccion-datos-Ecuador-IV-ITSANET.html','Protección de datos personales · Ecuador',privacidad()))
    (a.salida/'Inventario-tecnico-IV-ITSANET.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2))
    base=S.slides()
    gal=''
    for path,caption in [('v69/Cantidad-movil-sin-flechas.png','Validación móvil · pruebas v69'),('v64/camara-390x844.png','Captura de evidencia · pruebas v64'),('v69/Cero-guardado-escritorio.png','Ficha de registro · pruebas v69')]:
        archivo=Path(path).name
        raw=a.salida/'capturas'/archivo
        if not raw.exists():
            origen=ROOT/'docs/entrega-final-20261029/capturas'/archivo
            if not origen.exists():origen=Path('/workspace/revisiones')/path
            raw.parent.mkdir(parents=True,exist_ok=True);raw.write_bytes(origen.read_bytes())
        data='data:image/png;base64,'+base64.b64encode(raw.read_bytes()).decode()
        gal+='<figure><img class="captura" data-origen="pruebas" src="'+data+'" alt="'+caption+'"><figcaption>'+caption+'</figcaption></figure>'
    gallery=('Interfaz en PC y handheld','Capturas de la aplicación en pruebas; pulsa para ampliar', '<div class="galeria">'+gal+'</div><label>Cargar capturas actuales revisadas (solo en esta página) <input id="capturas-locales" type="file" multiple accept="image/png,image/jpeg,image/webp"></label><p class="mini" id="estado-capturas">Sin capturas locales cargadas.</p><div id="galeria-local" class="galeria"></div><p class="mini">Datos sintéticos. Estas capturas no representan una recepción productiva actual.</p>')
    roles=('Trabajo por roles','El operario registra; el supervisor revisa y entrega','<div class="grid dos">'+K('Operario','Acceso → recepción → escaneo → cantidad/ubicación → novedad/foto → guardar → revisar bitácora.')+K('Supervisor','Revisar avance → diferencias/PNC → evidencia y enlaces → corrección autorizada → documentos → entrega confirmada.')+'</div><div class="banda">ADMIN mantiene usuarios, configuración e integraciones y consulta el monitor. Los permisos efectivos se comprueban en API.</div><p>Diagramas editables separados: Flujo Operario y Flujo Supervisor.</p>')
    live=('Demostración en vivo','Mostrar el equipo real y el flujo de evidencia','<div class="grid dos">'+K('Desde el dispositivo','Abrir la URL corporativa, entrar como operario y mostrar recepción de prueba, escaneo y registro de novedad con foto.')+K('En la pantalla de la reunión','Compartir pantalla del móvil con la herramienta corporativa aprobada o duplicación compatible. El modo móvil de PC muestra diseño, no hardware real.')+'</div><a class="boton" href="https://apps.flexnetuio.com:8443/app/" target="_blank" rel="noopener noreferrer">Abrir aplicación real</a><div class="banda">Preparar entorno de pruebas o recepción DEMO autorizada. Escanear consulta; Guardar escribe datos. No enviar a destinatarios de clientes durante la demostración.</div><p class="mini">Certificado confiable y permiso de cámara. Guía detallada y diagnóstico de cámara incluidos en el paquete.</p>')
    legal=('Protección de datos en Ecuador','Controles técnicos y obligaciones de la organización','<div class="grid">'+K('Aplicado en código','Roles, permisos, hash de credenciales, sesiones, trazabilidad y tokens cifrados.')+K('Infraestructura','HTTPS y servidor corporativo; verificar certificado, red, privilegios y respaldos efectivos.')+K('Gobierno del dato','Finalidad/base jurídica, aviso, derechos, retención, riesgo, proveedores y respuesta a incidentes.')+'</div><div class="banda">LOPDP + Reglamento General. Drive y Gmail implican tratamiento externo: no toda la información permanece en el servidor ni se acredita residencia exclusiva en Ecuador.</div><p class="mini">El documento de protección de datos distingue controles y pendientes. No constituye certificación de cumplimiento; revisar resoluciones SPDP vigentes.</p>')
    old=base[7];base[7]=(old[0],old[1],old[2]+'<p class="mini" id="detalle-muestra">No hay muestra cargada.</p>')
    old=base[8];base[8]=(old[0],old[1],old[2]+'<label>Cargar CSV de comparación <input type="file" id="historico" accept=".csv,text/csv"></label><select id="fila-historica" aria-label="Comparación histórica"></select><p class="mini" id="estado-historico">Sin comparaciones cargadas.</p>')
    ss=[base[0],roles,base[1],base[2],gallery,base[3],base[4],base[5],base[6],base[7],base[8],live,legal,base[9],base[10],base[11]]
    M.slides=lambda:ss
    logo='data:image/png;base64,'+base64.b64encode((ROOT/'firebase/public/logo-itsa.png').read_bytes()).decode()
    h=M.presentacion(logo).replace('Arquitectura y mantenimiento','Funcionamiento y rendimiento').replace('IV ITSANET · Arquitectura técnica','IV ITSANET · Operación en vivo').replace('20261028','20261029')
    extra_css='.pasos-demo{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}.etapa[aria-pressed=true]{background:#225de2;color:white}.slide input[type=number]{display:block;max-width:100%;width:100%;padding:8px;font:inherit}.metricas strong{font-size:28px;color:#176b79}.galeria{display:flex;gap:15px;justify-content:center;flex-wrap:wrap}.galeria figure{margin:0;text-align:center;flex:1}.captura{height:270px;max-width:100%;object-fit:contain;cursor:zoom-in}.galeria figcaption{font-size:12px}.slide details,.slide label{font-size:13px}dialog{max-width:95vw;max-height:95vh;border:0;border-radius:12px}dialog img{max-width:85vw;max-height:80vh;object-fit:contain}.slide #galeria-local .captura{height:120px}.slide .mini{line-height:1.35}.slide select{max-width:100%}@media(max-width:600px){.galeria{flex-direction:column}.captura{height:auto;max-height:450px}.slide{overflow:visible}}@media print{dialog{display:none!important}.slide .pasos-demo button{display:inline-block}.captura{height:62mm}.slide .galeria{flex-direction:row;flex-wrap:nowrap}.slide input[type=file],.slide #galeria-local{display:none}.slide .mini{font-size:7.5pt}.slide label{font-size:8pt}}'
    h=h.replace('</style>',extra_css+'</style>')
    h=h.replace('</body>','<dialog id="zoom-captura"><button id="cerrar-zoom">Cerrar</button><br><img id="img-ampliada" alt="Captura ampliada"></dialog><script>'+S.EXTRA_JS+'</script><script>'+JS+'</script></body>')
    (a.salida/'Presentacion-IV-ITSANET-20261029.html').write_text(h)
    flujos_roles(a.salida/'IV-ITSANET-Arquitectura-y-flujos-20261029.drawio')
    (a.salida/'Plantilla-comparacion-tiempos.csv').write_text('tarea,registros,minutos_antes,minutos_actual,personal,condiciones\nConteo,,,,,\nEvidencia,,,,,\nInforme,,,,,\n')
    (a.salida/'exportar_mediciones_presentacion.py').write_bytes((ROOT/'scripts/exportar_mediciones_presentacion.py').read_bytes())
    (a.salida/'Comando-exportacion-servidor.txt').write_text(COMANDO+'\n')
    print(json.dumps({'salida':str(a.salida),'slides':len(ss),'diagramas':7}))


if __name__=='__main__':main()
