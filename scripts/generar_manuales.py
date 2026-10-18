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


def generar():
    SALIDA.mkdir(parents=True,exist_ok=True)
    css=(FUENTES/'manual.css').read_text()
    js=(FUENTES/'manual.js').read_text()
    logo=base64.b64encode((RAIZ/'firebase/public/logo-itsa.png').read_bytes()).decode()
    manuales=json.loads((FUENTES/'contenido.json').read_text())
    for ident,datos in manuales.items():
        nav='\n'.join(f'<button type="button" data-section="{escape(t["id"])}"><span class="num">{i+1:02d}</span><span>{escape(t["titulo"])}</span><span class="done" aria-hidden="true"></span></button>' for i,t in enumerate(datos['temas']))
        capitulos='\n'.join(f'<article class="chapter" id="{escape(t["id"])}" hidden><span class="eyebrow">Tema {i+1:02d} · {escape(datos["rol"])}</span><h2>{escape(t["titulo"])}</h2>{t["html"]}</article>' for i,t in enumerate(datos['temas']))
        texto=f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{escape(datos['subtitulo'])}"><title>ITSANET · {escape(datos['titulo'])}</title>
<style>{css}</style></head>
<body data-manual="{ident}">
<header class="top"><a class="brand" href="#" aria-label="ITSANET · guía"><img src="data:image/png;base64,{logo}" alt="ITSA"></a><div class="edition">GUÍAS INTERACTIVAS<br>Versión 43 · 18 de octubre de 2026</div><div class="top-actions"><button data-download>↓ Descargar HTML</button><button data-print>Imprimir / PDF</button><button data-theme aria-label="Cambiar tema">☾</button></div></header>
<main class="layout"><aside class="sidebar"><label>BUSCAR UNA TAREA<input type="search" data-search aria-label="Buscar en el manual" placeholder="Código, fotos, cierre…"></label><div class="learning"><span class="ring" data-ring role="img" aria-label="Avance del manual"><span>0%</span></span><p><strong data-learning></strong><br>Tu avance se guarda en este navegador.</p></div><nav class="chapter-nav" aria-label="Temas del manual">{nav}</nav><p class="empty" data-empty hidden>No hay temas con esa búsqueda.</p><div class="role-links"><a href="operario.html">Operario</a><a href="supervisor.html">Supervisor</a><a href="tecnico.html">Informe TI</a></div><p class="muted" style="font-size:11px">Archivo autónomo. Las prácticas usan datos ficticios y no se conectan a la aplicación.</p></aside>
<div class="content"><section class="intro"><span class="eyebrow">ITSANET · {escape(datos['rol'])}</span><h1>{escape(datos['titulo'])}</h1><p>{escape(datos['subtitulo'])}</p><div class="badges"><span class="badge">Sin conexión</span><span class="badge">Ejemplos interactivos</span><span class="badge">Descarga e impresión</span></div></section>{capitulos}<footer class="chapter-footer"><button data-prev>← Anterior</button><label><input type="checkbox" data-read>Ya revisé este tema</label><small data-page></small><button class="primary" data-next>Siguiente →</button></footer><p class="bottom-note">ITSANET · Guía 43 · Los registros operativos se realizan en la app, con la cuenta y el entorno correctos.</p></div></main>
<script>{js}</script></body></html>'''
        (SALIDA/(ident+'.html')).write_text(texto,encoding='utf-8')
    salida_zip=RAIZ/'docs/descargas/ITSANET-manuales-v43.zip'
    salida_zip.parent.mkdir(parents=True,exist_ok=True)
    archivos={ident+'.html':(SALIDA/(ident+'.html')).read_bytes() for ident in manuales}
    archivos['LEEME.txt']=('ITSANET - Manuales interactivos v43\nExtrae este ZIP y abre operario.html, supervisor.html o tecnico.html con Chrome, Edge o Firefox.\nNo necesitas instalar programas ni tener Internet. Cada HTML incluye todo su código.\nLas prácticas no escriben en la app. El informe TI distingue lo implementado de lo pendiente.\nPulsa Descargar HTML para guardar otra copia; Imprimir / PDF permite exportar todos los temas.\n').encode('utf-8')
    with zipfile.ZipFile(salida_zip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for nombre,contenido in sorted(archivos.items()):
            info=zipfile.ZipInfo(nombre,date_time=(2026,10,18,12,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,contenido)
    (salida_zip.with_suffix('.sha256')).write_text(hashlib.sha256(salida_zip.read_bytes()).hexdigest()+'  '+salida_zip.name+'\n')
    return salida_zip


if __name__=='__main__':
    print(generar().relative_to(RAIZ))
