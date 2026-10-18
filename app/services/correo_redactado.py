"""Un mismo correo revisable para el envío firmado y para la copia manual.

Solo se editan textos; las tablas y sus enlaces se calculan con datos reales.
No hace llamadas a Google ni almacena imágenes dentro del borrador.
"""
import hashlib
import json
from html import escape

from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppArchivo, AppConfig, AppCopiaDrive, AppEntrega, AppInforme, utcnow
from app.services import app_modelo as m, ajustes, entregas, integraciones
from app.services.instantaneas import expandir

CAMPOS = {'asunto': 250, 'destinatarios': 1500, 'saludo': 500,
          'introduccion': 5000, 'notas': 8000, 'despedida': 1000, 'firma': 1000}


def clave_config(codigo,manual=False):
    # AppConfig.clave admite 40 caracteres; las recepciones pueden tener 60.
    return ('correo:m:' if manual else 'correo:b:')+hashlib.sha256(m.limpiar(codigo).upper().encode()).hexdigest()[:30]


def _fuente(db, codigo, entrega_id=''):
    r = m.obtener(db, codigo)
    codigo=r.codigo
    if entrega_id:
        e = db.get(AppEntrega, entrega_id)
        if not e or e.recepcion != codigo:
            raise HTTPException(404, 'El envío no pertenece a esta recepción.')
        d = expandir(e.datos)
        skus, eventos = d.get('skus', []), d.get('eventos', [])
        ids = d.get('informes', [])
    else:
        e = None
        skus = m.leer_coleccion(db, codigo, 'skus', actual=True)
        eventos = m.leer_coleccion(db, codigo, 'eventos', actual=True)
        ultimo = db.scalar(select(AppInforme).where(AppInforme.recepcion == codigo)
            .order_by(AppInforme.numero.desc()).limit(1))
        ids = [a['id'] for a in (ultimo.datos.get('archivos', []) if ultimo else [])]
    # EXPORT, CIERRE y auditoría no cambian las cantidades revisadas.
    eventos = [ev for ev in eventos if ev.get('tipo') not in ('EXPORT', 'CIERRE', 'AUDITORIA')]
    archivos = [db.get(AppArchivo, ident) for ident in ids]
    archivos = [a for a in archivos if a and a.recepcion == codigo]
    from app.services.drive import manifiesto
    unicas = {}
    for foto in manifiesto(db, codigo):
        ident=foto['archivoId']
        if ident in unicas:continue
        copia=db.get(AppCopiaDrive,ident)
        unicas[ident]={**foto,'carpetaRecepcion':(copia.datos or {}).get('carpetaRecepcionUrl','') if copia else ''}
    fotos=sorted(unicas.values(),key=lambda foto:(db.get(AppArchivo,foto['archivoId']).creado_en,foto['archivoId']))
    fuente = {'cliente': r.cliente, 'descripcion': r.descripcion, 'skus': skus,
              'eventos': eventos, 'fotos': fotos, 'entrega': entrega_id}
    return r, e, fuente, archivos


def _hash(valor):
    return hashlib.sha256(json.dumps(valor, sort_keys=True, default=str).encode()).hexdigest()


def _link(url, texto):
    import re
    return ('<a href="' + escape(url, quote=True) + '">' + escape(texto) + '</a>') if re.match(
        r'^https://(?:drive|docs)\.google\.com/', str(url or '')) else ''


def _parrafo(texto):
    return '<p>' + escape(str(texto or '')).replace('\n', '<br>') + '</p>' if texto else ''


