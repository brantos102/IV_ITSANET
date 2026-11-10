"""HTML autónomos y ZIP reproducible: python scripts/generar_manuales.py."""
from pathlib import Path
from html import escape
import base64
import hashlib
import json
import zipfile

RAIZ=Path(__file__).resolve().parents[1]
FUENTES=RAIZ/'docs/manuales'
SALIDA=RAIZ/'firebase/public/manuales'
EDICION='47'


def banco_faq(ident):
    preguntas=json.loads((FUENTES/'faq.json').read_text())
    preguntas=[p for p in preguntas if ident in p['roles']]
    categorias=sorted({p['categoria'] for p in preguntas})
    opciones=''.join(f'<option>{escape(c)}</option>' for c in categorias)
    filas=''.join(f'<details data-faq-item data-category="{escape(p["categoria"])}" id="faq-{escape(p["id"])}"><summary>{escape(p["pregunta"])}</summary><span class="faq-category">{escape(p["categoria"])}</span><div class="faq-answer">{p["respuesta"]}</div></details>' for p in preguntas)
    return f'''<p>Busca tu duda y abre la respuesta. Puedes volver a consultar este banco en cualquier momento, sin conexión.</p><div class="faq-tools"><label>Tu pregunta<input data-faq-search type="search" placeholder="Ejemplo: foto duplicada, cámara, correo…" aria-label="Buscar preguntas frecuentes"></label><label>Tema<select data-faq-category aria-label="Filtrar preguntas por tema"><option value="">Todos los temas</option>{opciones}</select></label></div><div class="actions"><button data-faq-expand>Expandir respuestas visibles</button><button data-faq-reset>Limpiar filtros</button><span data-faq-count role="status" aria-live="polite"></span></div><p data-faq-empty hidden>No encontramos esa pregunta. Prueba con otra palabra o consulta al supervisor indicando recepción, hora y mensaje, sin compartir claves.</p><div class="faq-list">{filas}</div>'''


def generar():
    SALIDA.mkdir(parents=True,exist_ok=True)
    css=(FUENTES/'manual.css').read_text()
    js=(FUENTES/'manual.js').read_text()
    logo=base64.b64encode((RAIZ/'firebase/public/logo-itsa.png').read_bytes()).decode()
    manuales=json.loads((FUENTES/'contenido.json').read_text())
    for ident,datos in manuales.items():
        datos['temas']=[*datos['temas'],{'id':'faq','titulo':'Preguntas frecuentes · FAQ','html':banco_faq(ident)}]
        nav='\n'.join(f'<button type="button" data-section="{escape(t["id"])}"><span class="num">{i+1:02d}</span><span>{escape(t["titulo"])}</span><span class="done" aria-hidden="true"></span></button>' for i,t in enumerate(datos['temas']))
        capitulos='\n'.join(f'<article class="chapter" id="{escape(t["id"])}" hidden><span class="eyebrow">Tema {i+1:02d} · {escape(datos["rol"])}</span><h2>{escape(t["titulo"])}</h2>{t["html"]}</article>' for i,t in enumerate(datos['temas']))
        texto=f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{escape(datos['subtitulo'])}"><title>ITSANET · {escape(datos['titulo'])}</title>
<style>{css}</style></head>
<body data-manual="{ident}" data-edition="{EDICION}">
<header class="top"><a class="brand" href="#" aria-label="ITSANET · guía"><img src="data:image/png;base64,{logo}" alt="ITSA"></a><div class="edition">GUÍAS INTERACTIVAS<br>Edición {EDICION} · App 47 · 18 octubre 2026</div><div class="top-actions"><button data-open-faq>¿Necesitas ayuda?</button><button data-download>↓ Descargar HTML</button><button data-print>Imprimir / PDF</button><button data-theme aria-label="Cambiar tema">☾</button></div></header>
<main class="layout"><aside class="sidebar"><label>BUSCAR UNA TAREA<input type="search" data-search aria-label="Buscar en el manual" placeholder="Código, fotos, cierre…"></label><div class="learning"><span class="ring" data-ring role="img" aria-label="Avance del manual"><span>0%</span></span><p><strong data-learning></strong><br>Tu avance se guarda en este navegador.</p></div><nav class="chapter-nav" aria-label="Temas del manual">{nav}</nav><p class="empty" data-empty hidden>No hay temas con esa búsqueda.</p><div class="role-links"><a href="operario.html">Operario</a><a href="supervisor.html">Supervisor</a><a href="instalacion-supervisor.html">Instalar / configurar</a><a href="tecnico.html">Informe TI</a></div><p class="muted" style="font-size:11px">Archivo autónomo. Las prácticas usan datos ficticios y no se conectan a la aplicación.</p></aside>
<div class="content"><section class="intro"><span class="eyebrow">ITSANET · {escape(datos['rol'])}</span><h1>{escape(datos['titulo'])}</h1><p>{escape(datos['subtitulo'])}</p><div class="badges"><span class="badge">Sin conexión</span><span class="badge">Prácticas + FAQ</span><span class="badge">App 47 · Fotos auditables</span></div></section>{capitulos}<footer class="chapter-footer"><button data-prev>← Anterior</button><label><input type="checkbox" data-read>Ya revisé este tema</label><small data-page></small><button class="primary" data-next>Siguiente →</button></footer><p class="bottom-note">ITSANET · Guía {EDICION} · Los registros operativos se realizan en la app, con la cuenta y el entorno correctos.</p></div></main>
<script>{js}</script></body></html>'''
        (SALIDA/(ident+'.html')).write_text(texto,encoding='utf-8')
    salida_zip=RAIZ/f'docs/descargas/ITSANET-manuales-v{EDICION}.zip'
    salida_zip.parent.mkdir(parents=True,exist_ok=True)
    archivos={ident+'.html':(SALIDA/(ident+'.html')).read_bytes() for ident in manuales}
    archivos['LEEME.txt']=(f'ITSANET - Guías interactivas {EDICION} / aplicación 47\nExtrae TODO el ZIP y abre operario.html, supervisor.html, instalacion-supervisor.html o tecnico.html con Chrome, Edge o Firefox.\nLos cuatro archivos incluyen código, estilos y logo: las prácticas y FAQ funcionan sin Internet. Los enlaces a la app, Google y GitHub sí necesitan conexión.\nLas prácticas son simulaciones con datos ficticios y no escriben en la app. El progreso se guarda en el navegador cuando permite almacenamiento local.\nPara usar la app, cada supervisor necesita navegador, enlace correcto y cuenta aprobada. Solo el equipo anfitrión de pruebas necesita Docker; no cada supervisor.\nGoogle se configura una vez por cuenta con asistencia de ADMIN y autorización del propietario. Nunca introduzcas claves en estas guías.\nPulsa Descargar HTML para guardar otra copia; Imprimir / PDF incluye todos los temas y FAQ.\nEl informe TI distingue comprobaciones automatizadas y aceptación física pendiente.\n').encode('utf-8')
    with zipfile.ZipFile(salida_zip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for nombre,contenido in sorted(archivos.items()):
            info=zipfile.ZipInfo(nombre,date_time=(2026,10,18,12,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,contenido)
    (salida_zip.with_suffix('.sha256')).write_text(hashlib.sha256(salida_zip.read_bytes()).hexdigest()+'  '+salida_zip.name+'\n')
    return salida_zip


if __name__=='__main__':
    print(generar().relative_to(RAIZ))
