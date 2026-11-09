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


def leer_word(archivo,salida):
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    pasos={};actual=None
    with ZipFile(archivo) as z:
        rel={r.get('Id'):r.get('Target') for r in X.fromstring(z.read('word/_rels/document.xml.rels'))}
        for p in X.fromstring(z.read('word/document.xml')).findall('.//w:body/w:p',ns):
            texto=''.join(e.text or '' for e in p.findall('.//w:t',ns))
            m=re.search(r'PASO\s*(\d+)\s*DE\s*40',texto,re.I)
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
.galeria-real{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:15px}.galeria-real img{width:100%;max-height:560px;object-fit:contain;cursor:zoom-in}.visual{break-inside:auto}.cambio{padding:13px;background:#f1f8ff;border-left:4px solid #225de2;margin:14px 0}.procedimiento{font-size:14px}dialog{border:0;border-radius:12px;max-width:96vw;max-height:96vh}dialog img{max-width:90vw;max-height:82vh;object-fit:contain}.alerta{background:#fff5da;padding:15px;border-left:4px solid #c08000}.folio-caption{font-size:12px;color:#526781}@media(max-width:650px){.galeria-real{grid-template-columns:1fr}}@media print{.step{break-inside:auto}.visual{break-inside:auto}.galeria-real{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4mm}.galeria-real img{width:100%;height:85mm;max-height:85mm;break-inside:avoid}.galeria-real.unica{grid-template-columns:1fr}.galeria-real.unica img{height:110mm;max-height:110mm}.visual figcaption{break-before:avoid}.step h2,.screen{break-after:avoid}.cambio{font-size:9pt;padding:3mm}.procedimiento{font-size:9pt}dialog{display:none!important}}
'''


EDIT_JS=r'''
document.querySelectorAll('[data-captura]').forEach(input=>input.onchange=async()=>{const s=input.closest('.step'),host=s.querySelector('.galeria-real');for(const f of [...input.files]){if(!['image/png','image/jpeg','image/webp'].includes(f.type)||f.size>8*1024*1024){estado.textContent='Usa PNG/JPG/WebP de hasta 8 MB por captura.';continue;}const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(f);});const img=new Image();img.src=data;img.alt='Captura añadida al paso '+s.dataset.paso;img.onclick=()=>ampliar(img.src);host.append(img);s.querySelector('.placeholder').hidden=true;host.classList.toggle('unica',host.children.length===1);}estado.textContent='Capturas agregadas localmente. Descarga el HTML para conservarlas.';});
function ampliar(src){document.querySelector('#vista-img').src=src;document.querySelector('#zoom').showModal();}
document.querySelectorAll('.galeria-real img').forEach(i=>i.onclick=()=>ampliar(i.src));document.querySelector('#cerrar-zoom').onclick=()=>document.querySelector('#zoom').close();
document.querySelector('#descargar').onclick=()=>{const d=document.documentElement.cloneNode(true);d.querySelectorAll('.step').forEach(s=>s.hidden=false);d.querySelector('#buscar').setAttribute('value','');d.querySelector('#zoom').removeAttribute('open');d.querySelector('#vista-img').removeAttribute('src');const u=URL.createObjectURL(new Blob(['<!doctype html>\n'+d.outerHTML],{type:'text/html;charset=utf-8'})),a=document.createElement('a');a.href=u;a.download='Manual-usuario-final-IV-ITSANET.html';a.click();setTimeout(()=>URL.revokeObjectURL(u),5000);};
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--word',type=Path,required=True);p.add_argument('--salida',type=Path,required=True);p.add_argument('--referencias',type=Path,required=True);p.add_argument('--revision',default='candidato-v70');a=p.parse_args()
    a.salida.mkdir(parents=True,exist_ok=True);(a.salida/'capturas').mkdir(exist_ok=True)
    ws=leer_word(a.word,a.salida);datos=U.pasos();result=[];referencias={24:'24-Edicion-recepcion-referencia.png',33:'33-Agrupacion-correos-referencia.png'}
    notas={7:'Al escanear un código relacionado se muestra el SKU canónico del cliente de la recepción. Los códigos compartidos entre clientes se resuelven con ese contexto.',
      8:'Primero pulsa Contar este producto o Agregar otro conteo si la ficha está en consulta. El botón Usar 1 empaque = N unidades aplica las unidades del empaque solo al pulsarlo. Para varios empaques, verifica su conversión a unidades físicas. Un factor vacío/cero debe revisarse.',
      15:'Filtros vigentes: Sin buscar, Faltan unidades, Sobran unidades, Con PNC, Adicionales y Completos. El cero confirmado es FALTANTE; No aparecieron ya no es una opción operativa. Los eventos antiguos se conservan.',
      19:'Para importar relaciones: Recepciones → Catálogo → Importar códigos de barras. Selecciona RELACION_CODIGOS.xlsx (RL_CODIGOS) y confirma. La importación valida todas las filas y separa las relaciones por CLIENTE_ID. No modifica existencias ni conteos. Si hay un conflicto, se revierte el archivo completo.',
      24:'Si reduces el total, confirma la consolidación y su motivo. El sistema conserva el historial y bloquea cambios que afecten bultos ocupados o impresiones en curso.',
      26:'En Qué etiquetas imprimir puedes elegir todas, números/rangos o subbultos registrados. Primero emite el rótulo del bulto padre; luego selecciona el subbulto, por ejemplo A01.1. No se crean cajas nuevas para imprimir. Las etiquetas de producto usan el código principal a todo el ancho, separado de los otros campos.',
      27:'El porcentaje de revisión no implica igualdad de cantidades. Un cero confirmado es una referencia revisada con faltante; no debe aparecer como trabajo sin buscar.',
      31:'Las categorías se materializan al subir. El archivo mantiene identidad estable y los accesos directos reutilizan ID en reintentos. No se borran duplicados históricos automáticamente.',
      32:'Gmail se autoriza desde la cuenta propia. Las fotos pueden usar la cuenta operativa central de Drive seleccionada por ADMIN. Si esa cuenta está REAUTORIZAR, el administrador debe reconectarla para Drive y guardar la cuenta operativa para reprogramar las copias en revisión.'}
    indice=''.join('<a href="#paso-'+str(i)+'">'+str(i).zfill(2)+' · '+E(d[1])+'</a>' for i,d in enumerate(datos,1));sections=''
    for i,d in enumerate(datos,1):
        rol,titulo,pantalla,acciones,comprobar,atencion,_=d;w=ws.get(i);imgs=list(w['imagenes']) if w else []
        if w:
            ts=w['textos'];where=next((j for j,t in enumerate(ts) if t.startswith('Dónde:')),None);check=next((j for j,t in enumerate(ts) if t.startswith('Comprueba:')),None)
            if where is not None and check is not None:
                acciones=ts[where+1:check];comprobar=ts[check].removeprefix('Comprueba:').strip()
            atencion=next((t.removeprefix('Ten en cuenta:').strip() for t in ts if t.startswith('Ten en cuenta:')),atencion)
        # En el Word suministrado estos dos archivos son los marcos vacíos comprobados.
        if i in referencias:
            imgs=[];src=a.referencias/referencias[i]
            dest=a.salida/'capturas'/src.name;dest.write_bytes(src.read_bytes());imgs=[{'archivo':dest.name,'origen':'PRUEBAS','original':''}]
        caption=('Capturas reales aportadas en el Word V2. Pueden mostrar la interfaz anterior a los ajustes de esta versión.' if imgs and imgs[0]['origen']=='WORD' else 'Referencia tomada de la interfaz ejecutada en pruebas con datos sintéticos; sustituir por captura de la recepción autorizada.' if imgs else 'Paso restituido de la guía: falta incorporar su captura real.')
        resultado={'paso':i,'imagenes':len(imgs),'origen':imgs[0]['origen'] if imgs else 'PENDIENTE','restituido':not bool(w)};result.append(resultado)
        extra=''
        if i==33:
            extra='''<div class="cambio procedimiento"><b>Cómo tomar la captura real de este punto</b><ol><li>Entra como supervisor y abre una recepción autorizada con más de un packing list o embarque.</li><li>Abre Informes → Correo final editable y, en el diálogo de correos, pulsa Elegir: por packing list o por embarque.</li><li>En Organizar correos de la recepción, abre Preparar y revisar. Deben verse: Un correo por cada packing list, Un correo por cada embarque y Un correo consolidado de toda la recepción.</li><li>Captura el diálogo antes de guardar la organización o enviar. En Windows puedes usar Recortes con retardo y desplegar la lista durante la espera.</li><li>Añade el PNG con el control de este paso y descarga el HTML completado. No muestres destinatarios ajenos al procedimiento.</li></ol></div>'''
        if i in notas:extra+='<div class="cambio"><b>Actualización de la guía:</b> '+E(notas[i])+'</div>'
        gal=''.join(imagen(a.salida/'capturas'/im['archivo'],f'Paso {i}: {titulo} · captura {j}') for j,im in enumerate(imgs,1))
        sections+='<section class="step" id="paso-'+str(i)+'" data-paso="'+str(i)+'"><div class="tag">Paso '+str(i).zfill(2)+' de 40 · '+E(rol)+'</div><h2>'+E(titulo)+'</h2><p class="screen"><b>Dónde:</b> '+E(pantalla)+'</p><ol>'+''.join('<li>'+E(x)+'</li>' for x in acciones)+'</ol><div class="result"><b>Comprueba:</b> '+E(comprobar)+'</div>'+extra+'<figure class="visual"><div class="galeria-real '+('unica' if len(imgs)==1 else '')+'">'+gal+'</div><div class="placeholder" '+('hidden' if imgs else '')+'><strong>Captura por completar · paso '+str(i)+'</strong><p>'+E(pantalla)+'</p></div><figcaption>'+caption+'</figcaption></figure><div class="attention"><b>Ten en cuenta:</b> '+E(atencion)+'</div><div class="edit"><label>Añadir capturas de este paso <input data-captura type="file" multiple accept="image/png,image/jpeg,image/webp"></label></div><div class="links"><a href="#indice">Índice</a><a href="#paso-'+str(min(40,i+1))+'">Siguiente →</a></div></section>'
    cover='''<section class="cover" id="portada"><div class="tag">IV ITSANET · Edición de referencia 70 · 09/11/2026</div><h1>Manual de usuario</h1><h2>Ingreso &amp; Validación Itsanet</h2><p>Guía para operarios y supervisores. Incluye las capturas reales del Word V2 recibido, los pasos de ayuda restituidos y las actualizaciones preparadas para la versión 70.</p><ul><li>Acceso y orientación: pasos 01–03.</li><li>Operario: pasos 04–18.</li><li>Supervisor: pasos 19–37.</li><li>Ayuda: pasos 38–40.</li></ul><p class="alerta">Las capturas del Word corresponden a la operación documentada por su responsable. Los pasos 24 y 33 contienen una referencia de pruebas identificada; los pasos 39 y 40 requieren captura real. Las mejoras de la versión 70 se utilizan después del pase controlado; este manual no acredita que el servidor haya sido actualizado.</p><p>El HTML funciona sin conexión. Pulsa una imagen para ampliarla. Puedes añadir capturas y descargar el HTML completado; no se suben archivos al aplicativo.</p><p>Acceso: https://apps.flexnetuio.com:8443/app/</p></section>'''
    h='<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IV ITSANET · Manual de usuario final</title><style>'+U.CSS+EXTRA_CSS+'</style></head><body><header><b>IV ITSANET · Manual de usuario final</b><p>Capturas del Word V2 · operación y supervisión</p><div class="toolbar"><button id="imprimir">Imprimir / PDF</button><button id="descargar">Descargar HTML con capturas</button></div><p id="estado">Documento interno: revisar los datos visibles antes de distribuir.</p></header><main class="layout"><nav><input id="buscar" aria-label="Buscar pasos" placeholder="Buscar en el manual"><button id="ver-todo">Ver todo</button>'+indice+'</nav><div class="content">'+cover+'<section class="indice" id="indice"><h2>Índice</h2><div class="columns">'+indice+'</div></section>'+sections+'</div></main><dialog id="zoom"><button id="cerrar-zoom">Cerrar</button><br><img id="vista-img" alt="Captura ampliada"></dialog><script>'+U.JS+'</script><script>'+EDIT_JS+'</script></body></html>'
    (a.salida/'Manual-usuario-final-IV-ITSANET.html').write_text(h)
    audit={'word':a.word.name,'sha256Word':hashlib.sha256(a.word.read_bytes()).hexdigest(),'pasosWord':len(ws),'pasosFinales':40,'hallazgos':['El título de portada se unifica a IV ITSANET.','Se elimina repetición de Dónde y leyendas de pruebas que no corresponden a las capturas reales.','Se restituyen pasos 39 y 40, ausentes en el Word.','Se sustituyen marcos vacíos de pasos 24 y 33 por referencias de pruebas identificadas.','Se conserva el orden de las capturas aportadas y se añaden notas de cambios de la versión 70.'],'pasos':result}
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
    old=M.secciones;M.secciones=lambda *args:ss
    try:tecnico=M.manual(inv,inv['tablasDetalle'])
    finally:M.secciones=old
    tecnico=tecnico.replace('20261028','20261109').replace('revisión 1.1','revisión documental 70').replace('Manual-tecnico-ITSANET-20261109.html','Manual-tecnico-final-IV-ITSANET.html')
    tecnico=tecnico.replace('Estado operativo</td><td>En línea, confirmado por el responsable el 28/10/2026.','Estado operativo</td><td>Referencia de producción previa v69; candidato v70 preparado, instalación actual por cotejar.')
    (a.salida/'Manual-tecnico-final-IV-ITSANET.html').write_text(tecnico)
    (a.salida/'Inventario-tecnico-v70.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2))
    print(json.dumps({'salida':str(a.salida),'pasos':40,'capturas':sum(x['imagenes'] for x in result),'tablas':len(inv['tablasDetalle'])}))


if __name__=='__main__':main()
