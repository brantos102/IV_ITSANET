"""Genera documentación HTML autónoma desde contenido revisado e inventario del código.

No importa la aplicación, no consulta bases ni credenciales y no contacta Google.
"""
from pathlib import Path
import ast
import html
import json
import re

RAIZ=Path(__file__).resolve().parents[1]
SALIDA=RAIZ/'docs'/'entrega-v67'
E=html.escape


def tabla(cabeceras,filas):
    return '<div class="tabla"><table><thead><tr>'+''.join('<th>'+E(c)+'</th>' for c in cabeceras)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in f)+'</tr>' for f in filas)+'</tbody></table></div>'


def lista(*items):return '<ul>'+''.join('<li>'+x+'</li>' for x in items)+'</ul>'


def pasos(*items):return '<ol>'+''.join('<li>'+x+'</li>' for x in items)+'</ol>'


def nota(t):return '<aside class="nota">'+t+'</aside>'


def codigo(t):return '<pre><code>'+E(t)+'</code></pre>'


def inventario():
    modelos=[];rutas=[]
    for n in ast.parse((RAIZ/'app/models.py').read_text()).body:
        if isinstance(n,ast.ClassDef):
            for x in n.body:
                if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__tablename__' for t in x.targets):
                    modelos.append({'modelo':n.name,'tabla':ast.literal_eval(x.value)})
    for archivo in sorted((RAIZ/'app/routers').glob('*.py')):
        arbol=ast.parse(archivo.read_text());prefijo=''
        for n in arbol.body:
            if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='APIRouter':
                prefijo=next((ast.literal_eval(k.value) for k in n.value.keywords if k.arg=='prefix'),'')
        for n in arbol.body:
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for d in n.decorator_list:
                    if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and isinstance(d.func.value,ast.Name) and d.func.value.id=='router' and d.args and isinstance(d.args[0],ast.Constant):
                        rutas.append({'metodo':d.func.attr.upper(),'ruta':prefijo+d.args[0].value,'fuente':str(archivo.relative_to(RAIZ)),'funcion':n.name})
    requisitos=[x for x in (RAIZ/'requirements.txt').read_text().splitlines() if re.match(r'^[A-Za-z].*==',x)]
    return {'versionFrontend':'20261023-67','fecha':'2026-10-23','zonaHoraria':'America/Guayaquil',
        'alcance':'Inventario estático del código candidato v67. No acredita instalación ni configuración productiva.',
        'tablas':modelos,'rutas':rutas,'dependenciasPythonDeclaradas':requisitos,
        'dependenciasJSDeclaradas':json.loads((RAIZ/'package.json').read_text())['devDependencies']}


CSS='''
:root{--fondo:#f1f5f9;--papel:#fff;--tinta:#172b45;--muted:#526781;--linea:#dce5ef;--azul:#225de2;--suave:#eef4ff;--nota:#effaf6}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--fondo);color:var(--tinta);font:16px/1.65 system-ui,-apple-system,Arial,sans-serif}a{color:var(--azul);text-underline-offset:3px}header{padding:28px max(22px,calc((100vw - 1320px)/2));background:#102743;color:white}header p{max-width:900px;color:#cfddf2;margin-bottom:0}.sello{color:#9cc5ff;font-size:12px;letter-spacing:1.4px;text-transform:uppercase}h1{font-size:clamp(27px,4vw,42px);line-height:1.15;margin:10px 0}h2{font-size:25px;line-height:1.3}h3{font-size:19px}main{max-width:1320px;margin:26px auto;display:grid;grid-template-columns:260px minmax(0,1fr);gap:26px;padding:0 22px}nav{position:sticky;top:16px;align-self:start;max-height:95vh;overflow:auto;background:var(--papel);padding:18px;border:1px solid var(--linea);border-radius:15px}nav input{width:100%;min-width:0;padding:10px;border:1px solid var(--linea);border-radius:8px;font:inherit;font-size:14px}nav a{display:block;padding:7px 0;line-height:1.4;font-size:14px;text-decoration:none}nav small{display:block;margin:12px 0;color:var(--muted)}.herramientas{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}button{padding:9px 12px;border:1px solid var(--linea);border-radius:8px;background:var(--papel);color:var(--tinta);font:600 13px system-ui;cursor:pointer}button:hover{border-color:var(--azul)}button:focus-visible,a:focus-visible{outline:3px solid #81aaff;outline-offset:3px}.primario{background:var(--azul);color:white;border-color:var(--azul)}.contenido{min-width:0;overflow-wrap:anywhere}section{background:var(--papel);border:1px solid var(--linea);border-radius:16px;padding:28px;margin:0 0 20px;scroll-margin-top:15px}section>h2{margin-top:0}.nota{border-left:4px solid #139575;padding:15px 18px;margin:18px 0;background:var(--nota);border-radius:0 9px 9px 0}.tabla{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:11px;border-bottom:1px solid var(--linea);vertical-align:top}th{background:var(--suave)}code{font:13px/1.5 ui-monospace,Consolas,monospace;overflow-wrap:anywhere;background:var(--suave);padding:2px 4px;border-radius:4px}pre{position:relative;background:#102743;color:#e7f0ff;padding:18px;border-radius:10px;overflow:auto;font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}pre code{background:transparent;color:inherit}li{margin:9px 0}details{margin:12px 0;border:1px solid var(--linea);border-radius:10px;padding:14px}summary{cursor:pointer;font-weight:700}.flujo{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0}.flujo a{background:var(--suave);border:1px solid var(--linea);border-radius:10px;padding:18px;text-decoration:none}.flujo b{display:block}.flujo small{display:block;color:var(--muted);margin-top:6px}.lista-control label{display:flex;gap:10px;align-items:start;border-bottom:1px solid var(--linea);padding:10px 0}.lista-control input{margin-top:6px;flex:none}#estado{min-height:26px;font-size:13px;color:var(--muted)}.evidencia{font-size:12px;color:var(--muted);border-top:1px solid var(--linea);padding-top:12px;margin-top:18px}.hero-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.hero-grid>div{padding:18px;border:1px solid var(--linea);border-radius:12px}.hero-grid b{display:block;font-size:22px}.nada{padding:20px;color:var(--muted)}[hidden]{display:none!important}footer{padding:20px;text-align:center;color:var(--muted);font-size:12px}body.oscuro{--fondo:#0c1727;--papel:#14263d;--tinta:#e6eef8;--muted:#a7b9d1;--linea:#30475f;--azul:#8eb6ff;--suave:#1a3458;--nota:#113f38}body.oscuro .primario{color:#102743}body.oscuro header{background:#10233b}
@media(max-width:850px){main{grid-template-columns:1fr}nav{position:static;max-height:none}.indice{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 12px}section{padding:20px}.flujo{grid-template-columns:1fr 1fr}.hero-grid{grid-template-columns:1fr}h2{font-size:23px}}
@media(max-width:480px){main{padding:0 12px;gap:16px}.flujo{grid-template-columns:1fr}.indice{grid-template-columns:1fr 1fr}td,th{padding:8px}section{padding:18px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{body,body.oscuro{--papel:white;--tinta:black;--muted:#333;--linea:#ccc;--suave:#f4f6f8;--nota:#f4f6f8;background:white;font-size:10pt}header{background:white;color:black;padding:0}header p,.sello{color:#333}main{display:block;max-width:none;margin:0;padding:0}nav,.herramientas,button,footer,.nada{display:none!important}section{border:0;border-radius:0;padding:15px 0;break-before:page}.contenido>section:first-child{break-before:auto}pre{background:#f2f2f2;color:black}.tabla{overflow:visible}table{font-size:9pt}h2,h3{break-after:avoid}.flujo,.hero-grid{break-inside:avoid}a{color:black}details>*{display:block}details:not([open])>*:not(summary){display:block}}
'''

