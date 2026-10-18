"""Informe técnico y paquete de captura; no modifica la versión de la app."""
import base64
from html import escape as e
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'docs/auditoria'
OUT=ROOT/'docs/descargas'
NOMBRE='ITSANET-informe-servidor-20261018'

def bloque(b):
    t=b['tipo']
    if t=='p':return '<p>'+e(b['texto'])+'</p>'
    if t=='lista':return '<ul>'+''.join('<li>'+e(i)+'</li>' for i in b['items'])+'</ul>'
    if t=='codigo':return '<pre><code>'+e(b['texto'])+'</code></pre>'
    if t=='tabla':return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+e(c)+'</th>' for c in b['columnas'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(c)+'</td>' for c in f)+'</tr>' for f in b['filas'])+'</tbody></table></div>'
    raise ValueError('Bloque desconocido')

def generar():
    data=json.loads((SRC/'informe-servidor-20261018.json').read_text())
    css=(SRC/'informe.css').read_text();js=(SRC/'informe.js').read_text()
    logo=base64.b64encode((ROOT/'firebase/public/logo-itsa.png').read_bytes()).decode()
    nav=''.join('<a href="#'+s['id']+'" data-nav="'+s['id']+'">'+e(s['titulo'])+'</a>' for s in data['secciones'])
    categorias=sorted({s['evidencia'] for s in data['secciones']})
    options=''.join('<option>'+e(c)+'</option>' for c in categorias)
    content=''.join('<details class="report-section" id="'+s['id']+'" data-evidence="'+e(s['evidencia'])+'"'+(' open' if i==0 else '')+'><summary>'+e(s['titulo'])+'</summary><div class="report-body"><span class="badge'+(' pending' if 'Pendiente' in s['evidencia'] else '')+'">'+e(s['evidencia'])+'</span>'+''.join(bloque(b) for b in s['bloques'])+'</div></details>' for i,s in enumerate(data['secciones']))
    html=f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(data['titulo'])}</title><style>{css}</style></head><body>
