"""HTML de usuario y técnico desde Word privado; no publica adjuntos ni toca producción."""
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
import argparse
import xml.etree.ElementTree as X
import re,json,base64,hashlib,importlib.util
from html import escape as E

ROOT=Path(__file__).resolve().parents[1]
def modulo(nombre,archivo):
    spec=importlib.util.spec_from_file_location(nombre,ROOT/'scripts'/archivo)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
U=modulo('guia_usuario','generar_manual_usuario_completo.py')
M=modulo('manual_tecnico','generar_manual_tecnico_final.py')
D=modulo('manual_entrega','manual_entrega_tecnica.py')
MARCOS_VACIOS={24:'b0e1298f8ec911587d4a54aaceb05cc21a42eb9d514c09e3233cf01466135143',
               33:'807cdc1f5f29d4dc36cf8d6498da377a9ad153f0dd86c7135508d3c8cc50025b'}


def leer_word(archivo,salida):
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    pasos={};actual=None
    with ZipFile(archivo) as z:
        rel={r.get('Id'):r.get('Target') for r in X.fromstring(z.read('word/_rels/document.xml.rels'))}
        for p in X.fromstring(z.read('word/document.xml')).findall('.//w:body/w:p',ns):
            texto=''.join(e.text or '' for e in p.findall('.//w:t',ns))
            m=re.search(r'PASO\s*(\d+)\s*DE\s*\d+',texto,re.I)
            if m:actual=int(m[1]);pasos.setdefault(actual,{'textos':[],'imagenes':[]})
            if not actual:continue
            if texto:pasos[actual]['textos'].append(texto)
            for image in p.findall('.//a:blip',ns):
                target=rel.get(image.get('{'+ns['r']+'}embed'),'');pp=PurePosixPath(target)
                if not target.startswith('media/') or '..' in pp.parts or pp.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):continue
                info=z.getinfo('word/'+target)
                if info.file_size>20*1024*1024:raise ValueError('Imagen demasiado grande en Word.')
                data=z.read(info);ident=hashlib.sha256(data).hexdigest()
                dest=salida/'capturas'/('word-'+ident[:18]+pp.suffix.lower())
                dest.write_bytes(data)
                pasos[actual]['imagenes'].append({'archivo':dest.name,'original':pp.name,'sha256':ident,'origen':'WORD'})
    return pasos


def imagen(path,alt):
    mime='image/jpeg' if path.suffix.lower() in ('.jpg','.jpeg') else 'image/webp' if path.suffix=='.webp' else 'image/png'
    return '<img alt="'+E(alt)+'" src="data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()+'">'


EXTRA_CSS='''
.galeria-real{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:15px}.galeria-real img{width:100%;max-height:560px;object-fit:contain;cursor:zoom-in}.visual{break-inside:auto}.cambio{padding:13px;background:#f1f8ff;border-left:4px solid #225de2;margin:14px 0}.procedimiento{font-size:14px}dialog{border:0;border-radius:12px;max-width:96vw;max-height:96vh}dialog img{max-width:90vw;max-height:82vh;object-fit:contain}.alerta{background:#fff5da;padding:15px;border-left:4px solid #c08000}.folio-caption{font-size:12px;color:#526781}@media(max-width:650px){.galeria-real{grid-template-columns:1fr}}@media print{.step{break-inside:auto}.visual{break-inside:auto}.galeria-real{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4mm}.galeria-real img{width:100%;height:85mm;max-height:85mm;break-inside:avoid}.galeria-real.unica{grid-template-columns:1fr}.galeria-real.unica img{height:110mm;max-height:110mm}.visual figcaption{break-before:avoid}.step h2,.screen{break-after:avoid}.cambio{font-size:9pt;padding:3mm}.procedimiento{font-size:9pt}#paso-33 .galeria-real{grid-template-columns:1fr}dialog{display:none!important}}
'''