JS='''
const $=s=>document.querySelector(s),secciones=[...document.querySelectorAll('main section')],normalizar=s=>s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
function avisar(t){$('#estado').textContent=t;}
function filtrar(){const q=normalizar($('#buscar').value.trim());let n=0;for(const s of secciones){s.hidden=!!q&&!normalizar(s.textContent).includes(q);if(!s.hidden)n++;const a=document.querySelector('nav a[href="#'+s.id+'"]');if(a)a.hidden=s.hidden;}$('#sin-resultados').hidden=!!n;avisar(n+' secciones visibles.');}
$('#buscar').oninput=filtrar;
$('#limpiar').onclick=()=>{$('#buscar').value='';filtrar();};
$('#tema').onclick=()=>{document.body.classList.toggle('oscuro');avisar('Tema cambiado.');};
$('#expandir').onclick=()=>{document.querySelectorAll('details').forEach(d=>d.open=true);avisar('Detalles desplegados.');};
let antesImpresion;
addEventListener('beforeprint',()=>{antesImpresion=secciones.map(s=>s.hidden);secciones.forEach(s=>s.hidden=false);});
addEventListener('afterprint',()=>{if(antesImpresion)secciones.forEach((s,i)=>s.hidden=antesImpresion[i]);});
$('#imprimir').onclick=()=>window.print();
function descargar(nombre,tipo,contenido){const u=URL.createObjectURL(new Blob([contenido],{type:tipo})),a=document.createElement('a');a.href=u;a.download=nombre;a.click();setTimeout(()=>URL.revokeObjectURL(u),4000);avisar('Descarga iniciada: '+nombre);}
$('#descargar').onclick=()=>{const d=document.documentElement.cloneNode(true);d.querySelectorAll('[hidden]').forEach(e=>{if(e.matches('section,nav a'))e.removeAttribute('hidden');});d.querySelector('#buscar').setAttribute('value','');d.querySelector('#sin-resultados').setAttribute('hidden','');descargar(document.body.dataset.archivo,'text/html;charset=utf-8','<!doctype html>\\n'+d.outerHTML);};
document.querySelectorAll('pre').forEach(pre=>{const b=document.createElement('button');b.textContent='Copiar texto';b.onclick=async()=>{const texto=pre.querySelector('code').textContent;try{await navigator.clipboard.writeText(texto);avisar('Texto copiado.');}catch{const r=document.createRange();r.selectNodeContents(pre.querySelector('code'));getSelection().removeAllRanges();getSelection().addRange(r);avisar('Texto seleccionado. Usa Copiar en tu navegador.');}};pre.after(b);});
const checks=[...document.querySelectorAll('[data-check]')],clave='itsanet-entrega67-'+document.body.dataset.archivo;
function progreso(){avisar(checks.filter(c=>c.checked).length+' de '+checks.length+' comprobaciones marcadas en este navegador. No equivale a aprobación formal.');}
try{const d=JSON.parse(localStorage.getItem(clave)||'[]');checks.forEach(c=>c.checked=d.includes(c.dataset.check));}catch{}
checks.forEach(c=>c.onchange=()=>{try{localStorage.setItem(clave,JSON.stringify(checks.filter(c=>c.checked).map(c=>c.dataset.check)));}catch{}progreso();});
if($('#exportar'))$('#exportar').onclick=()=>descargar('revision-entrega-ITSANET-v67.json','application/json',JSON.stringify({version:67,fecha:new Date().toISOString(),alcance:'Lista de revisión local, sin firma ni aprobación automática',comprobaciones:checks.map(c=>({control:c.parentElement.textContent.trim(),revisado:c.checked}))},null,2));
'''


def documento(archivo,titulo,subtitulo,secciones):
    indice=''.join('<a href="#'+ident+'">'+E(t)+'</a>' for ident,t,_ in secciones)
    cuerpo=''.join('<section id="'+ident+'"><h2>'+E(t)+'</h2>'+contenido+'</section>' for ident,t,contenido in secciones)
    texto='<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+E(titulo)+'</title><style>'+CSS+'</style></head><body data-archivo="'+archivo+'"><header><div class="sello">ITSANET · Entrega v67 · 23 de octubre de 2026 · Ecuador</div><h1>'+E(titulo)+'</h1><p>'+E(subtitulo)+'</p></header><main><nav aria-label="Contenido"><label for="buscar"><b>Buscar en el documento</b></label><input id="buscar" type="search" placeholder="Ej.: Drive, respaldo, PNC"><div class="herramientas"><button id="limpiar">Limpiar</button><button id="tema">Cambiar tema</button></div><div class="indice">'+indice+'</div><div class="herramientas"><button id="expandir">Desplegar detalles</button><button id="imprimir">Imprimir / PDF</button><button class="primario" id="descargar">Descargar HTML</button></div><p id="estado" role="status" aria-live="polite">HTML autónomo. Funciona sin conexión.</p><small>Lectura técnica y operativa. La aceptación productiva se documenta por separado.</small><a href="index.html">Paquete de entrega</a></nav><div class="contenido"><p class="nada" id="sin-resultados" hidden>No hay secciones que coincidan.</p>'+cuerpo+'</div></main><footer>ITSANET IMS · Documentación del código v67. Los datos productivos, credenciales y correos no se incluyen.</footer><script>'+JS+'</script></body></html>'
    (SALIDA/archivo).write_text(texto,encoding='utf-8')


def controles(items):
    return '<div class="lista-control">'+''.join('<label><input type="checkbox" data-check="'+str(i)+'"><span>'+x+'</span></label>' for i,x in enumerate(items))+'</div><p><button id="exportar">Descargar revisión JSON</button></p>'