def renderizar(codigo, fuente, campos, archivos, remitente):
    resumen = entregas.resumen_final(fuente['skus'], fuente['eventos'])
    def tabla(titulo, filas, novedad=False):
        if not filas:
            return ''
        cab = ['Referencia', 'Descripción', 'Declarado', 'Contado', 'Diferencia', 'Pallets']
        if novedad:
            cab += ['Unidades afectadas', 'Novedad']
        cab += ['Observaciones']
        cuerpo = ''
        for s in filas:
            valores = [s['sku'], s['descripcion'], s['esperado'], s['fisico'],
                       s['diferencia'], str(s['pallets']).replace('~', '.')]
            if novedad:
                inc = s.get('incidencias', [])
                valores += [sum(float(i.get('cantidad') or 0) for i in inc),
                            ' · '.join(dict.fromkeys(i.get('nombre') or i.get('tipo', '') for i in inc)) or 'PNC por revisar']
            valores += [s['observacion']]
            cuerpo += '<tr>' + ''.join('<td style="padding:7px;border:1px solid #d9e1ed">' + escape(str(int(v)) if type(v) in (int,float) and float(v).is_integer() else str(v)) + '</td>' for v in valores) + '</tr>'
        return ('<h3>' + titulo + '</h3><table style="border-collapse:collapse;width:100%;font-size:12px">'
                '<thead><tr>' + ''.join('<th style="padding:7px;background:#edf3ff;border:1px solid #d9e1ed">' + c + '</th>' for c in cab)
                + '</tr></thead><tbody>' + cuerpo + '</tbody></table>')
    fotos = fuente['fotos']
    carpetas = list(dict.fromkeys(f.get('carpetaRecepcion') or f.get('carpeta', '') for f in fotos))
    links = ''.join('<p>' + _link(u, 'Abrir carpeta de evidencias') + '</p>' for u in carpetas if u)
    fotos_html = ''
    for i, f in enumerate(fotos[:12], 1):
        url = f.get('enlace') or f.get('driveUrl') or ('https://drive.google.com/file/d/' + f['fileId'] + '/view' if f.get('fileId') else '')
        nombre = f.get('nombre') or f.get('sku') or 'Fotografía'
        miniatura=''
        if f.get('fileId'):
            miniatura='<img data-archivo="'+escape(f['archivoId'],quote=True)+'" src="https://drive.google.com/thumbnail?id='+escape(f['fileId'],quote=True)+'&amp;sz=w320" alt="'+escape(nombre,quote=True)+'" style="display:block;width:150px;height:120px;object-fit:contain;border:1px solid #ddd">'
        fotos_html += '<li style="display:inline-block;vertical-align:top;width:170px;max-width:100%;margin:4px;overflow-wrap:anywhere;word-break:break-word">' + miniatura + '<div style="max-width:170px;overflow-wrap:anywhere;word-break:break-all;font-size:11px;line-height:1.5">' + str(i) + '. ' + (_link(url, nombre) or escape(nombre + ' · copia a Drive pendiente')) + '</div></li>'
    html = '<div style="font-family:Arial,sans-serif;font-size:14px;color:#172033;max-width:1100px">'
    html += _parrafo(campos['saludo']) + _parrafo(campos['introduccion']) + links
    html += '<p><b>Recepción: ' + escape(codigo) + '</b> · Cliente: ' + escape(fuente['cliente']) + '</p>'
    html += '<p>' + str(resumen['unidadesEsperadas']) + ' unidades declaradas · ' + str(resumen['unidadesFisicas']) + ' contadas · ' + str(resumen['unidadesPnc']) + ' PNC.</p>'
    html += tabla('Sobrantes', [s for s in resumen['discrepancias'] if s['diferencia'] > 0])
    html += tabla('Faltantes', [s for s in resumen['discrepancias'] if s['diferencia'] < 0])
    html += tabla('Producto no conforme y otras novedades físicas', resumen['novedades'], True)
    if not resumen['discrepancias'] and not resumen['novedades']:
        html += '<p>Sin diferencias de cantidad ni novedades físicas registradas.</p>'
    if fotos_html:
        html += '<h3>Fotografías registradas · orden de registro</h3><ol style="list-style:none;padding:0">' + fotos_html + '</ol>'
        if len(fotos) > 12:
            html += '<p>' + str(len(fotos) - 12) + ' fotos adicionales disponibles en las carpetas de evidencias.</p>'
    if archivos:
        html += '<h3>Documentos finales</h3><ul>' + ''.join('<li>' + escape(a.nombre) + '</li>' for a in archivos) + '</ul>'
    html += _parrafo(campos['notas']) + _parrafo(campos['despedida']) + _parrafo(campos['firma'])
    html += '<p style="font-size:11px;color:#586477">Preparado por: ' + escape(remitente) + ' · ' + escape(codigo) + '</p></div>'
    from html.parser import HTMLParser
    class Texto(HTMLParser):
        def __init__(self):
            super().__init__(); self.partes = []
        def handle_data(self, data): self.partes.append(data)
        def handle_endtag(self, tag):
            if tag in ('p', 'tr', 'h3', 'li'): self.partes.append('\n')
            elif tag in ('td', 'th'): self.partes.append(' | ')
        def handle_starttag(self, tag, attrs):
            if tag == 'a': self.partes.append(dict(attrs).get('href', '') + ' ')
            if tag == 'br': self.partes.append('\n')
    t = Texto(); t.feed(html)
    return {'asunto': campos['asunto'], 'html': html, 'texto': ''.join(t.partes), 'remitente': remitente,
            'imagenesDrive':[f['fileId'] for f in fotos[:12] if f.get('fileId')]}