<header><div class="actions"><img alt="ITSA" src="data:image/png;base64,{logo}"><div><strong>Informe técnico · ITSANET</strong><small>{e(data['fecha'])}</small></div></div><div class="actions"><button data-download>Descargar HTML</button><button data-print>Imprimir / PDF</button></div></header>
<main class="shell"><aside class="side"><label>BUSCAR EN EL INFORME<input data-search type="search" placeholder="Cámara, base, credenciales…"></label><label>TIPO DE EVIDENCIA<select data-evidence><option value="">Todas</option>{options}</select></label><p data-count class="muted" aria-live="polite"></p><nav aria-label="Secciones del informe">{nav}</nav><hr><small>HTML autónomo con captura empresarial aportada por el usuario. No se conecta a la app ni a Google.</small></aside><div>
<section class="hero"><span class="eyebrow">Documento de revisión para TI</span><h1>{e(data['titulo'])}</h1><p>{e(data['version'])}</p><p class="note"><strong>Producción 46 activa, con margen de disco y RAM.</strong> La captura del usuario confirma servicio y salud correctos, 53G disponibles (25 % de uso), 9,8 GiB de RAM disponible y swap sin uso. La medición de las 17:38 de Ecuador confirma MySQL 13.14 MiB, archivos locales 5,59 MiB y una entrega REVISION. Falta comparar crecimiento; los 17G del filesystem no se atribuyen a ITSANET.</p><p>Acceso empresarial: <a href="https://apps.flexnetuio.com:8443/app/">https://apps.flexnetuio.com:8443/app/</a></p><div class="flow"><div><strong>Navegador y cámara</strong>Origen HTTPS confiable + permiso del dispositivo</div><div><strong>Apache :8443 → FastAPI :3002</strong>Misma aplicación y API bajo el acceso empresarial</div><div><strong>MySQL + disco → Drive</strong>Metadatos y operaciones; evidencia externa y copia confirmada</div></div><div class="actions controls"><button data-expand>Expandir secciones</button><button data-clear>Limpiar filtros</button></div></section><p data-empty class="empty" hidden>No hay secciones con ese filtro.</p>{content}
<section class="card" id="capacidad"><span class="eyebrow">Simulación de capacidad · no son datos reales</span><h2>Buffer de fotos pendientes en disco</h2><div class="grid" data-plan-form><label>Recepciones por día<input type="number" min="0" max="10000000" value="10" data-plan></label><label>Fotos por recepción<input type="number" min="0" max="10000000" value="50" data-plan></label><label>Peso medio tras procesar (KiB)<input type="number" min="0" max="10000000" value="250" data-plan></label><label>Días de indisponibilidad Drive<input type="number" min="0" max="10000000" value="3" data-plan></label></div><p data-plan-result aria-live="polite"></p><p class="muted">Son supuestos editables. El peso real depende de la imagen y puede conservarse el original. Se excluyen SQL, informes, logs, miniaturas y respaldos.</p></section>
<section class="card" id="medicion"><span class="eyebrow">Captura local · sin subir archivos</span><h2>Completar el informe con métricas del servidor</h2><p>Ejecuta el paquete de lectura en @apps y elige su JSON. Puedes añadir una captura anterior de la misma base para comparar. Este HTML procesa el archivo únicamente en tu navegador.</p><div class="grid"><label class="file-label">Captura actual<input data-current type="file" accept=".json,application/json"></label><label class="file-label">Captura anterior, opcional<input data-previous type="file" accept=".json,application/json"></label></div><p data-import-state class="status" role="status"></p><p class="muted">Hora de la captura: <span data-live-date>Sin captura</span><br>Commit: <span data-live-commit>Sin confirmar</span></p><div class="metrics"><div class="metric"><b data-live-health>Sin confirmar</b><small>Salud local del servicio</small></div><div class="metric"><b data-live-db>Sin confirmar</b><small>Asignación MySQL datos + índices</small></div><div class="metric"><b data-live-free>Sin confirmar</b><small>Espacio libre del filesystem de datos</small></div></div><p>TLS: <span data-live-tls>Sin confirmar</span></p><pre data-live-service>Servicio sin captura</pre><div class="table-wrap" data-live-tables>Tablas pendientes de medición.</div><p data-compare-result class="note" role="status"></p><p class="muted">Una captura es puntual. No acredita carga máxima, consistencia de un respaldo ni disponibilidad futura. Los reportes privados no contienen contraseñas o claves.</p></section>
<footer>ITSANET · Revisión documental y captura puntual. Conserva la versión 48 y el enlace: el paquete no actualiza ni reinicia la app.</footer></div></main><script type="application/json" id="captura-inicial">{json.dumps(data.get("capturaMedicion"),ensure_ascii=True).replace("<",chr(92)+"u003c")}</script><script>{js}</script></body></html>'''
    md=['# '+data['titulo'],'',data['fecha'],'',data['version'],'']
    for s in data['secciones']:
        md+=['## '+s['titulo'],'','Evidencia: '+s['evidencia'],'']
        for b in s['bloques']:
            if b['tipo']=='p':md += [b['texto'],'']
            elif b['tipo']=='lista':md += ['- '+x for x in b['items']]+['']
            elif b['tipo']=='codigo':md += ['```bash',b['texto'],'```','']
            elif b['tipo']=='tabla':md += ['| '+' | '.join(b['columnas'])+' |','|'+'---|'*len(b['columnas'])]+['| '+' | '.join(c.replace('|','\\|') for c in row)+' |' for row in b['filas']]+['']
    OUT.mkdir(exist_ok=True)
    (OUT/(NOMBRE+'.html')).write_text(html,encoding='utf-8');(OUT/(NOMBRE+'.md')).write_text('\n'.join(md),encoding='utf-8')
    files={'informe-tecnico.html':html.encode(),'informe-tecnico.md':'\n'.join(md).encode()}
    for f in ['auditar_servidor_lectura.py','estado_produccion.py','revisar_servidor_lectura.sh']:files[f]=(ROOT/'scripts'/f).read_bytes()
    files['LEEME.txt']=('ITSANET - Informe técnico 18/10/2026\nExtrae TODO el ZIP. Abre informe-tecnico.html en Chrome/Edge/Firefox: no requiere Internet.\nPuedes buscar, expandir, imprimir y cargar las capturas JSON de forma local.\nIncluye la captura real aportada por el usuario el 18/10/2026 a las 17:38:45 de Ecuador.\nLas nuevas capturas son opcionales para completar TLS, recursos y tendencia de crecimiento.\nEn Linux @apps, desde esta carpeta, ejecutar: bash revisar_servidor_lectura.sh "$HOME/bryan/IV_ITSANET"\nRequiere sudo, systemd y la .venv ya instalada; usa EnvironmentFile privado sin mostrar valores.\nNo hace pull, no reinicia servicios, no abre túneles, no copia fotos ni envía correos.\nMySQL se consulta con transacción de solo lectura y consultas limitadas. Solo crea informes privados fuera del código.\nNo ejecutar los scripts de captura en Windows. Conserva la versión 48 y el enlace público actual.\n').encode()
    zpath=OUT/(NOMBRE+'.zip')
    with zipfile.ZipFile(zpath,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,body in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,10,18,12,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,body)
    zpath.with_suffix('.sha256').write_text(hashlib.sha256(zpath.read_bytes()).hexdigest()+'  '+zpath.name+'\n')
    return zpath
if __name__=='__main__':print(generar().relative_to(ROOT))