def tecnico(inv):
    componentes=tabla(['Componente','Implementación verificada','Responsabilidad'],[
        ['Interfaz operativa','HTML, CSS y módulos JavaScript en <code>firebase/public</code>. Servidos en <code>/app/</code>.','Recepciones, conteos, evidencias, informes, correo, usuarios y paneles; uso móvil y escritorio.'],
        ['Backend','FastAPI + Uvicorn; <code>app/main.py</code> y <code>app/routers</code>.','Autenticación, permisos, transacciones, validaciones, consultas y trabajadores de segundo plano.'],
        ['Persistencia','SQLAlchemy; MySQL vía PyMySQL para operación corporativa. SQLite para pruebas/uso local por defecto.','Recepciones, líneas, eventos, usuarios, agregados, referencias de archivos, colas y auditoría.'],
        ['Archivos','Pillow, SHA-256 y almacenamiento privado bajo <code>VAL_DATA_DIR</code>.','Fotos e informes locales; miniaturas privadas; relación con Drive e integridad.'],
        ['Integración Google central','OAuth web + PKCE; Drive API y Gmail API desde el servidor.','Drive operativo común y correo propio de cada supervisor. No exige un Apps Script por persona.'],
        ['Compatibilidad','Apps Script firmado por HMAC; Firebase Hosting/Firestore y API anterior presentes en el repositorio.','Vías anteriores/alternativas; su presencia en código no acredita que intervengan en el despliegue corporativo actual.'],
        ['Impresión','JsBarcode CODE128, HTML/PDF, ZPL y agente opcional de PC puente.','Etiquetas de bulto y selección por rangos; el agente requiere configuración de estación.'],
        ['Documentos','SheetJS en navegador y openpyxl en procesos Python; jsPDF para salidas que lo utilizan.','Excel/CSV/PDF según flujo. Bibliotecas de navegador distribuidas localmente en <code>vendor/</code>.']])
    red=tabla(['Tramo','Dirección / protocolo','Estado de la evidencia'],[
        ['Usuarios → aplicación','<code>https://apps.flexnetuio.com:8443/app/</code>','Origen corporativo informado por el usuario y documentado el 18/10. Verificar vigencia, acceso y certificado en el pase.'],
        ['Proxy HTTPS → Uvicorn','Servicio <code>iv-itsanet</code>; salud local <code>http://127.0.0.1:3002/health</code>.','Arquitectura y puerto del procedimiento productivo. Apache figura en el diagnóstico histórico; virtual host y binding actuales requieren captura.'],
        ['Backend → MySQL','Protocolo MySQL; puerto habitual 3306; conexión definida en <code>VAL_DATABASE_URL</code>.','Motor corporativo informado. Host, versión, exposición y TLS SQL actuales no se leen desde esta entrega.'],
        ['Backend → Google','HTTPS 443: OAuth, Drive API, Gmail API.','Implementación directa verificada; cuenta, permisos efectivos y cuotas se confirman con autorización corporativa.'],
        ['Backend → Depot','HTTPS: base por defecto <code>https://ec.itsanet.com/q_apidepot</code>, <code>/gettoken</code> y <code>/getstock</code>.','Configuración reemplazable; credenciales guardadas en servidor. El código consulta catálogo/stock, no acredita un movimiento de inventario en Depot.'],
        ['PC puente → impresora','Agente opcional; conexión según configuración local de la estación.','No afirmar instalación física ni un puerto de impresora sin inventario TI.'],
        ['DNS / Wi-Fi / VPN','El informe histórico relaciona el nombre corporativo con <code>192.168.4.94</code>.','Dato histórico de red interna. TI confirma DNS, segmentación, firewall y cobertura en la jornada actual.']])
    entidades=tabla(['Grupo','Tablas principales','Relación / criterio'],[
        ['Acceso y catálogo','<code>operadores</code>, <code>sesiones</code>, <code>productos</code>, <code>producto_codigos</code>','Identidad local, rol y permisos; maestro local para consulta.'],
        ['Recepción operativa','<code>app_recepciones</code>, <code>app_lineas</code>, <code>app_skus</code>, <code>app_huellas</code>','Código de recepción → listas/orígenes → líneas originales; agregado por SKU. Fecha de registro original en UTC.'],
        ['Conteo y coordinación','<code>app_eventos</code>, <code>app_calidad_skus</code>, <code>app_presencias</code>','Eventos identificados; corrección/anulación conserva referencia al original. Presencia informa coincidencias; no es bloqueo exclusivo del SKU.'],
        ['Ingreso y bultos','<code>app_ingresos</code>, <code>app_unidades_logisticas</code>, <code>app_impresiones</code>','Unidades físicas, rótulos y solicitudes durables. Consolidación protegida de bultos finales vacíos.'],
        ['Evidencia','<code>app_archivos</code>, <code>app_archivo_identidades</code>, <code>app_archivo_skus</code>, <code>app_evidencias</code>, <code>app_copias_drive</code>','Archivo único, secuencia y asociaciones a SKU/bulto/embarque; copia y organización independientes del conteo.'],
        ['Entrega y configuración','<code>app_informes</code>, <code>app_entregas</code>, <code>app_config</code>, <code>app_auditoria_general</code>','Revisiones, huellas, nombres de salida, colas, configuración y registro técnico. Las auditorías de recepción también usan eventos.'],
        ['Modelo anterior coexistente','<code>recepciones</code>, <code>packing_items</code>, <code>pallets</code>, <code>scan_events</code>, <code>skus_pendientes</code>, <code>auditoria</code>','Compatibilidad del backend anterior. No intercambiar sus identificadores ni volver a importar históricos al actualizar.']])
    secciones=[
      ('alcance','1. Alcance y evidencia',
       '<p>Documento para transferencia a TI y Reingeniería de <b>ITSANET IMS</b>, validación física de recepciones. Describe el código candidato <b>v67 / interfaz 20261023-67</b>, la infraestructura reportada y los controles que deben verificarse en el servidor real.</p>'+nota('<b>No es un acta de puesta en producción.</b> El commit instalado, las versiones reales de servidor/base, el certificado, las autorizaciones Google, la restauración y el desempeño productivo deben anexarse como evidencia de aceptación. <code>/health</code> devuelve versión genérica 1.0.0: no identifica por sí solo el commit.')+
       tabla(['Tipo de información','Fuente y alcance'],[['Verificada en el repositorio','Servicios, rutas, modelos, dependencias declaradas y pruebas locales. Inventario anexo generado sin importar la aplicación.'],['Histórica del servidor','Captura incorporada a <code>docs/auditoria/informe-servidor-20261018.json</code>: servicio y salud correctos el 18/10; 11 GiB de RAM total y 73 G de filesystem redondeados. No representa recursos actuales.'],['Pendiente de evidencia actual','CPU y sistema operativo, carga concurrente, uso actual de disco/RAM/SQL, versión MySQL, topología/bindings, copia restaurable y datos de certificado. No se inventan valores ni garantías.']])+
       '<p>Los cambios de esta revisión son carpetas bajo demanda y fecha/filtros de Recepciones. Se mantienen los flujos de informes calculables, adjuntos con nombre independiente, ubicación por conteo, etiquetas simplificadas y coordinación incorporados en revisiones anteriores.</p>'),
      ('arquitectura','2. Arquitectura y componentes',
       '<div class="flujo"><a href="#clientes"><b>01 · Operación</b><small>Handheld / móvil / PC → HTTPS corporativo → /app/</small></a><a href="#datos"><b>02 · Núcleo corporativo</b><small>FastAPI / Uvicorn ↔ MySQL + archivos privados</small></a><a href="#google"><b>03 · Integraciones</b><small>Colas → Google Drive / Gmail; consulta Depot</small></a></div>'+componentes+
       '<p>Crear la recepción, guardar un conteo o corregirlo se confirma contra el servidor. Google participa en la copia y entrega posterior. El fallo de una integración se refleja en su estado; una foto local guardada no se presenta como foto ya confirmada en Drive.</p>'+nota('<b>Ubicación de los datos:</b> el núcleo transaccional está en la infraestructura corporativa. Fotografías, informes copiados y correo también se procesan en Google. La residencia, retención, compartición y base legal de ese tratamiento deben validarse con las políticas corporativas; alojar el backend en la empresa no acredita por sí solo cumplimiento normativo.')),
      ('red','3. Infraestructura y conexiones',red+
       '<p>El directorio operativo informado es <code>~/bryan/IV_ITSANET</code>. El servicio carga <code>/etc/iv-itsanet.env</code>; la ruta real de datos depende de <code>VAL_DATA_DIR</code>. Los contenedores de <code>compose.local.yaml</code> corresponden a desarrollo aislado, no prueban que producción esté contenerizada. No se requiere crear otra VM para aplicar esta revisión.</p>'+nota('TI debe registrar SO/versión, CPU, RAM, almacenamiento, responsables de DNS/certificado y puertos efectivamente expuestos. La evidencia histórica documenta Apache; no se presupone Nginx ni balanceador.')),
      ('clientes','4. Clientes móviles y disponibilidad',
       lista('Interfaz web adaptable; manifiesto PWA y service worker para recursos de la aplicación. Instalación desde el navegador es opcional.',
       'La captura en vivo exige HTTPS con certificado confiable en cada dispositivo y permiso de cámara para el origen y puerto exactos. El lector integrado del handheld puede funcionar como entrada de teclado.',
       'El escritorio y los móviles comparten los mismos registros SQL. Verificar versión del navegador, cámara y tamaño de pantalla con los equipos reales de la operación.',
       'La caché de interfaz y recuperación de fotos del navegador no convierten el sistema en una aplicación de conteo sin red. Guardar y validar datos requiere conexión al servidor; no declarar guardado cuando falla la confirmación.',
       'La galería distingue guardado, copia, organización y confirmación; revisa su estado aproximadamente cada tres segundos mientras está abierta.')),
      ('datos','5. Datos y consistencia',entidades+
       '<p>La base guarda los tiempos de operación en UTC; la interfaz presenta fecha y hora en <b>America/Guayaquil</b>. El filtro de Recepciones utiliza el día de registro en Ecuador, incluso si el navegador está en otra zona. Un registro antiguo sin fecha muestra «Sin fecha registrada»; no se deduce la fecha del código.</p>'+lista(
       'Las claves de idempotencia y restricciones únicas impiden sumar dos veces una misma solicitud reintentada. No impiden que una persona envíe deliberadamente dos solicitudes distintas.',
       'Los agregados por SKU se derivan de los eventos vigentes y sus anulaciones. Los bloqueos transaccionales y controles de versión protegen correcciones y borradores concurrentes.',
       'MySQL utiliza InnoDB, utf8mb4, modo estricto, sesiones SQL en UTC y reconexión previa. La configuración de pool declarada parte de cinco conexiones más cinco de desahogo por proceso; no es una cifra certificada de usuarios simultáneos.',
       'El arranque crea tablas ausentes y aplica compatibilidad aditiva de correo; no debe emplearse como restauración. El modelo conserva tablas anteriores. V67 no requiere una migración destructiva.',
       'ADMIN dispone de un borrado integral con confirmación escrita de recepción. Por ello la auditoría no se presenta como almacenamiento inalterable ni WORM; TI debe restringir ese permiso y definir retención y respaldo.')),
      ('flujo','6. Flujo operativo y trazabilidad',pasos(
       'Supervisor crea recepción con cliente y bultos; carga el packing list y revisa columnas, embarques y contenedores realmente recibidos. Se conservan los datos de origen.',
       'Operario identifica SKU, registra cantidad, pallet libre, origen y observación; añade posición sugerida o la completa después del conteo sobre el registro/pallet correspondiente.',
       'Clasifica incidencias y cantidades afectadas. PNC significa producto no conforme; sus evidencias deben justificar el estado del registro y el pallet encontrado.',
       'Las fotos se asocian al embarque, categoría, SKU y/o bulto elegido; pueden documentar varios ítems mediante vínculos sin duplicar el binario.',
       'Supervisor revisa diferencias, evidencias y catálogo; prepara informes vigentes, selecciona adjuntos y sus nombres finales, edita correo y responde al hilo apropiado del ejecutivo.',
       'El envío conserva su revisión y acuse. Un cierre o envío manual declarado se diferencia de una entrega confirmada por Google.')+
       '<p>Los informes distinguen cantidad física, conforme y PNC por registro/pallet/posición; evitan repetir el conjunto de ubicaciones de un SKU en todas sus filas. Una posición sugerida no acredita que el producto ya haya sido movido o cargado en Depot. El seguimiento por ítem permite construir indicadores sin sustituir la validación física.</p>'),
      ('archivos','7. Evidencias, carpetas y ciclo de vida',
       '<p>Crear una recepción, agregar embarques, abrir Drive o comprobar el correo <b>no crea categorías vacías</b>. La primera copia de un archivo crea su ruta necesaria. Los informes crean <code>INFORMES</code> al copiar un informe; no necesitan fotografías para existir.</p>'+codigo('Repositorio / CLIENTE / MARCA / RECEPCIÓN / EMBARQUE / PRE-INGRESO / foto.jpg\nRepositorio / CLIENTE / MARCA / RECEPCIÓN / EMBARQUE / PNC / SKU / foto.jpg\nRepositorio / CLIENTE / MARCA / RECEPCIÓN / EMBARQUE / BULTOS / BULTO / foto.jpg\nRepositorio / CLIENTE / MARCA / RECEPCIÓN / INFORMES / informe.xlsx')+
       '<p>Según la evidencia, las categorías son SOBRANTES, FALTANTES, PNC, PRODUCTOS, BULTOS, PRE-INGRESO, FOTOS-FINALES o PANORAMICAS. Una foto general compartida puede ir en COMPARTIDAS. Los nombres sanitizados pueden llevar sufijo para evitar colisiones; no cambiar esos nombres manualmente. Se muestra al usuario el destino previsto y el enlace confirmado.</p>'+lista(
       'Las referencias están en SQL; los originales locales se guardan en <code>VAL_DATA_DIR/app_archivos</code>. Las miniaturas se conservan en <code>app_miniaturas</code>.',
       'Se valida contenido, tipo/tamaño e identidad local. En la API directa se reserva un ID Drive antes de cargar y se comprueba el checksum remoto. Perder una respuesta no debe originar otro archivo.',
       'Después de la confirmación Drive, el flujo puede liberar el original local y mantener una miniatura. El respaldo local posterior ya no incluye necesariamente ese original: la protección y recuperación de Drive forman parte de la continuidad.',
       'La cuenta operativa debe conservar acceso al repositorio existente. La carpeta madre confirmada conserva su ID aunque cambien datos descriptivos; no se reubican históricos silenciosamente.',
       'Las carpetas antiguas no se eliminan masivamente. Una ruta puede quedar vacía tras retirar/reclasificar evidencia o una copia fallida; requiere revisión para no romper enlaces históricos. El cambio v67 evita la precreación, no constituye una limpieza retroactiva.',
       'El servidor evita invocar el preparador masivo de un Apps Script antiguo. Las subidas y reintentos siguen usando los archivos reales; con Google central se aplica sin republicar Apps Script por supervisor.')),
      ('google','8. Google central y correo',
       tabla(['Elemento','Diseño / validación'],[['Cliente OAuth','Uno de tipo aplicación web; Client ID/secret y URI exacta HTTPS configurados por ADMIN. Callback de operación: <code>/api/auth/google/callback</code>.'],['Cuenta Drive','Cuenta operativa autorizada por ADMIN y elegida para el repositorio. Permiso <code>https://www.googleapis.com/auth/drive</code>; revisar alcance y política Workspace.'],['Cuenta del remitente','Cada supervisor autoriza su mismo correo de la ficha local; permisos <code>gmail.readonly</code>, <code>gmail.send</code>, <code>openid</code> y <code>email</code>. No accede al buzón de otro supervisor.'],['OAuth y secretos','PKCE S256, estado de un uso de diez minutos, cookie HttpOnly, coincidencia de cuenta/sesión. Tokens y secretos cifrados con Fernet; clave fuera de MySQL en <code>VAL_DATA_DIR/secretos/integraciones.key</code>.'],['Correo final','MIME con texto/HTML, miniaturas incorporadas y archivos seleccionados. Destino operativo: ejecutivo asignado; revisar destinatarios reales antes de enviar.'],['Hilo original','Búsqueda desde el buzón autorizado por asunto/fecha y selección del mensaje. Respuesta conserva la relación con el hilo cuando Google la confirma.'],['Confirmación','Una petición aceptada o una entrega pendiente no equivale a correo recibido. Sin acuse concluyente se pausa para revisión, evitando repetir envíos a ciegas.'],['Compartición','La aplicación no vuelve públicas las fotos. Los destinatarios necesitan acceso apropiado a enlaces de Drive; las miniaturas del correo van incorporadas.']])+
       nota('Google Cloud debe permitir la audiencia utilizada; una cuenta Gmail externa no puede autorizarse en una audiencia interna exclusiva del dominio. El modo de prueba, la verificación de permisos y las políticas del administrador Google pueden afectar vigencia y autorización. Esto requiere aceptación de TI/Workspace, no otro despliegue de Apps Script por usuario.')),
      ('reportes','9. Informes y entrega de resultados',lista(
       'Las cantidades e importes exportados son celdas numéricas calculables; identificadores como SKU, pallet, código de barras, factura y ubicación conservan ceros y significado como texto.',
       'Las líneas de REV corresponden al packing list; UBICACIONES desglosa cantidades/estado por conteo y ubicación. ADICIONALES contiene únicamente SKU fuera de las listas de la recepción, no el sobrante de un SKU ya declarado.',
       'Los formatos del ejecutivo y los ampliados/auditables permiten seleccionar varios adjuntos, con nombres de salida independientes. Se conserva el nombre y binario histórico.',
       'La revisión queda vinculada a los datos que la originaron. Si cambian cantidades o evidencias, regenerar los documentos vigentes; no reutilizar un Excel anterior como si reflejara los cambios.',
       'El correo organiza prerecepción, observaciones y novedades con evidencias. Los avisos internos de productos por verificar en Depot se mantienen fuera del correo externo.',
       'Los CSV de Depot separan componentes de posición cuando corresponde al formato configurado. La aceptación del WMS y del Excel de escritorio debe verificarse con una muestra real autorizada.')),
      ('sincronizacion','10. Actualización, procesos y observabilidad',
       '<p>Las vistas comparten un canal SSE autenticado por recepción/página. El servidor detecta commits consultando SQL aproximadamente cada 0,75 s; el navegador agrupa invalidaciones y conserva formularios sin guardar. Hay respaldo por consulta cada cuatro segundos si SSE falla. La latencia real depende de red, proxy, carga y dispositivo; no se promete actualización instantánea.</p>'+lista(
       'Presencia por SKU con personas y actividad, con caducidad. Sirve para coordinación; cantidades, pallet y origen siguen requiriendo comunicación operativa.',
       'Avisos de catálogo por jornada de Ecuador y de novedades: PNC, sobrantes, faltantes y adicionales. Las diferencias abiertas son provisionales; una foto genérica no confirma evidencia PNC.',
       'ADMIN consulta Procesos y errores, colas actuales e historial técnico descargable. La bitácora operativa permite buscar y revisar eventos/anulaciones. Los registros técnicos se incorporan desde su implementación; no inventan historia anterior.',
       'La cola Drive tiene dos trabajadores de fotos con reservas SQL. El trabajador de entregas diferencia PENDIENTE, PROCESANDO, REVISION, ENTREGADA y CANCELADA.',
       'El journal de systemd conserva diagnóstico del proceso; los tiempos de retención, alertas externas y monitoreo de capacidad deben definirse por TI.')),
      ('seguridad','11. Seguridad y límites conocidos',
       tabla(['Control implementado','Alcance / aceptación requerida'],[['Autenticación local','Usuario/contraseña o PIN; PBKDF2-HMAC-SHA256 con salt y 120.000 iteraciones. Sesión aleatoria en SQL, caducidad configurable de 12 h por defecto.'],['Cookies','HttpOnly y SameSite=Lax. Secure según HTTPS reconocido o <code>VAL_COOKIE_SECURE=1</code>. Verificar cabeceras de proxy y origen real.'],['Roles y permisos','OPERADOR, SUPERVISOR y ADMIN, con permisos operativos adicionales. La autorización se comprueba en backend; no depende solo de ocultar botones.'],['Integraciones','Secretos cifrados en SQL y clave privada en disco con permisos restringidos. Respaldar y custodiar juntos datos y clave; no anexar secretos al expediente.'],['Validación','Controles de pertenencia de recepción/archivo/grupo, revisión vigente, duplicados, checksum, sanitizado de HTML y restricciones de rutas.'],['Concurrencia','Idempotencia, restricciones únicas, locks y controles de versión. La presencia no garantiza exclusividad ni sustituye el control físico de doble conteo.'],['Alcance de auditoría','Trazabilidad funcional y técnica. No constituye firma electrónica, certificación de seguridad, auditoría inmutable ni cumplimiento legal acreditado.'],['Revisión de TI','Validar exposición de /docs y /openapi.json, políticas de contraseñas/MFA, limitación de intentos y red, bajas de cuentas, permisos Drive, TLS, parches y vulnerabilidades. No se afirma que existan controles perimetrales no observados.']])+
       nota('En una base totalmente vacía el arranque puede crear un administrador inicial con credencial conocida. Debe cambiarse antes de habilitar el acceso. Una actualización de la base existente no requiere recrear ese usuario.')),
      ('continuidad','12. Despliegue, respaldo y recuperación',pasos(
       'Separar desarrollo de producción. Las pruebas usan SQLite temporal o una base MySQL de pruebas explícita; nunca ejecutar fixtures de pytest sobre datos operativos.',
       'Aplicar el commit completo de la entrega mediante <code>scripts/actualizar_produccion.sh</code>. Confirmar WorkingDirectory, servicio activo, avance lineal y ausencia de cambios locales no resueltos; avisar la pausa de registros.',
       'El actualizador prepara dependencias antes de parar y verifica requisitos de mysqldump. Detiene solo iv-itsanet para copiar SQL y datos de forma consistente; conserva configuración privada y código anterior.',
       'El respaldo contiene <code>mysql.sql.gz</code>, <code>archivos.tar.gz</code>, manifiesto de checksum y copia privada del entorno. El directorio habitual es <code>~/bryan/respaldos-itsanet</code>. Revisar espacio y custodia.',
       'Tras aplicar el código, instalar dependencias preparadas y arrancar, verifica /health y que la página corresponda al archivo instalado. Si falla, intenta volver al código anterior; no restaura ni reemplaza automáticamente la base.',
       'Una recuperación de datos exige procedimiento TI: restaurar SQL, archivos y clave en un entorno aislado; verificar relaciones, conteos, fotos, permisos y correo sin enviar; documentar tiempo y pérdida tolerable antes de una sustitución productiva.')+
       '<p>Un gzip legible y un checksum correcto no demuestran una restauración completa. TI debe acordar RPO/RTO, frecuencia y retención de respaldo y hacer un ensayo. Drive requiere protección y recuperación propias para los originales liberados localmente.</p>'),
      ('inventario','13. Inventario del código y dependencias',
       '<p>Inventario generado por análisis estático: <b>'+str(len(inv['tablas']))+' tablas ORM</b> y <b>'+str(len(inv['rutas']))+' declaraciones de rutas en routers</b>. Se incluyen interfaces anteriores para no ocultar su coexistencia; estos números no son tablas ni endpoints medidos en el servidor. No incluyen mounts ni /health y rutas automáticas de FastAPI.</p>'+
       '<details><summary>Dependencias Python declaradas</summary>'+codigo('\n'.join(inv['dependenciasPythonDeclaradas']))+'</details>'+
       '<details><summary>Herramientas JavaScript declaradas</summary>'+tabla(['Paquete','Versión declarada'],[(E(k),E(v)) for k,v in inv['dependenciasJSDeclaradas'].items()])+'</details>'+
       '<details><summary>Modelo y nombre real de todas las tablas</summary>'+tabla(['Modelo','Tabla'],[(E(t['modelo']),'<code>'+E(t['tabla'])+'</code>') for t in inv['tablas']])+'</details>'+
       '<details><summary>Rutas y fuentes del backend</summary>'+tabla(['Método','Ruta','Fuente'],[(E(r['metodo']),'<code>'+E(r['ruta'])+'</code>','<code>'+E(r['fuente'])+'</code>') for r in inv['rutas']])+'</details>'+
       '<p>El anexo <code>inventario-codigo-v67.json</code> permite contrastar el contenido. Las versiones instaladas se capturan desde el servidor; las versiones fijadas en un requirements no demuestran qué tiene cargado el proceso.</p>'),
      ('aceptacion','14. Aceptación por TI y Reingeniería',controles([
       'TI registró commit instalado, versión de recursos, SO/CPU/RAM/disco, versión SQL y fecha de arranque del servicio.',
       'TI verificó HTTPS y certificado en PC y handheld; documentó responsable de renovación, DNS y reglas de red.',
       'TI comprobó usuarios/roles, contraseñas, exposición de API, custodia de claves y permisos efectivos en Google.',
       'Una recepción de prueba conserva filas y cantidades; correcciones, anulación y doble reintento producen resultados trazables.',
       'Dos usuarios ven cambios y presencia sin perder entradas sin guardar; se evaluó la red/proxy de la bodega.',
       'Sin fotos no aparecen categorías nuevas; una PNC con evidencia crea solo su destino, mantiene fileId y abre el enlace correcto.',
       'Se descargaron informes calculables y se conciliaron REV, UBICACIONES y ADICIONALES con registros físicos y posiciones.',
       'Un supervisor respondió al hilo autorizado del ejecutivo con adjuntos elegidos, nombres revisados, miniaturas y acuse; una incertidumbre no reenvía a ciegas.',
       'TI ensayó restauración en ambiente aislado incluyendo clave privada y disponibilidad de originales en Drive; acordó RPO/RTO y retención.',
       'Reingeniería y Operación validaron procedimiento, responsables, indicadores y manejo de excepciones; se archivó el acta formal con observaciones.'
       ])+nota('Las casillas se guardan solo en este navegador y se exportan como una lista de revisión. No acreditan firma, resultado técnico automático ni aprobación de ninguna jefatura.')),
      ('fuentes','15. Fuentes y control documental',
       lista('<code>app/main.py</code>, <code>app/db.py</code>, <code>app/config.py</code>, <code>app/models.py</code>, <code>app/security.py</code> y routers: arquitectura, datos y acceso.',
       '<code>app/services/google_cuentas.py</code>, <code>google_drive_api.py</code>, <code>google_gmail_api.py</code>, <code>drive.py</code>, <code>entregas.py</code>, <code>carpetas_recepcion.py</code>: integraciones y estados.',
       '<code>firebase/public</code>, <code>scripts/versionar_frontend.mjs</code>, <code>requirements.txt</code>, <code>package.json</code>: interfaz y dependencias.',
       '<code>scripts/actualizar_produccion.sh</code>, <code>respaldo_produccion.py</code>, <code>auditar_servidor_lectura.py</code>: pase, respaldo y captura de lectura.',
       '<code>docs/auditoria/informe-servidor-20261018.json</code>: evidencia histórica identificada, no diagnóstico actual.',
       'Los documentos anteriores describen revisiones específicas y pueden contener procedimientos reemplazados. Para entrega v67 usar este paquete, su manifestación de revisión y las evidencias de aceptación reales.')+
       '<p>Este informe no contiene claves, tokens, binarios de evidencias de clientes ni buzones. Los responsables personales, fechas de puesta en producción y aprobaciones se completan en el acta institucional.</p>')]
    documento('Informe-tecnico-ITSANET-v67.html','Informe técnico · arquitectura y entrega','Estructura, infraestructura, datos, integraciones y criterios de aceptación para TI y Reingeniería.',secciones)