def vista(db, codigo, usuario, entrega_id=''):
    r, e, fuente, archivos = _fuente(db, codigo, entrega_id)
    codigo=r.codigo
    f = db.get(AppConfig, clave_config(codigo)); guardado = f.datos if f else {}
    campos = {'asunto': 'Informe de recepción · ' + codigo, 'destinatarios': e.datos.get('destinatarios', '') if e else '',
              'saludo': 'Estimados,', 'introduccion': 'Por medio del presente, remito el informe correspondiente a la recepción ' + codigo + ' del cliente ' + r.cliente + '. Se detallan las novedades registradas durante la validación.',
              'notas': '', 'despedida': 'Quedo atento a cualquier consulta o información adicional.\nSaludos cordiales,', 'firma': usuario}
    campos.update({k: v for k, v in guardado.get('campos', {}).items() if k in CAMPOS})
    # Un envío confirmado conserva el texto que efectivamente se solicitó.
    congelado = expandir(e.datos).get('correoFinal') if e else None
    final = congelado if congelado and e.estado in ('ENTREGADA','PROCESANDO') else renderizar(codigo, fuente, campos, archivos, usuario)
    declarado=bool(e and (e.datos.get('correoManual') or {}).get('estado')=='DECLARADO_ENVIADO')
    if congelado and (e.estado in ('ENTREGADA','PROCESANDO') or declarado):
        campos=congelado.get('campos',campos);final=congelado
    final={'imagenesDrive':[],**final}
    g = integraciones.google(db, usuario)
    version = _hash([fuente, guardado.get('revision', 0),usuario])
    ultima=entregas.recientes(db,1,recepcion=codigo)
    return {'campos': campos, 'version': version, 'revision': guardado.get('revision', 0), **final,
            'entregaDisponible':ultima[0].id if ultima and not entrega_id else '',
            'conexionConfigurada': bool(g['url'] and g['secreto']),
            'soloLectura': bool(e and e.estado in ('ENTREGADA', 'PROCESANDO') or declarado),
            'archivos': [{'id': a.id, 'nombre': a.nombre, 'url': '/api/app/archivos/' + a.id} for a in archivos],
            'fotos': [{'id': f['archivoId'], 'nombre': f.get('nombre', ''), 'url': '/api/app/archivos/' + f['archivoId']} for f in fuente['fotos'][:12]],
            'manual':(db.get(AppConfig,clave_config(codigo,manual=True)).datos if db.get(AppConfig,clave_config(codigo,manual=True)) else None),
            'modificadoPor': guardado.get('usuario'), 'modificadoEn': guardado.get('fecha')}


def guardar(db, codigo, datos, usuario):
    codigo=m.obtener(db, codigo, bloquear=True).codigo
    entrega_id = str(datos.get('entregaId') or '')
    anterior = vista(db, codigo, usuario, entrega_id)
    if anterior['soloLectura']:
        raise HTTPException(409, 'Este correo ya está en proceso o confirmado. Su texto se conserva en el historial.')
    if datos.get('version') != anterior['version']:
        raise HTTPException(409, 'La recepción o el borrador cambió. Actualiza la vista antes de guardar.')
    campos = datos.get('campos')
    if not isinstance(campos, dict) or set(campos) != set(CAMPOS):
        raise HTTPException(422, 'Completa asunto, destinatarios y los textos del correo.')
    for k, limite in CAMPOS.items():
        if not isinstance(campos[k], str) or len(campos[k]) > limite:
            raise HTTPException(422, f'Revisa {k}: máximo {limite} caracteres.')
    campos = {k: v.strip() for k, v in campos.items()}
    if not campos['asunto'] or any(c in campos['asunto'] for c in '\r\n'):
        raise HTTPException(422, 'Escribe el asunto en una sola línea.')
    campos['destinatarios'] = entregas.validar_destinatarios(campos['destinatarios'])
    f = db.get(AppConfig, clave_config(codigo)) or AppConfig(clave=clave_config(codigo))
    f.datos = {'campos': campos, 'revision': anterior['revision'] + 1, 'usuario': usuario, 'fecha': utcnow().isoformat()}
    f.usuario = usuario; db.add(f)
    ajustes.auditar(db, usuario, 'CORREO_BORRADOR_GUARDADO', codigo, {'revision': f.datos['revision']})
    db.commit()
    return vista(db, codigo, usuario, entrega_id)