EDIT_JS=r'''
function actualizarReferencias(){const lista=[...document.querySelectorAll('.step[data-origen="PRUEBAS"]')].map(s=>s.dataset.paso);document.querySelector('#referencias-capturas').textContent=lista.length?'Las imágenes combinan capturas de operación y ejemplos de interfaz identificados con datos de prueba.':'Las imágenes corresponden a capturas aportadas por el responsable de la operación.';}
document.querySelectorAll('[data-captura]').forEach(input=>input.onchange=async()=>{
 const s=input.closest('.step'),host=s.querySelector('.galeria-real'),archivos=[...input.files];input.value='';if(!archivos.length)return;
 try{const imagenes=[];for(const f of archivos){if(!['image/png','image/jpeg','image/webp'].includes(f.type)||f.size>8*1024*1024)throw new Error('Usa PNG/JPG/WebP de hasta 8 MB por captura. Se conservaron las imágenes anteriores.');
  const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(new Error('No se pudo leer la captura.'));r.readAsDataURL(f);});const img=new Image();img.src=data;await img.decode();img.alt='Captura incorporada al paso '+s.dataset.paso;img.onclick=()=>ampliar(img.src);imagenes.push(img);}
  if(input.dataset.accion==='reemplazar')host.replaceChildren(...imagenes);else host.append(...imagenes);
  document.querySelector('[data-pdf-publicado]')?.remove();s.dataset.origen='RESPONSABLE';s.querySelector('.placeholder').hidden=true;host.classList.toggle('unica',host.children.length===1);
  s.querySelector('figcaption').textContent='Capturas incorporadas por el responsable para este paso. Revisar su contenido antes de distribuir.';actualizarReferencias();
  estado.textContent='Capturas del paso '+s.dataset.paso+' actualizadas localmente. Descarga el HTML y luego imprime ese archivo a PDF para conservar la misma versión.';
 }catch(e){estado.textContent=e.message||'No se pudo incorporar la imagen. Se conservaron las capturas anteriores.';}
});
function ampliar(src){document.querySelector('#vista-img').src=src;document.querySelector('#zoom').showModal();}
document.querySelectorAll('.galeria-real img').forEach(i=>i.onclick=()=>ampliar(i.src));document.querySelector('#cerrar-zoom').onclick=()=>document.querySelector('#zoom').close();
actualizarReferencias();
document.querySelector('#descargar').onclick=()=>{const d=document.documentElement.cloneNode(true);d.querySelectorAll('.step').forEach(s=>s.hidden=false);d.querySelector('#buscar').setAttribute('value','');d.querySelector('#zoom').removeAttribute('open');d.querySelector('#vista-img').removeAttribute('src');const u=URL.createObjectURL(new Blob(['<!doctype html>\n'+d.outerHTML],{type:'text/html;charset=utf-8'})),a=document.createElement('a');a.href=u;a.download='Manual-usuario-final-IV-ITSANET.html';a.click();setTimeout(()=>URL.revokeObjectURL(u),5000);};
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--word',type=Path,required=True);p.add_argument('--salida',type=Path,required=True);p.add_argument('--referencias',type=Path,required=True);p.add_argument('--revision',default='candidato-v72');p.add_argument('--version',type=int,choices=(70,71,72),default=72);p.add_argument('--captura-correos',type=Path,nargs='+');a=p.parse_args()
    if a.captura_correos:
        for f in a.captura_correos:
            if not f.is_file() or f.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or f.stat().st_size>8*1024*1024:p.error('Cada captura de correos debe ser PNG/JPG/WebP existente de hasta 8 MB.')
    a.salida.mkdir(parents=True,exist_ok=True);(a.salida/'capturas').mkdir(exist_ok=True)
    ws=leer_word(a.word,a.salida);datos=U.pasos();total=len(datos);result=[];referencias={24:'24-Edicion-recepcion-referencia.png',33:'33-Agrupacion-correos-referencia.png'}
    notas={7:'Al escanear un código relacionado se muestra el SKU canónico del cliente de la recepción. Los códigos compartidos entre clientes se resuelven con ese contexto.',
      8:'Primero pulsa Contar este producto o Agregar otro conteo si la ficha está en consulta. El botón Usar 1 empaque = N unidades aplica las unidades del empaque solo al pulsarlo. Para varios empaques, verifica su conversión a unidades físicas. Un factor vacío/cero debe revisarse.',
      15:'Filtros vigentes: Sin buscar, Faltan unidades, Sobran unidades, Con PNC, Adicionales y Completos. El cero confirmado es FALTANTE; No aparecieron ya no es una opción operativa. Los eventos antiguos se conservan.',
      19:'Para importar relaciones: Recepciones → Catálogo → Importar códigos de barras. Selecciona RELACION_CODIGOS.xlsx (RL_CODIGOS) y confirma. La importación valida todas las filas y separa las relaciones por CLIENTE_ID. No modifica existencias ni conteos. Si hay un conflicto, se revierte el archivo completo.',
      24:'Si reduces el total, confirma la consolidación y su motivo. El sistema conserva el historial y bloquea cambios que afecten bultos ocupados o impresiones en curso.',
      26:'En Qué etiquetas imprimir puedes elegir todas, números/rangos o subbultos registrados. Primero emite el rótulo del bulto padre; luego selecciona el subbulto, por ejemplo A01.1. No se crean cajas nuevas para imprimir. Las etiquetas de producto usan el código principal a todo el ancho, separado de los otros campos.',
      27:'El porcentaje de revisión no implica igualdad de cantidades. Un cero confirmado es una referencia revisada con faltante; no debe aparecer como trabajo sin buscar.',
      31:'Las categorías se materializan al subir. El archivo mantiene identidad estable y los accesos directos reutilizan ID en reintentos. No se borran duplicados históricos automáticamente.',
      32:'Gmail se autoriza desde la cuenta propia. Las fotos pueden usar la cuenta operativa central de Drive seleccionada por ADMIN. Si esa cuenta está REAUTORIZAR, el administrador debe reconectarla para Drive y guardar la cuenta operativa para reprogramar las copias en revisión.'}
    if a.version>=71:
        notas[12]='Guardar conteo respalda primero cantidades, ubicación, observación y fotos en este dispositivo. El aviso inicial es Pendiente de sincronizar. Solo Pendiente sincronizado confirma el servidor. Puedes seguir registrando varios conteos de los códigos descargados. Revisa la sección Respaldo de conteos en este dispositivo; permite sincronizar, revisar rechazos, descargar respaldo JSON con fotos y restaurarlo con la misma cuenta. No borres los datos del navegador. Si falta espacio, conserva la ficha: no se confirma un respaldo que falló.'
        notas[15]+=' Sin conexión, el avance es la última información confirmada; los pendientes locales no se suman a los indicadores. No se puede ver el trabajo nuevo de otros dispositivos hasta reconectar. Coordina físicamente el pallet para evitar contar las mismas unidades.'
        notas[37]='Antes de cerrar, sincroniza los pendientes de este dispositivo y confirma con el equipo que no quedan registros en otros equipos desconectados. Si la recepción se cerró mientras un equipo no tenía red, sus pendientes se conservan en revisión: el supervisor debe resolver el cierre antes de reintentar. Recargar o volver a entrar recupera la cola al autenticar la cuenta original; no se inicia sesión nueva sin servidor.'
        notas[38]='Durante un corte, continúa únicamente con los códigos descargados de la recepción abierta y guarda cada conteo. Comprueba el aviso de respaldo local y revisa la cola. Al reconectar se validará cada movimiento; no repitas el conteo con un identificador nuevo. Puedes descargar y restaurar el respaldo JSON desde la misma cuenta.'
    indice=''.join('<a href="#paso-'+str(i)+'">'+str(i).zfill(2)+' · '+E(d[1])+'</a>' for i,d in enumerate(datos,1));sections=''
    for i,d in enumerate(datos,1):
        rol,titulo,pantalla,acciones,comprobar,atencion,_=d;w=ws.get(i);imgs=list(w['imagenes']) if w else []
        if w:
            ts=w['textos'];where=next((j for j,t in enumerate(ts) if t.startswith('Dónde:')),None);check=next((j for j,t in enumerate(ts) if t.startswith('Comprueba:')),None)
            if where is not None and check is not None:
                acciones=ts[where+1:check];comprobar=ts[check].removeprefix('Comprueba:').strip()
            atencion=next((t.removeprefix('Ten en cuenta:').strip() for t in ts if t.startswith('Ten en cuenta:')),atencion)
        acciones=[re.sub(r'(?i)el paso 39', 'el diagnóstico de cámara del dispositivo', re.sub(r'(?i)el paso 40', 'el seguimiento de fotos y correos en Entregas',t)) for t in acciones]
        atencion=re.sub(r'(?i)el paso 39','el diagnóstico de cámara del dispositivo',re.sub(r'(?i)el paso 40','el seguimiento de fotos y correos en Entregas',atencion))
        if a.version>=71 and i==12:comprobar='Primero aparece Conteo pendiente de sincronizar y la cola del dispositivo aumenta. Solo Pendiente sincronizado confirma el registro en el servidor. Si falla el respaldo local, la ficha permanece abierta.'
        # Sustituir solo marcos vacíos conocidos; conservar capturas nuevas de un Word actualizado.
        if i in MARCOS_VACIOS:imgs=[im for im in imgs if im.get('sha256')!=MARCOS_VACIOS[i]]
        if i in referencias and not imgs:
            imgs=[];src=a.referencias/referencias[i]
            dest=a.salida/'capturas'/src.name;dest.write_bytes(src.read_bytes());imgs=[{'archivo':dest.name,'origen':'PRUEBAS','original':''}]
        if i==33 and a.captura_correos:
            imgs=[]
            for f in a.captura_correos:
                ident=hashlib.sha256(f.read_bytes()).hexdigest();dest=a.salida/'capturas'/('correos-'+ident[:18]+f.suffix.lower());dest.write_bytes(f.read_bytes());imgs.append({'archivo':dest.name,'origen':'RESPONSABLE','original':f.name})
        caption=('Captura de la operación documentada.' if imgs and imgs[0]['origen']=='WORD' else 'Captura de operación aportada por el responsable.' if imgs and imgs[0]['origen']=='RESPONSABLE' else 'Ejemplo de interfaz con datos de prueba.' if imgs else 'Procedimiento descrito en los pasos anteriores.')
        resultado={'paso':i,'imagenes':len(imgs),'origen':imgs[0]['origen'] if imgs else 'PENDIENTE','restituido':not bool(w)};result.append(resultado)
        extra=''
        if i in notas:extra+='<div class="cambio"><b>Criterio operativo:</b> '+E(notas[i])+'</div>'
        gal=''.join(imagen(a.salida/'capturas'/im['archivo'],f'Paso {i}: {titulo} · captura {j}') for j,im in enumerate(imgs,1))
        sections+='<section class="step" id="paso-'+str(i)+'" data-paso="'+str(i)+'" data-origen="'+resultado['origen']+'"><div class="tag">Paso '+str(i).zfill(2)+' de '+str(total)+' · '+E(rol)+'</div><h2>'+E(titulo)+'</h2><p class="screen"><b>Dónde:</b> '+E(pantalla)+'</p><ol>'+''.join('<li>'+E(x)+'</li>' for x in acciones)+'</ol><div class="result"><b>Comprueba:</b> '+E(comprobar)+'</div>'+extra+'<figure class="visual"><div class="galeria-real '+('unica' if len(imgs)==1 else '')+'">'+gal+'</div><div class="placeholder" '+('hidden' if imgs else '')+'><strong>Captura por completar · paso '+str(i)+'</strong><p>'+E(pantalla)+'</p></div><figcaption>'+caption+'</figcaption></figure><div class="attention"><b>Ten en cuenta:</b> '+E(atencion)+'</div><div class="edit"><label>Reemplazar capturas del paso <input data-captura data-accion="reemplazar" type="file" multiple accept="image/png,image/jpeg,image/webp"></label><label>Añadir capturas adicionales <input data-captura data-accion="anadir" type="file" multiple accept="image/png,image/jpeg,image/webp"></label></div><div class="links"><a href="#indice">Índice</a><a href="#'+('paso-'+str(i+1) if i<total else 'indice')+'">'+('Siguiente →' if i<total else 'Volver al índice')+'</a></div></section>'
    cover='''<section class="cover" id="portada"><div class="tag">IV ITSANET · Guía de operación · 09/11/2026</div><h1>Manual de usuario</h1><h2>Ingreso &amp; Validación Itsanet</h2><p>Guía de acceso, registro, validación, novedades, evidencias e informes para operarios y supervisores.</p><ul><li>Acceso y orientación: pasos 01–03.</li><li>Operario: pasos 04–18.</li><li>Supervisor: pasos 19–37.</li><li>Ayuda: paso 38.</li></ul><p><span id="referencias-capturas">Capturas de operación y ejemplos de interfaz identificados.</span></p><p>El HTML funciona sin conexión. Pulsa una imagen para ampliarla. La edición local permite reemplazar o añadir capturas y descargar el documento; no modifica datos del aplicativo.</p><p>Acceso: https://apps.flexnetuio.com:8443/app/</p></section>'''
    h='<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IV ITSANET · Manual de usuario final</title><style>'+U.CSS+EXTRA_CSS+'</style></head><body><header><b>IV ITSANET · Manual de usuario final</b><p>Capturas del Word V2 · 38 pasos · operación y supervisión</p><div class="toolbar"><button id="imprimir">Imprimir / PDF</button><button id="descargar">Descargar HTML con capturas</button></div><p id="estado">Documento interno: revisar los datos visibles antes de distribuir.</p></header><main class="layout"><nav><input id="buscar" aria-label="Buscar pasos" placeholder="Buscar en el manual"><button id="ver-todo">Ver todo</button>'+indice+'</nav><div class="content">'+cover+'<section class="indice" id="indice"><h2>Índice</h2><div class="columns">'+indice+'</div></section>'+sections+'</div></main><dialog id="zoom"><button id="cerrar-zoom">Cerrar</button><br><img id="vista-img" alt="Captura ampliada"></dialog><script>'+U.JS+'</script><script>'+EDIT_JS+'</script></body></html>'
    h=h.replace('Capturas del Word V2 · 38 pasos · operación y supervisión','38 pasos · operación y supervisión')
    (a.salida/'Manual-usuario-final-IV-ITSANET.html').write_text(h)
    audit={'word':a.word.name,'sha256Word':hashlib.sha256(a.word.read_bytes()).hexdigest(),'pasosWord':len(ws),'pasosFinales':total,'hallazgos':['El título de portada se unifica a IV ITSANET.','Se elimina repetición de Dónde y leyendas de pruebas que no corresponden a las capturas reales.','Se eliminan los pasos 39 y 40 por solicitud del responsable; el manual conserva 38 pasos.','Se sustituyen marcos vacíos de pasos 24 y 33 por referencias de pruebas identificadas.','Se conserva el orden de las capturas aportadas y se añaden notas de cambios de la versión 70.'],'pasos':result}
    audit['version']=a.version;audit['hallazgos'][-1]=f'Se conserva el orden de las capturas aportadas y se añaden notas de cambios hasta la versión {a.version}.'
    (a.salida/'Revision-del-Word-V2.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    M.REF=a.revision;M.B.REVISION=a.revision;M.FECHA='9 de noviembre de 2026'
    inv=M.B.inventario();inv.update(fecha='2026-11-09',revisionCodigo=a.revision,tablasDetalle=M.diccionario())
    ss=M.secciones(inv,inv['tablasDetalle'])
    ss=[(k,t,c.replace('<b>30 tablas</b>','<b>31 tablas</b>').replace('v69 · recursos 20261024-69','v70 · recursos 20261109-70')) for k,t,c in ss]
    ss.insert(-1,('cambios70','Cambios preparados en la versión 70',M.T(['Componente','Implementación'],[
        ['Relaciones de productos','Nueva tabla producto_relaciones con clave cliente+código, SKU y unidades por empaque. No modifica la PK del maestro global ni los conteos existentes.'],
        ['Importación','RL_CODIGOS, hasta 20000 filas. Validación completa, transacción atómica, auditoría e idempotencia. Vacíos no borran factores conocidos.'],
        ['Lectura','Contexto de cliente/recepción; UPC-A/EAN-13 equivalentes solo con dígito válido. Conflictos se bloquean. El factor se aplica con acción explícita.'],
        ['Filtros','Cero verificado se presenta como FALTANTE. Se retira No aparecieron de filtros/KPI y se mantiene compatibilidad de eventos históricos.'],
        ['Bultos','Edición del total con confirmación/motivo al reducir; controles de versión, ocupación e impresiones en curso. Subbultos impresos desde cajas ya registradas.'],
        ['Etiquetas','Producto de 100×50 mm con barras principales a todo el ancho, texto SKU separado y áreas sin superposición. El código no se recorta para hacerlo caber.'],
        ['Drive','Carpetas/archivos con ID reservado; accesos directos también reservan identidad por destino+archivo. No se borran duplicados históricos.']])+ '<p>El modelo declara 31 tablas tras el cambio. La instalación existente y la exposición del servidor deben cotejarse; no se ha accedido a producción ni se ha importado el archivo corporativo en ella. La separación de relaciones por cliente no acredita por sí sola segregación integral multicliente de todas las funciones.</p>'))
    for archivo in ('Etiqueta-producto-mejorada.png','Etiqueta-subbulto-A01-1.png'):
        src=a.referencias/archivo
        dest=a.salida/'capturas'/archivo;dest.write_bytes(src.read_bytes())
        k,t,c=ss[-2]
        c+='<figure style="margin:20px 0;text-align:center">'+imagen(dest,'Interfaz de pruebas v70 · '+archivo).replace('<img ','<img style="max-width:100%;max-height:340px;object-fit:contain" ')+'<figcaption>Interfaz de referencia ejecutada en pruebas; datos sintéticos.</figcaption></figure>'
        ss[-2]=(k,t,c)
    if a.version>=71:
        ss.insert(-1,('continuidad71','Continuidad operativa y recuperación · versión 71',M.T(['Control','Implementación'],[
            ['Escritura previa','IndexedDB del navegador confirma cada trabajo, incluidos los binarios de las fotos, antes de liberar la ficha. Un fallo de cuota o almacenamiento conserva el formulario y no anuncia éxito.'],
            ['Identidad','Cada conteo mantiene su clave de idempotencia, cuenta, recepción, SKU, cantidades, origen, pallet e incidencias. Varias pestañas coordinan el envío mediante arrendamiento atómico de 60 segundos, renovado cada 15.'],
            ['Sincronización','La página de validación reintenta con espera progresiva y al recuperar conexión. No requiere que el navegador soporte Background Sync. Con la aplicación cerrada no se ejecuta el envío; la cola se recupera al volver con la cuenta original.'],
            ['Fotografías','Se recuperan los binarios, se comprimen y suben; el enlace de cada foto queda registrado localmente antes de enviar el conteo. No se confirma un conteo con fotos seleccionadas sin sus enlaces confirmados. La copia posterior a Drive conserva su cola existente.'],
            ['Confirmación','Solo el ACK del servidor cambia a CONFIRMADO y libera los binarios de la cola local. Una respuesta perdida se reintenta con la misma clave. Los campos capturadoEnDispositivo y dispositivoOrigen son informativos; creado_en es la fecha del servidor.'],
            ['Revalidación','El servidor aplica los bloqueos y validaciones actuales. Sobrante, reparto desactualizado, recepción cerrada o falta de permiso quedan en REVISION, sin confirmación automática ni descarte. Se comprueba el operador original en el servidor.'],
            ['Lecturas locales','GET autenticado /api/app/recepciones/{codigo}/lecturas-locales: solo SKU de esta recepción y relaciones de su cliente, con equivalencias deterministas. Sin red se rechazan códigos desconocidos o ambiguos. No se autentica una sesión nueva sin servidor.'],
            ['Rescate','Descarga/restauración JSON con fotos e identificadores originales, exclusivamente para la misma cuenta. Los pendientes no se eliminan por antigüedad. No se garantiza supervivencia a borrado de datos del navegador, daño o pérdida del dispositivo; descargar respaldos ante incidencias.'],
            ['Visibilidad','Los indicadores conservan únicamente totales del servidor. Un dispositivo sin conexión no puede comunicar conteos nuevos ni presencias al resto; el cierre requiere verificar los equipos del equipo operativo. El cliente detiene su cierre si tiene pendientes locales.']
        ])+'<p>La cola local no añade tablas MySQL ni modifica Apache. Componentes: conteos-pendientes.js, cola-conteos-ui.js, validar.html, lecturas.py y comprobación de identidad en las rutas de conteo. La protección de los equipos y del perfil de navegador forma parte de la custodia operativa de los pendientes.</p>'))
    if a.version>=72:
        ss.insert(-1,('manuales72','Publicación y mantenimiento de manuales',M.T(['Documento','Ubicación y acceso'],[
            ['Manual de usuario','documentacion/manuales/usuario/versiones/<version>. HTML y PDF se publican juntos. Menú → Manual de usuario · HTML y PDF. Ruta autenticada /api/app/manuales/usuario/html.'],
            ['Manual técnico','documentacion/manuales/tecnico/versiones/<version>, acceso local de mantenimiento. No tiene ruta HTTP ni enlace desde la aplicación.'],
            ['Actualización','scripts/publicar_manuales.py valida los 38 pasos y los archivos, conserva versiones y cambia el puntero actual.json después de escribir el par completo. No reinicia servicios ni cambia datos operativos.'],
            ['Protección','Los documentos publicados se excluyen de Git. El HTML usa una política de contenido aislada; no puede consultar las APIs de la aplicación. La sesión se comprueba antes de servir cualquier manual de usuario.'],
            ['Respaldo','respaldo_produccion.py incorpora documentacion/manuales al respaldo de archivos cuando existe. El manual técnico queda en carpetas privadas, sin exposición web.'],
            ['Capturas y PDF','El manual de usuario conserva 38 pasos. El paso 33 admite reemplazar las capturas en el HTML o cargar PNG/JPG/WebP con --captura-correos. Después se genera el PDF desde el mismo HTML y se publica de nuevo el par.']
        ])+'<p>La opción PDF requiere Chrome/Chromium/Edge ya instalado; también se puede imprimir el HTML a PDF en el computador del responsable. No se instala software ni se modifica Apache para generar documentos. La documentación no acredita por sí sola que la revisión de código o sus manuales hayan sido publicados en el servidor.</p>'))
    continuidad=next((c for k,t,c in ss if k=='continuidad71'),'')
    publicacion=next((c for k,t,c in ss if k=='manuales72'),'')
    publicacion=publicacion.replace(' La documentación no acredita por sí sola que la revisión de código o sus manuales hayan sido publicados en el servidor.','')
    ss=D.secciones(M,inv,inv['tablasDetalle'],continuidad,publicacion)
    old=M.secciones;M.secciones=lambda *args:ss
    try:tecnico=M.manual(inv,inv['tablasDetalle'])
    finally:M.secciones=old
    tecnico=tecnico.replace('20261028','20261109').replace('Manual-tecnico-ITSANET-20261109.html','Manual-tecnico-final-IV-ITSANET.html')
    (a.salida/'Manual-tecnico-final-IV-ITSANET.html').write_text(tecnico)
    (a.salida/f'Inventario-tecnico-v{a.version}.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2))
    print(json.dumps({'salida':str(a.salida),'pasos':total,'capturas':sum(x['imagenes'] for x in result),'tablas':len(inv['tablasDetalle'])}))


if __name__=='__main__':main()