def operativo():
    secciones=[
      ('preparar','1. Preparar la jornada',pasos(
       'Entrar desde el origen HTTPS corporativo aprobado, con el usuario propio. En móvil o handheld, comprobar lector/cámara y conexión antes de empezar.',
       'Revisar Avisos: coincidencias de trabajo, catálogo pendiente y novedades. Supervisor/ADMIN comprueba que el catálogo de los clientes de la jornada esté actualizado.',
       'Abrir Recepciones. Buscar por código, cliente, descripción o embarque; combinar estado con Registro desde/hasta y elegir orden. En el servidor, la búsqueda cubre todo el histórico y se recorre con Anterior/Siguiente en páginas de 50. Las fechas representan el registro original en hora de Ecuador.',
       'Seleccionar Validar en la recepción correcta. Verificar cliente, marca, packing list/embarque y cantidades antes del primer conteo.')+nota('Usar una cuenta propia conserva la trazabilidad por persona. Una recepción cerrada se consulta; si hace falta modificar registros, corresponde el procedimiento de reapertura autorizado.')),
      ('supervision','2. Crear recepción y cargar listas',pasos(
       'Supervisor/ADMIN: Nueva recepción → código único, cliente, número de bultos si ya se conoce y descripción. Crear no copia fotografías ni crea categorías vacías en Drive.',
       'Seleccionar el packing list. Revisar hoja, fila de encabezado y columnas detectadas en la vista previa; corregir el mapeo si el formato difiere.',
       'Seleccionar únicamente los contenedores realmente recibidos. Las cantidades declaradas corresponden a las líneas seleccionadas; no sustituirlas por un total deseado.',
       'Revisar los embarques y guardar. Si llega otra lista de la misma recepción, usar Gestionar → + Embarque. Ante un aviso de duplicado, comprobar el contenido con el documento recibido antes de confirmar.',
       'Si varias listas comparten un SKU, identificar el origen de cada conteo; la entrega por grupo requiere revisar la asignación correspondiente.')+
       nota('Si el declarado no coincide con lo recibido, revisar primero líneas, contenedores y documentos. Una diferencia física se registra como tal; no corregir la fuente solo para hacerla coincidir.')),
      ('contar','3. Contar, ubicar y coordinar',pasos(
       'Escanear o buscar el SKU. Comprobar descripción y lista; revisar si otro operario aparece trabajando en ese mismo código.',
       'Registrar cantidad de este conteo y pallet tal como se identifica físicamente. El pallet es texto libre; no es necesario anteponer DP.',
       'Seleccionar packing list/origen cuando corresponda. Indicar observación concreta y posición sugerida si ya está definida.',
       'Guardar y esperar confirmación. Reintentar un envío pendiente desde la misma ficha conserva su identificador; no abrir otro conteo para sustituir una respuesta todavía incierta.',
       'Si se definió pallet pero falta la ubicación, usar Posición final después del conteo para elegir el registro/pallet exacto y completar su ubicación sin cambiar cantidades.',
       'Para corregir, entrar al registro correspondiente, verificar su cantidad/pallet/posición y escribir el motivo. La corrección conserva el original como antecedente de auditoría.')+
       '<p>La posición sugerida se escribe como un solo valor, por ejemplo <code>BM-A-10-1</code>. El sistema interpreta nave, literal/calle, columna y nivel cuando el formato es válido; no volver a digitarlos por separado. Verificar que corresponde a la posición física autorizada. Guardar esa sugerencia no mueve automáticamente existencias en Depot.</p>'+nota('La alerta de coincidencia facilita coordinar personas; no bloquea de forma exclusiva todo el SKU. Evitar que dos personas registren las mismas unidades aunque usen pallets distintos.')),
      ('novedades','4. Novedades y PNC por registro',
       '<p>Registrar tipo, unidades afectadas, observación y pallet específico donde se encontró la incidencia. PNC es <b>producto no conforme</b>; la evidencia debe justificar la clasificación.</p>'+
       tabla(['Ejemplo físico','Registro que corresponde'],[['2 unidades PNC en A01, ubicación BM-A-10-1','Conteo/cantidad afectada: 2 PNC, pallet A01, ubicación BM-A-10-1; observación y foto del daño.'],['4 unidades conformes en A01, misma ubicación','Registro conforme por 4 unidades en A01; no extender la PNC a todo el SKU.'],['4 unidades conformes en A02, ubicación BM-B-12-1','Registro conforme por 4 unidades en A02, con su ubicación.'],['Total del SKU','10 físicas = 8 conformes + 2 PNC; cada fila de ubicación permite identificar cantidad y estado.']])+
       lista('Sobrante: unidades por encima de lo declarado para un SKU que sí está en el packing list.',
       'Faltante: diferencia de unidades frente a lo declarado; durante recepción abierta puede ser provisional.',
       'Adicional: SKU que no pertenece a ninguna lista de la recepción. No es otra forma de registrar el sobrante de un código declarado.',
       'No utilizar una foto genérica de bodega como prueba de daño específico. Clasificar y vincular la imagen al registro que corresponda.')),
      ('fotos','5. Registrar fotos y comprobar su destino',pasos(
       'Abrir Fotos del ítem o Bultos y fotos, según la evidencia. Para descarga del contenedor, elegir Prerecepción / pre-ingreso.',
       'Seleccionar embarque, grupo/tipo de foto y SKU/bulto/pallet cuando aplique. Revisar la ruta prevista que aparece en el modal.',
       'Elegir cámara o galería. Revisar siempre la imagen antes de guardar: enfoque, daño, etiqueta y pallet legibles. Se puede ajustar el destino de cada foto del lote.',
       'Guardar fotos seleccionadas o guardar con el conteo. Guardar solo fotos no suma unidades.',
       'Comprobar el estado: Guardada en servidor → copiando/organizando → Confirmada en Drive. Revisar el progreso y el enlace individual; una vista previa local no prueba que Drive recibió la imagen.',
       'Si hay pendientes, conservar la selección y revisar Recuperación y organización / reintento. Avisar al supervisor si necesita conexión o permisos; no tomar otra foto idéntica únicamente para sustituir una copia pendiente.')+
       tabla(['Evidencia elegida','Destino esperado al copiar'],[['Prerecepción / descarga','Recepción / embarque / PRE-INGRESO.'],['Incidencia PNC de SKU','Recepción / embarque / PNC / SKU; puede incluir la identificación del bulto asociado.'],['Sobrante / faltante con foto','Su categoría correspondiente y SKU dentro del embarque elegido.'],['Foto adicional del producto','PRODUCTOS / SKU; no convierte el producto en adicional del packing list.'],['Bulto','BULTOS / identificación del bulto.'],['Cómo quedó / panorámica','FOTOS-FINALES o PANORAMICAS según tipo.'],['General compartida','COMPARTIDAS cuando fue elegida para toda la recepción con varios embarques.']])+
       nota('Solo se crea la ruta utilizada por un archivo. Sin fotos no se crean las ocho categorías. Las carpetas existentes de revisiones anteriores no son prueba de que haya una foto; revisar las imágenes y sus enlaces confirmados.')),
      ('bultos','6. Bultos y etiquetas',pasos(
       'Abrir Bultos y fotos para revisar el total confirmado. Si hubo consolidación física, usar Corregir total, escribir el nuevo total, motivo y confirmación.',
       'El sistema protege los bultos con fotos, códigos o registros. Si rechaza la consolidación, revisar la distribución física; el mensaje indica la causa y conserva lo escrito.',
       'En etiquetas, confirmar literal, total, tamaño 10×5 o 10×15 cm y destino. Revisar vista previa.',
       'Para imprimir una parte, elegir Solo números o rangos seleccionados y escribir, por ejemplo, 1-10, 15, 20-25. Se mantienen los números físicos; elegir 15 imprime el bulto 15.',
       'Cada etiqueta muestra cliente, rótulo del bulto y sus barras CODE128. Imprimir al 100 %, sin márgenes ni encabezados; verificar una lectura con el equipo real antes del lote.',
       'Para el diseño actualizado preparar una nueva solicitud o reimpresión. Las solicitudes antiguas conservan su instantánea y ZPL original.')),
      ('revisar','7. Revisar y descargar informes',pasos(
       'Supervisor revisa bitácora, incidencias, pallets, posiciones, evidencia PNC y diferencias pendientes. Los nombres de personas y observaciones ayudan a ubicar el registro concreto.',
       'Preparar el informe del ejecutivo y, si hace falta, el ampliado/auditable. Descargar desde el mismo modal de preparación del correo.',
       'Cambiar el nombre de cada archivo en su propia fila y marcar los que se adjuntarán. Preparar otro formato conserva el nombre ya editado de los anteriores.',
       'Descargar seleccionados genera un archivo o un ZIP. Abrirlos para validar cantidades calculables, registros de ubicación y adicionales fuera del packing list.',
       'Si se corrige un conteo o cambia una evidencia, actualizar y preparar la revisión vigente. Los históricos se conservan para consulta, no se presentan como una revisión nueva.')+
       '<p>REV permite contrastar líneas y resultado; UBICACIONES identifica cantidad/estado por pallet y posición; ADICIONALES reúne códigos fuera del packing list. Comprobar siempre que las sumas y la mercadería física corresponden al grupo de envío.</p>'),
      ('correo','8. Preparar y enviar al ejecutivo',pasos(
       'Elegir el correo de la recepción, packing list o embarque que corresponde. Verificar cliente–marca y código del grupo.',
       'Revisar destinatarios del ejecutivo asignado. Conectar la cuenta Google propia del supervisor desde Mi cuenta si aún no está autorizada.',
       'Si se responde una solicitud previa, buscar asunto/fecha en el buzón propio y seleccionar el mensaje original correcto.',
       'Editar la redacción en contexto. Revisar primero fotos de prerecepción, después observaciones y novedades con sus evidencias; incluir o retirar imágenes según el caso.',
       'Preparar y descargar documentos, elegir los adjuntos y comprobar sus nombres. Comprobar carpetas e imágenes actualiza enlaces existentes y reintenta las fotos pendientes sin crear categorías vacías.',
       'Revisar miniaturas, enlaces, cantidades y archivos. Guardar cambios y pulsar Enviar correo cuando todo esté validado.',
       'Esperar el resultado en Entregas. Si aparece pendiente o revisión, comprobar el motivo y Enviados antes de cualquier recuperación. No volver a enviar a ciegas.')+
       nota('Los productos por verificar en Depot son un aviso interno. No deben remitirse al ejecutivo como si fueran una novedad física. Un envío manual declarado por supervisor no es un acuse automático de Google.')),
      ('excepciones','9. Mensajes y acciones',tabla(['Mensaje / situación','Qué hacer'],[
       ['Otra persona está en el SKU','Coordinar pallet, origen y unidades antes de registrar. Consultar los nombres mostrados.'],
       ['Recepción o borrador cambió','Conservar la redacción pendiente, actualizar y revisar los cambios; no repetir correcciones sobre una versión antigua.'],
       ['Copia Drive pendiente','La imagen local puede estar guardada. Consultar el archivo y esperar/reintentar; verificar conexión responsable.'],
       ['Sin carpeta / sin fotografías','Es normal antes del primer archivo. La ruta se crea al copiar la foto o el informe.'],
       ['Falta enlace o miniatura','Actualizar imágenes y resolver el pendiente antes del envío. No pegar una URL vacía o de otro SKU.'],
       ['Entrega en revisión sin acuse','Supervisor/ADMIN comprueba el buzón y el monitor antes de decidir recuperación.'],
       ['Sin conexión / sesión vencida','Restablecer acceso al servidor o entrar nuevamente. Confirmar qué registro se guardó antes de volver a contar.'],
       ['Registro sin fecha original','Se muestra expresamente; no deducirla del nombre ni modificarla para ordenar el listado.']])+
       '<p>Al solicitar soporte incluir recepción, SKU, pallet, acción, hora aproximada de Ecuador y mensaje visible. No enviar contraseñas, tokens o claves del servidor.</p>'),
      ('indicadores','10. Cierre e indicadores',
       '<p>La trazabilidad por ítem y evento permite consultar cantidades, incidencias, evidencia, operador y tiempos. Interpretar los indicadores con la jornada, origen y estado correctos. Una diferencia provisional no es un reclamo confirmado; PNC y diferencia de cantidad son dimensiones distintas.</p>'+controles([
       'Se revisaron recepción, cliente–marca, listas y contenedores correspondientes.',
       'Cada conteo refleja sus propias unidades, pallet, posición e incidencias.',
       'Se resolvieron coincidencias de personas y diferencias pendientes con el equipo.',
       'Las evidencias seleccionadas están confirmadas con enlaces y miniaturas correctos.',
       'Los informes descargados son vigentes y sus nombres y selección corresponden al envío.',
       'El ejecutivo y el hilo original están revisados; la entrega se confirmó o quedó identificada para seguimiento.'
       ]))]
    documento('Manual-operativo-ITSANET-v67.html','Manual operativo · registro y entrega','Guía para operarios y supervisores: recepción, conteos, ubicación, PNC, fotografías, documentos y correo.',secciones)