def congelar(db, codigo, datos, usuario, entrega_id=''):
    if not datos.get('correoVersion'):
        return None  # Compatibilidad con clientes anteriores.
    v = vista(db, codigo, usuario, entrega_id)
    if datos['correoVersion'] != v['version']:
        raise HTTPException(409, 'Cambió la recepción o el correo. Revisa nuevamente el correo final antes de enviar.')
    if entregas.validar_destinatarios(datos.get('destinatarios')) != v['campos']['destinatarios']:
        raise HTTPException(409, 'Los destinatarios cambiaron. Guarda y revisa el correo final antes de enviar.')
    if datos.get('modoEntrega') not in ('MANUAL','MANUAL_ENVIADO'):
        from app.services.drive import resumen_fotos
        if resumen_fotos(db,codigo)['pendientes']:
            raise HTTPException(409,'Confirma las fotos en Drive antes del correo automático o elige envío manual. No se cerró ni se envió la recepción.')
    if len(v['html'])>500000:
        raise HTTPException(422,'El correo supera el tamaño permitido. Reduce los textos o envía las novedades extensas en los documentos finales.')
    return {k: v[k] for k in ('asunto', 'html', 'texto', 'remitente','campos','imagenesDrive')}


def manual(db,codigo,datos,usuario):
    """El operador declara el envío externo; nunca se inventa un acuse Google."""
    r=m.obtener(db,codigo,bloquear=True)
    codigo=r.codigo
    grupo=list(db.scalars(select(AppEntrega).where(AppEntrega.recepcion==codigo).with_for_update()
                          .execution_options(populate_existing=True)))
    if any(e.estado=='PROCESANDO' or e.estado=='REVISION' and e.datos.get('revisionMotivo') not in
           ('ENTREGAS_MULTIPLES','CONEXION_RECHAZADA','FOTOS_RECUPERADAS') for e in grupo):
        raise HTTPException(409,'Hay un envío en proceso o con confirmación interrumpida. Revisa Enviados antes de preparar una copia manual para evitar duplicados.')
    ident=str(datos.get('entregaId') or '')
    if grupo and (not ident or ident!=max(grupo,key=lambda e:(e.creado_en,e.id)).id):
        raise HTTPException(409,'Abre el correo de la entrega más reciente desde Entregas antes de preparar el envío manual.')
    e=next((e for e in grupo if e.id==ident),None)
    if e and e.estado=='ENTREGADA':raise HTTPException(409,'Google ya confirmó este correo. Revisa Enviados antes de volver a compartirlo.')
    if e:
        from app.services.recuperar_entrega import _validar
        _validar(db,e,grupo)
    v=vista(db,codigo,usuario,ident)
    if datos.get('correoVersion')!=v['version']:raise HTTPException(409,'Actualiza el correo antes de preparar el envío manual.')
    if not v['campos']['destinatarios']:raise HTTPException(422,'Completa los destinatarios antes de preparar el envío manual.')
    if not v['archivos']:raise HTTPException(409,'Genera los documentos finales desde Informes antes de preparar el envío manual.')
    accion=datos.get('accion')
    f=db.get(AppConfig,clave_config(codigo,manual=True))
    if accion not in ('PREPARAR','CONFIRMAR') or datos.get('confirmar') is not True:
        raise HTTPException(422,'Confirma la preparación o el envío manual.')
    if accion=='CONFIRMAR' and (not f or f.datos.get('version')!=v['version'] or f.datos.get('estado')!='PREPARADO'):
        raise HTTPException(409,'Prepara primero el correo manual actualizado y luego confirma que lo enviaste.')
    registro={'estado':'DECLARADO_ENVIADO' if accion=='CONFIRMAR' else 'PREPARADO','usuario':usuario,
              'fecha':utcnow().isoformat(),'version':v['version'],'destinatarios':v['campos']['destinatarios'],
              'asunto':v['asunto'],'entregaId':ident,'correoSha256':_hash(v['html'])}
    for anterior in grupo:
        if anterior.estado in ('PENDIENTE','REVISION'):
            anterior.estado='CANCELADA'
            anterior.datos={**anterior.datos,'anulacion':{'usuario':usuario,'fecha':registro['fecha'],'motivo':'Preparado para envío manual; automático detenido.'}}
    if e:
        e.datos={**e.datos,'correoManual':registro,'correoFinal':{k:v[k] for k in ('asunto','html','texto','remitente','campos','imagenesDrive')}}
        if e.datos.get('informeId'):
            informe=db.get(AppInforme,e.datos['informeId'])
            if informe:informe.estado='MANUAL_DECLARADO' if accion=='CONFIRMAR' else 'MANUAL_PREPARADO'
    f=f or AppConfig(clave=clave_config(codigo,manual=True));f.datos=registro;f.usuario=usuario;db.add(f)
    ajustes.auditar(db,usuario,'CORREO_MANUAL_'+accion,codigo,registro)
    db.commit()
    return {'mensaje':'Envío manual declarado por el supervisor; no es una confirmación de Google.' if accion=='CONFIRMAR' else 'Envíos automáticos detenidos. Copia el correo y adjunta los documentos finales.', 'manual':registro}