def administracion():
    captura='''cd ~/bryan/IV_ITSANET
sudo systemd-run --quiet --wait --pipe --collect \\
  --unit="iv-auditoria-$(date +%s)" --uid="$(id -un)" \\
  --property="WorkingDirectory=$PWD" \\
  --property=EnvironmentFile=/etc/iv-itsanet.env \\
  "$PWD/.venv/bin/python" "$PWD/scripts/auditar_servidor_lectura.py" \\
  --repo "$PWD" --salida "$HOME/bryan/auditorias-itsanet"'''
    secciones=[
      ('responsables','1. Responsables y transferencia',tabla(['Responsable','Función'],[
       ['Administrador funcional designado','Alta/baja y mantenimiento de usuarios, permisos, clientes, seguimiento de procesos y coordinación de incidencias. La designación personal se documenta en el acta.'],
       ['Supervisor de operación','Calidad de conteos, catálogo actualizado, revisión de evidencias, destinatarios e informes; autorización de su propio correo.'],
       ['TI / infraestructura','Servidor, MySQL, DNS, HTTPS, Wi-Fi/VPN, acceso, parches, respaldo/restauración, monitoreo y recuperación.'],
       ['TI / Google Workspace','Propiedad del proyecto Cloud y repositorio, autorizaciones, audiencia OAuth, compartición, cuotas, retención y recuperación de Google.'],
       ['Reingeniería','Validación del proceso, reglas, indicadores, excepciones y oportunidades de mejora, con evidencia del trabajo real.']])+
       '<p>Entregar código identificado por commit, estos HTML, inventario, validación, comando de actualización y acta con responsables y observaciones. Las credenciales se transfieren por el mecanismo privado de la empresa, por separado del paquete.</p>'),
      ('usuarios','2. Usuarios, roles y configuración',pasos(
       'ADMIN entra a Administración y Usuarios. Revisar nombre, correo, estado activo, rol y permisos; evitar cuentas compartidas.',
       'Aprobar las solicitudes que corresponden y asignar los permisos necesarios. Verificar que un operario puede contar pero no configurar integraciones ni enviar desde otro buzón.',
       'Mantener correo exacto del supervisor en su ficha: OAuth exige coincidencia con Google. Corregir una ficha no concede autorización para operar como otra persona.',
       'Desactivar las cuentas al retirar acceso. Revisar también autorizaciones Google y propiedad del repositorio cuando cambia el responsable.',
       'Revisar clientes, marcas, repositorios y formatos de importación/exportación. Probar los cambios con una recepción de prueba antes de usarlos en el turno.')+
       nota('No ejecutar el instalador inicial ni recrear el archivo de entorno para actualizar una instalación que funciona. El procedimiento de actualización preserva los datos y conexiones existentes.')),
      ('central','3. Configurar Google central una vez',pasos(
       'TI crea o utiliza el proyecto corporativo de Google Cloud, habilita Google Drive API y Gmail API y conserva su propiedad institucional.',
       'Configura audiencia y pantalla de consentimiento. Verificar si participan cuentas externas Gmail; una audiencia solo interna no las admite. Revisar políticas Workspace y verificación de permisos aplicables.',
       'Crea cliente OAuth de tipo Aplicación web y registra la URI exacta de callback: para el origen informado, https://apps.flexnetuio.com:8443/api/auth/google/callback. Debe coincidir con HTTPS, hostname, puerto y ruta reales.',
       'ADMIN abre Administración → Conexiones → Google central; guarda Client ID, Client secret y callback. El secreto se configura de forma privada, no se envía por correo ni se incluye en capturas.',
       'ADMIN autoriza su cuenta operativa de Drive y la selecciona para almacenamiento. Verifica carpeta raíz o repositorios por cliente/marca y acceso a los archivos existentes.',
       'Cada supervisor abre Mi cuenta → Conectar con Google y autoriza el mismo correo de su ficha. Comprobar Gmail. No crea su propia aplicación web Apps Script.',
       'En una recepción de prueba, guardar foto, comprobar confirmación/enlace, descargar informe y revisar un envío autorizado al destinatario de pruebas. Registrar acuse y permisos de acceso a las fotos.')+
       tabla(['Síntoma','Revisión'],[['ADMIN debe configurar cliente OAuth / HTTPS','Callback y origen autorizado deben coincidir exactamente; comprobar configuración central y acceso por el HTTPS correcto.'],['Cuenta Google diferente','Cerrar el selector y autorizar el correo exacto de la ficha local; no modificar el remitente para simular identidad.'],['El /exec pertenece a otra cuenta','Es una configuración anterior de Apps Script. Con Google central autorizado, utilizar esa vía; no repartir un mismo /exec como identidad de distintos supervisores.'],['Autorización revocada o modo prueba','Reconectar la cuenta y revisar políticas/estado del proyecto. No volver a crear el proyecto para cada envío.'],['Drive sin permiso / carpeta movida','Comprobar cuenta operativa, pertenencia y nombres/ID existentes antes de mover o crear otra estructura.']])+
       '<p>Apps Script queda como compatibilidad para instalaciones que aún lo requieren o exportación opcional a Sheets. V67 evita llamar a un preparador masivo antiguo; para la vía central basta actualizar el servidor. No es obligatorio republicar una app web por cada supervisor.</p>'),
      ('diario','4. Supervisión diaria y capacidad',lista(
       'Al iniciar la jornada, revisar Avisos y constancia de actualización masiva de catálogo por cliente. Consultar un solo SKU no acredita actualización completa.',
       'Revisar Procesos y errores como ADMIN: estado actual, intentos, referencia y causa. Filtrar por recepción y exportar diagnóstico JSON cuando se solicite soporte.',
       'Controlar fotos guardadas frente a confirmadas, pendientes de asignar embarque, carpetas desactualizadas y entregas en REVISION.',
       'No confundir CANCELADA con fallo: puede ser una acción deliberada. Confirmar el último envío vigente y los documentos asociados.',
       'Medir disco disponible, almacenamiento local pendiente, datos/índices SQL, memoria/carga y duración de reintentos. Comparar capturas entre jornadas; un valor puntual no demuestra tendencia.',
       'Revisar permisos y retención Drive y cuota de correo. Un respaldo de MySQL no reemplaza la recuperación de originales que ya solo están en Google.')),
      ('lectura','5. Diagnóstico de solo lectura',
       '<p>Estos comandos muestran revisión, estado y salud local. No prueban por sí solos una recepción completa ni un envío:</p>'+codigo('cd ~/bryan/IV_ITSANET\ngit rev-parse HEAD\nsystemctl is-active iv-itsanet\ncurl --fail --silent http://127.0.0.1:3002/health\nsudo journalctl -u iv-itsanet -n 80 --no-pager')+
       '<p>Para registrar infraestructura, configuración sin valores secretos, puertos, TLS, capacidad y estado SQL, usar la captura acotada de lectura. Escribe únicamente informes privados fuera del código; no reinicia, migra ni actualiza MySQL:</p>'+codigo(captura)+
       nota('Revisar los diagnósticos antes de compartirlos: pueden contener nombres de rutas, referencias operativas y metadatos. El helper no imprime contraseñas ni claves; no adjuntar archivos .env ni la clave privada.')),
      ('pase','6. Actualizar producción',pasos(
       'Leer el manifiesto y el comando exacto de la entrega. Identificar commit completo, rama operativa y versión de interfaz; no usar reset --hard para eludir cambios locales.',
       'Avisar una pausa de registros; confirmar con el equipo los guardados pendientes. Ejecutar el comando publicado que extrae scripts/actualizar_produccion.sh del commit probado.',
       'El actualizador comprueba servicio, ruta, avance de Git, dependencias y herramientas de respaldo. Prepara dependencias, detiene solo iv-itsanet, respalda base y datos y aplica la versión.',
       'Esperar resultado y registrar ruta de respaldo. Si falla, conservar el diagnóstico y comprobar recuperación del código anterior antes de retomar el trabajo.',
       'Recargar PC y handheld. Comprobar una recepción existente, fecha/filtros, lectura de etiquetas, datos y enlaces; las nuevas categorías solo aparecen al copiar archivos.',
       'Registrar commit, hora, resultado, persona ejecutora y aceptación funcional. Un mensaje del chat o una rama publicada no certifican que el pase se haya ejecutado.')+
       nota('El comando con el hash exacto se incluye en la entrega final. Se utiliza el servicio y la base existentes; no se importan volúmenes ni usuarios de desarrollo.')),
      ('recuperacion','7. Respaldar y recuperar',tabla(['Elemento','Qué debe conservarse'],[
       ['MySQL','Dump consistente, checksum y revisión del código correspondiente. Incluye datos operativos y referencias; no incluye por sí mismo los bytes originales en Drive.'],
       ['Archivos privados','VAL_DATA_DIR, evidencias pendientes, informes locales, miniaturas y secretos/integraciones.key con permisos correctos.'],
       ['Configuración','/etc/iv-itsanet.env, unidad de systemd y configuración de proxy/certificado bajo custodia TI. El actualizador copia el entorno en su respaldo privado; no presume un respaldo completo de Apache o TLS.'],
       ['Google','Propiedad y acceso del repositorio, política de retención/recuperación, autorizaciones y continuidad de la cuenta operativa.'],
       ['Código / dependencias','Commit, requisitos y artefactos disponibles. Volver a un commit no restaura filas SQL ni garantiza revertir dependencias ya instaladas.']])+
       pasos('Ensayar la restauración en otra base y ruta, con conexiones de correo/Google deshabilitadas para evitar envíos reales.',
       'Restaurar el SQL y los archivos del mismo punto de respaldo; recuperar la clave privada que descifra las credenciales sin publicarla.',
       'Arrancar el código compatible y validar relaciones, cantidades, eventos/anulaciones, descarga, evidencia y acceso. Revisar las colas sin reanudar entregas automáticamente en el ensayo.',
       'Medir el tiempo de recuperación y documentar la pérdida de datos tolerable. Solo después aprobar un procedimiento productivo y una ventana de sustitución con TI.')+
       nota('No se aporta un comando destructivo de restauración genérico. El servidor comparte servicios y los destinos reales deben identificarse antes de reemplazar una base o carpeta. Un respaldo debe probarse, no solo existir.')),
      ('incidentes','8. Resolver incidencias sin duplicar datos',tabla(['Caso','Acción operativa / TI'],[
       ['Foto guardada, Drive pendiente','Conservar el original. Revisar causa en monitor, cuenta operativa, permiso, cuota y conexión; reintentar desde la recepción manteniendo ID.'],
       ['Hay categorías vacías antiguas','V67 detiene la precreación. Revisar contenido, subcarpetas y enlaces históricos antes de cualquier limpieza autorizada. No borrar por nombre ni interpretar ausencia de fotos como cantidad física cero.'],
       ['Carpeta duplicada o movida','Revisar IDs y ruta; el sistema no elige arbitrariamente carpetas duplicadas. Conservar referencias de las entregas anteriores.'],
       ['Correo sin acuse','Revisar Enviados del remitente propio, referencia e hilo. Utilizar la recuperación controlada; no pulsar Enviar repetidamente.'],
       ['Datos no se refrescan','Comprobar misma recepción/versión, sesión, red y SSE en el proxy. La consulta de respaldo funciona cada cuatro segundos; no desactivar controles de concurrencia.'],
       ['No se guardó corrección de bultos','Leer el rechazo: fotos/códigos/registros, reserva de impresión o cambio de total concurrente. No borrar bultos utilizados para forzar consolidación.'],
       ['Excel solicita reparación','Guardar el archivo original y el registro de reparación XML, junto con formato/revisión. No sustituir cantidades por texto ni eliminar información hasta identificar el elemento.'],
       ['No abre la cámara en handheld','Comprobar HTTPS/origen, cadena del certificado, permiso y navegador. Evitar HTTP por IP como solución. Comprobar el lector físico por separado.'],
       ['Clave privada inaccesible','Restituir desde respaldo seguro con permisos correctos; no generar otra clave para intentar descifrar credenciales anteriores.'],
       ['Servidor o DB no responde','Conservar diagnóstico y revisar servicio, conexión/pool, espacio y recursos. No recrear tablas ni correr fixtures de pruebas en producción.']])+
       '<p>Para escalar: registrar versión, recepción/archivo/SKU, hora de Ecuador, acción y mensaje. Adjuntar diagnóstico sanitizado y revisión del informe. Contraseñas, tokens, claves y contenido privado de buzón quedan fuera del ticket.</p>'),
      ('aceptacion','9. Lista de transferencia',controles([
       'Se designaron responsables de administración funcional, infraestructura, Google y proceso; sus datos están en el acta.',
       'Se entregaron repositorio/commit, HTML, inventario y comprobaciones, diferenciando versión publicada e instalada.',
       'Usuarios, permisos y acceso a secretos se revisaron sin incluir claves en el expediente.',
       'Se capturó la infraestructura actual y se acordó el seguimiento de capacidad, certificado y respaldos.',
       'Se validaron fotos, informes, recepción/fecha y entrega al ejecutivo con datos de prueba autorizados.',
       'Se ensayó recuperación aislada, se acordó retención/RPO/RTO y se formalizó la aceptación con observaciones.'
       ]))]
    documento('Manual-administracion-ITSANET-v67.html','Manual de administración y soporte','Usuarios, Google central, seguimiento diario, diagnóstico, actualización y continuidad de la operación.',secciones)


def main():
    SALIDA.mkdir(parents=True,exist_ok=True)
    inv=inventario();(SALIDA/'inventario-codigo-v67.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2)+'\n')
    tecnico(inv)
    operativo()
    administracion()
    documento('index.html','Entrega de ITSANET IMS','Paquete v67 para Operación, TI y Reingeniería. Cada documento funciona sin conexión.',[
        ('documentos','Documentos de entrega', '<div class="hero-grid"><div><b>Informe técnico</b><p>Arquitectura, red, datos, controles y aceptación.</p><a href="Informe-tecnico-ITSANET-v67.html">Abrir informe técnico</a></div><div><b>Manual operativo</b><p>Operario y supervisor: registro, evidencias y entrega.</p><a href="Manual-operativo-ITSANET-v67.html">Abrir manual operativo</a></div><div><b>Administración y soporte</b><p>Usuarios, Google, monitor, respaldo y resolución.</p><a href="Manual-administracion-ITSANET-v67.html">Abrir manual de administración</a></div></div>'),
        ('uso','Uso y alcance','<p>Descomprime el paquete y abre index.html. Búsqueda, temas, descarga e impresión funcionan localmente. Los anexos de inventario y validación describen el código; la evidencia productiva debe capturarse al instalar y aceptar la entrega.</p>'+nota('No es necesario salir de la app ni modificar datos para leer estos manuales. Su contenido no ejecuta conexiones ni configura servicios.'))])
    print('Documentación generada: '+str(SALIDA))


if __name__=='__main__':main()
