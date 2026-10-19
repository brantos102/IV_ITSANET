"""Un mismo correo revisable para el envío firmado y para la copia manual.

Se editan textos, presentación y selección de fotos guardadas; las tablas se calculan con datos reales.
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


def clave_config(codigo,manual=False,origen=''):
    # AppConfig.clave admite 40 caracteres; las recepciones pueden tener 60.
    dato=m.limpiar(codigo).upper()+('\x1f'+origen if origen else '')
    return ('correo:m:' if manual else 'correo:b:')+hashlib.sha256(dato.encode()).hexdigest()[:30]


def _fuente(db, codigo, entrega_id='',origen=''):
    r = m.obtener(db, codigo)
    codigo=r.codigo
    if entrega_id:
        e = db.get(AppEntrega, entrega_id)
        if not e or e.recepcion != codigo:
            raise HTTPException(404, 'El envío no pertenece a esta recepción.')
        d = expandir(e.datos)
        skus, eventos = d.get('skus', []), d.get('eventos', [])
        hijo=next((c for c in d.get('correosPorOrigen',[]) if c['origen']==origen),None)
        ids = hijo['informes'] if hijo else d.get('informes', [])
    else:
        e = None
        skus = m.leer_coleccion(db, codigo, 'skus', actual=True)
        eventos = m.leer_coleccion(db, codigo, 'eventos', actual=True)
        ultimo = db.scalar(select(AppInforme).where(AppInforme.recepcion == codigo)
            .order_by(AppInforme.numero.desc()).limit(1))
        ids = [a['id'] for a in (ultimo.datos.get('archivos', []) if ultimo else []) if not origen or a.get('origen')==origen]
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
    if e:
        fuente['validacionDepot']=((hijo or {}).get('correoFinal') or d.get('correoFinal') or {}).get('validacionDepot')
    if not e or (fuente['validacionDepot'] is None and e.estado not in ('ENTREGADA','PROCESANDO')
            and (d.get('correoManual') or {}).get('estado')!='DECLARADO_ENVIADO'):
        from app.services.validacion_depot import validar
        fuente['validacionDepot']=validar(db,r.cliente,[s['sku'] for s in skus])
    if origen:
        if origen not in (r.origenes or []):raise HTTPException(422,'El packing list no pertenece a esta recepción.')
        from app.services.correos_embarque import filtrar,asignaciones
        fuente=filtrar(fuente,d.get('lineas',[]) if e else m.leer_coleccion(db,codigo,'lineas',actual=True),origen,
            d.get('asignacionesAdicionales',{}) if e else asignaciones(db,codigo))
    return r, e, fuente, archivos


def _hash(valor):
    return hashlib.sha256(json.dumps(valor, sort_keys=True, default=str).encode()).hexdigest()


def _link(url, texto):
    import re
    return ('<a href="' + escape(url, quote=True) + '">' + escape(texto) + '</a>') if re.match(
        r'^https://(?:drive|docs)\.google\.com/', str(url or '')) else ''


def _parrafo(texto):
    return '<p>' + escape(str(texto or '')).replace('\n', '<br>') + '</p>' if texto else ''


MAX_FOTOS = 12
PRESENTACION = {'mostrarTotales': False, 'fotosModo': 'NOVEDADES', 'fotosIds': []}


def _novedad_foto(foto, resumen, categoria=None):
    grupos = foto.get('rutasVinculadas') or [foto]
    actuales = {s['sku']: s for s in resumen['discrepancias'] + resumen['novedades']}
    for v in grupos:
        s = actuales.get(v.get('sku'))
        c = v.get('categoria')
        if not s or categoria and c != categoria:
            continue
        if c == 'PNC' and any(n['sku'] == s['sku'] for n in resumen['novedades']):
            return True
        if c == 'FALTANTE' and s['diferencia'] < 0 or c == 'SOBRANTE' and s['diferencia'] > 0:
            return True
    return False


def fotos_correo(fuente, presentacion):
    fotos = fuente['fotos']
    modo = presentacion['fotosModo']
    if modo == 'NINGUNA': return []
    if modo == 'ELEGIDAS':
        por_id = {f['archivoId']: f for f in fotos}
        return [por_id[i] for i in presentacion['fotosIds'] if i in por_id][:MAX_FOTOS]
    if modo == 'NOVEDADES':
        resumen = entregas.resumen_final(fuente['skus'], fuente['eventos'])
        fotos = [f for f in fotos if _novedad_foto(f, resumen)]
    return fotos[:MAX_FOTOS]


def validar_presentacion(valor, disponibles):
    if not isinstance(valor, dict) or set(valor) != set(PRESENTACION):
        raise HTTPException(422, 'Revisa las opciones de presentación del correo.')
    if type(valor['mostrarTotales']) is not bool or valor['fotosModo'] not in ('NOVEDADES', 'TODAS', 'NINGUNA', 'ELEGIDAS'):
        raise HTTPException(422, 'Selecciona totales y fotografías válidos.')
    ids = valor['fotosIds']
    if not isinstance(ids, list) or len(ids) > MAX_FOTOS or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        raise HTTPException(422, 'Selecciona hasta 12 fotografías diferentes para el correo.')
    if not set(ids) <= set(disponibles):
        raise HTTPException(409, 'Una foto seleccionada ya no pertenece a las evidencias disponibles. Actualiza el correo.')
    return {'mostrarTotales': valor['mostrarTotales'], 'fotosModo': valor['fotosModo'], 'fotosIds': list(ids)}


def renderizar(codigo, fuente, campos, archivos, remitente, presentacion=None):
    opciones = {**PRESENTACION, **(presentacion or {})}
    resumen = entregas.resumen_final(fuente['skus'], fuente['eventos'])
    fotos = fotos_correo(fuente, opciones)
    usadas = set()
    def numero(v):
        return str(int(v)) if type(v) in (int, float) and float(v).is_integer() else str(v)
    def fotos_html(filas, categoria=None):
        html = ''
        for f in filas:
            usadas.add(f['archivoId'])
            url = f.get('enlace') or f.get('driveUrl') or ('https://drive.google.com/file/d/' + f['fileId'] + '/view' if f.get('fileId') else '')
            vinculos=f.get('rutasVinculadas') or [f]
            codigos=list(dict.fromkeys(v['sku'] for v in vinculos if v.get('sku') and (not categoria or _novedad_foto(v,resumen,categoria))))
            caption=' · '.join(codigos) or 'Evidencia de recepción'
            img = ''
            if f.get('fileId'):
                img = '<img data-archivo="' + escape(f['archivoId'], quote=True) + '" src="https://drive.google.com/thumbnail?id=' + escape(f['fileId'], quote=True) + '&amp;sz=w320" alt="' + escape(caption, quote=True) + '" width="176" height="132" style="display:block;width:176px;height:132px;object-fit:contain;background:#f3f6fa;border:0;border-radius:8px">'
            else:
                img = '<span style="display:block;padding:16px;color:#64748b">Copia a Drive pendiente</span>'
            html += '<div style="display:inline-block;vertical-align:top;width:184px;max-width:100%;margin:8px 8px 0 0"><div style="border:1px solid #dce5ef;border-radius:9px;padding:4px">' + img + '<p style="margin:6px 2px;font-size:12px;overflow-wrap:anywhere">' + (_link(url, caption) or escape(caption)) + '</p></div></div>'
        return '<div style="margin-top:10px">' + html + '</div>' if html else ''
    def tabla(titulo, filas, categoria, color, novedad=False):
        if not filas: return ''
        cab = ['Referencia', 'Descripción', 'Declarado', 'Contado', 'Diferencia', 'Pallets']
        if novedad: cab += ['Uds. afectadas', 'Novedad']
        cab += ['Observaciones']
        cuerpo = ''
        for n, s in enumerate(filas):
            valores = [s['sku'], s['descripcion'], s['esperado'], s['fisico'], s['diferencia'], str(s['pallets']).replace('~', '.')]
            if novedad:
                inc = s.get('incidencias', [])
                valores += [sum(float(i.get('cantidad') or 0) for i in inc), ' · '.join(dict.fromkeys(i.get('nombre') or i.get('tipo', '') for i in inc)) or 'PNC por revisar']
            valores += [s['observacion']]
            cuerpo += '<tr style="background:' + ('#ffffff' if n % 2 else '#f7f9fc') + '">' + ''.join('<td style="padding:9px 7px;border-bottom:1px solid #e3e9f1;vertical-align:top;overflow-wrap:anywhere;' + ('font-weight:700;color:#174c91;' if i == 0 else '') + '">' + escape(numero(v)) + '</td>' for i, v in enumerate(valores)) + '</tr>'
        contenido = ('<div style="overflow-x:auto"><table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:12px;line-height:1.45;text-align:left">'
            '<thead><tr>' + ''.join('<th style="padding:9px 7px;background:#eaf0f8;color:#33465f;border-bottom:1px solid #d1ddeb;font-size:11px">' + c + '</th>' for c in cab) + '</tr></thead><tbody>' + cuerpo + '</tbody></table></div>')
        imagenes = [f for f in fotos if f['archivoId'] not in usadas and _novedad_foto(f, resumen, categoria)]
        return '<section style="margin:22px 0"><h3 style="margin:0 0 10px;padding:10px 12px;border-left:4px solid ' + color + ';background:#f2f5fa;font-size:16px;color:#1e3655">' + titulo + '</h3>' + contenido + fotos_html(imagenes, categoria) + '</section>'
    carpetas = list(dict.fromkeys(f.get('carpetaRecepcion') or f.get('carpeta', '') for f in fuente['fotos']))
    links = ''.join('<p style="margin:8px 0">' + _link(u, 'Consultar carpeta de evidencias →') + '</p>' for u in carpetas if u)
    html = '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#22334a;max-width:960px;margin:0 auto;background:#ffffff">'
    html += '<div style="background:#16345c;color:#ffffff;border-radius:12px 12px 0 0;padding:22px 24px"><p style="font-size:11px;letter-spacing:1.5px;margin:0;color:#c9def8">ITSANET · INFORME DE RECEPCIÓN</p><h2 style="font-size:23px;line-height:1.35;margin:8px 0;color:#ffffff;overflow-wrap:anywhere">' + escape(codigo) + '</h2><p style="margin:0;color:#e2ecf9">Cliente: <b>' + escape(fuente['cliente']) + '</b></p></div>'
    if fuente.get('origen'):html += '<p style="padding:10px 18px;background:#eef4fb;margin:0"><b>Packing list / embarque: '+escape(fuente['origen'])+'</b></p>'
    html += '<div style="padding:20px 18px;border:1px solid #dce5ef;border-top:0;border-radius:0 0 12px 12px">' + _parrafo(campos['saludo']) + _parrafo(campos['introduccion']) + links
    if opciones['mostrarTotales']:
        html += '<p style="padding:12px;background:#eef4fb;border-radius:8px"><b>Resumen de unidades</b><br>' + numero(resumen['unidadesEsperadas']) + ' declaradas · ' + numero(resumen['unidadesFisicas']) + ' contadas · ' + numero(resumen['unidadesPnc']) + ' PNC</p>'
    html += tabla('Sobrantes', [s for s in resumen['discrepancias'] if s['diferencia'] > 0], 'SOBRANTE', '#1577a7')
    html += tabla('Faltantes', [s for s in resumen['discrepancias'] if s['diferencia'] < 0], 'FALTANTE', '#d79315')
    html += tabla('Producto no conforme (PNC) y novedades físicas', resumen['novedades'], 'PNC', '#cf5252', True)
    if not resumen['discrepancias'] and not resumen['novedades']:
        html += '<p style="padding:14px;background:#eff9f4;border-left:4px solid #20a277">Sin diferencias de cantidad ni novedades físicas registradas.</p>'
    depot=fuente.get('validacionDepot')
    if depot:
        html += '<section style="margin:22px 0;padding:14px;border:1px solid #dce5ef;border-radius:8px"><h3 style="margin:0 0 8px;color:#1e3655;font-size:16px">Observaciones de validación en Depot</h3>'
        html += _parrafo(depot['notaMaestro'])+_parrafo(depot['metodo'])
        if depot.get('actualizadoEn'):html += _parrafo('Actualización del catálogo: '+(depot.get('fechaActualizacion') or depot['actualizadoEn']))
        pendientes=[s for s in fuente['skus'] if depot['porSku'].get(s['sku'],{}).get('estado','OK')!='OK']
        if pendientes:
            html += '<p><b>Verificar los siguientes productos antes de cargar sus cantidades en Depot:</b></p><ul>'
            for s in pendientes:
                d=depot['porSku'][s['sku']]
                html += '<li style="margin-bottom:10px"><b>'+escape(s['sku'])+'</b>'+(' · '+escape(s['descripcion']) if s.get('descripcion') else '')+'<br>'+escape(d['observacion'])+'</li>'
            html += '</ul>'
            if any(depot['porSku'][s['sku']]['estado']=='NO_ENCONTRADO' for s in pendientes):html += _parrafo('La ausencia en la consulta de stock no confirma inexistencia en el maestro de Depot. La creación debe solicitarse después de verificar el registro.')
        else:html += _parrafo('Los productos de esta recepción figuran en el catálogo consultado para el cliente.')
        html += '</section>'
    otras = [f for f in fotos if f['archivoId'] not in usadas]
    if otras: html += '<h3 style="font-size:16px;margin-top:24px">Evidencias seleccionadas</h3>' + fotos_html(otras)
    if archivos:
        html += '<div style="padding:14px 16px;background:#f3f6fa;border-radius:8px;margin-top:22px"><h3 style="font-size:15px;margin:0 0 8px">Documentos finales</h3><ul style="margin:0;padding-left:20px">' + ''.join('<li style="overflow-wrap:anywhere">' + escape(a.nombre) + '</li>' for a in archivos) + '</ul></div>'
    html += _parrafo(campos['notas']) + _parrafo(campos['despedida']) + _parrafo(campos['firma'])
    html += '<p style="font-size:11px;color:#63758d;border-top:1px solid #e0e7f0;padding-top:12px;margin-top:24px">Preparado por: ' + escape(remitente) + ' · ' + escape(codigo) + '</p></div></div>'
    from html.parser import HTMLParser
    class Texto(HTMLParser):
        def __init__(self): super().__init__(); self.partes = []
        def handle_data(self, data): self.partes.append(data)
        def handle_endtag(self, tag):
            if tag in ('p', 'tr', 'h2', 'h3', 'li'): self.partes.append('\n')
            elif tag in ('td', 'th'): self.partes.append(' | ')
        def handle_starttag(self, tag, attrs):
            if tag == 'a': self.partes.append(dict(attrs).get('href', '') + ' ')
            if tag == 'br': self.partes.append('\n')
    t = Texto(); t.feed(html)
    return {'asunto': campos['asunto'], 'html': html, 'texto': ''.join(t.partes), 'remitente': remitente,
            'imagenesDrive': list(dict.fromkeys(f['fileId'] for f in fotos if f.get('fileId'))),
            'presentacion': opciones, 'fotosSeleccionadas': [f['archivoId'] for f in fotos], 'validacionDepot':depot}


def vista(db, codigo, usuario, entrega_id='',origen=''):
    r, e, fuente, archivos = _fuente(db, codigo, entrega_id,origen)
    codigo=r.codigo
    hijo=next((c for c in e.datos.get('correosPorOrigen',[]) if c['origen']==origen),None) if e else None
    f = db.get(AppConfig, clave_config(codigo,origen=origen)); guardado = f.datos if f else {}
    campos = {'asunto': 'Informe de recepción · ' + codigo, 'destinatarios': e.datos.get('destinatarios', '') if e else '',
              'saludo': 'Estimados,', 'introduccion': 'Por medio del presente, remito el informe correspondiente a la recepción ' + codigo + ' del cliente ' + r.cliente + '. Se detallan las novedades registradas durante la validación.',
              'notas': '', 'despedida': 'Quedo atento a cualquier consulta o información adicional.\nSaludos cordiales,', 'firma': usuario}
    campos.update({k: v for k, v in guardado.get('campos', {}).items() if k in CAMPOS})
    if origen:
        if 'asunto' not in guardado.get('campos',{}):campos['asunto']+=' · '+origen
        if 'introduccion' not in guardado.get('campos',{}):campos['introduccion']='Remito el informe del packing list / embarque '+origen+' de la recepción '+codigo+' del cliente '+r.cliente+'. Se detallan exclusivamente los resultados de este embarque.'
        if hijo and 'destinatarios' not in guardado.get('campos',{}):campos['destinatarios']=hijo['destinatarios']
    # Un envío confirmado conserva el texto que efectivamente se solicitó.
    congelado = hijo.get('correoFinal') if hijo else expandir(e.datos).get('correoFinal') if e else None
    presentacion = {**PRESENTACION, **guardado.get('presentacion', {})}
    final = congelado if congelado and e.estado in ('ENTREGADA','PROCESANDO') else renderizar(codigo, fuente, campos, archivos, usuario, presentacion)
    declarado=bool(e and (e.datos.get('correoManual') or {}).get('estado')=='DECLARADO_ENVIADO')
    if congelado and (e.estado in ('ENTREGADA','PROCESANDO') or declarado or hijo and hijo.get('estado')=='ENTREGADA'):
        campos=congelado.get('campos',campos);final=congelado
    final={'imagenesDrive':[], 'presentacion':presentacion, 'fotosSeleccionadas':[], **final}
    g = integraciones.google(db, usuario)
    version = _hash([52, fuente, guardado.get('revision', 0), usuario])
    ultima=entregas.recientes(db,1,recepcion=codigo)
    resumen=entregas.resumen_final(fuente['skus'], fuente['eventos'])
    return {'campos': campos, 'version': version, 'revision': guardado.get('revision', 0), **final,
            'origen':origen,'origenes':r.origenes or [],'correosSeparados':len(r.origenes or [])>1 and (not e or bool(e.datos.get('correosPorOrigen'))),
            'correos':[{k:c.get(k) for k in ('origen','destinatarios','estado')} for c in e.datos.get('correosPorOrigen',[])] if e else [],
            'entregaDisponible':ultima[0].id if ultima and not entrega_id else '',
            'conexionConfigurada': bool(g['url'] and g['secreto']),
            'soloLectura': bool(e and e.estado in ('ENTREGADA', 'PROCESANDO') or declarado or hijo and hijo.get('estado')=='ENTREGADA'),
            'archivos': [{'id': a.id, 'nombre': a.nombre, 'url': '/api/app/archivos/' + a.id} for a in archivos],
            'limiteFotos':MAX_FOTOS, 'permiteFotoNueva':r.estado!='CERRADA',
            'fotos': [{'id': f['archivoId'], 'nombre': f.get('nombre', ''), 'sku':f.get('sku') or '',
                       'categoria':f.get('categoria') or 'GENERAL',
                       'vinculos':[{'sku':v.get('sku') or '', 'categoria':v.get('categoria') or 'GENERAL'} for v in f.get('rutasVinculadas') or [f]],
                       'esNovedad':_novedad_foto(f, resumen),
                       'enDrive':bool(f.get('fileId')), 'url': '/api/app/archivos/' + f['archivoId']} for f in fuente['fotos']],
            'manual':(db.get(AppConfig,clave_config(codigo,manual=True)).datos if db.get(AppConfig,clave_config(codigo,manual=True)) else None),
            'modificadoPor': guardado.get('usuario'), 'modificadoEn': guardado.get('fecha')}


def guardar(db, codigo, datos, usuario):
    codigo=m.obtener(db, codigo, bloquear=True).codigo
    entrega_id = str(datos.get('entregaId') or '')
    origen=str(datos.get('origen') or '')
    anterior = vista(db, codigo, usuario, entrega_id,origen)
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
    f = db.get(AppConfig, clave_config(codigo,origen=origen)) or AppConfig(clave=clave_config(codigo,origen=origen))
    presentacion=validar_presentacion(datos.get('presentacion', anterior['presentacion']), [f['id'] for f in anterior['fotos']])
    f.datos = {'campos': campos, 'presentacion':presentacion, 'revision': anterior['revision'] + 1, 'usuario': usuario, 'fecha': utcnow().isoformat()}
    f.usuario = usuario; db.add(f)
    ajustes.auditar(db, usuario, 'CORREO_BORRADOR_GUARDADO', codigo, {'revision': f.datos['revision']})
    db.commit()
    return vista(db, codigo, usuario, entrega_id,origen)


def congelar(db, codigo, datos, usuario, entrega_id=''):
    if entrega_id and db.get(AppEntrega,entrega_id).datos.get('correosPorOrigen'):
        raise HTTPException(409,'Revisa los correos independientes por embarque antes de programar esta entrega.')
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
    return {k: v[k] for k in ('asunto', 'html', 'texto', 'remitente','campos','imagenesDrive','presentacion','fotosSeleccionadas','validacionDepot') if k in v}


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
    origen=str(datos.get('origen') or '')
    if len(r.origenes or [])>1 and (not e or e.datos.get('correosPorOrigen')) and not origen:
        raise HTTPException(409,'Abre el correo del embarque que deseas copiar para el envío manual.')
    v=vista(db,codigo,usuario,ident,origen)
    if v['soloLectura']:raise HTTPException(409,'Este correo ya está confirmado o en proceso. Se conserva sin reenviarlo.')
    if datos.get('correoVersion')!=v['version']:raise HTTPException(409,'Actualiza el correo antes de preparar el envío manual.')
    if not v['campos']['destinatarios']:raise HTTPException(422,'Completa los destinatarios antes de preparar el envío manual.')
    if not v['archivos']:raise HTTPException(409,'Genera los documentos finales desde Informes antes de preparar el envío manual.')
    accion=datos.get('accion')
    if e and e.datos.get('correosPorOrigen') and accion=='CONFIRMAR':
        raise HTTPException(409,'Registra el envío manual desde Entregas y confirma cada embarque pendiente.')
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
        final={k:v[k] for k in ('asunto','html','texto','remitente','campos','imagenesDrive','presentacion','fotosSeleccionadas','validacionDepot')}
        if e.datos.get('correosPorOrigen'):
            items=[{**c,'correoFinal':final,'destinatarios':v['campos']['destinatarios']} if c['origen']==origen else c for c in e.datos['correosPorOrigen']]
            e.datos={**e.datos,'correoManual':registro,'correosPorOrigen':items,
                'destinatarios':','.join(dict.fromkeys(v for c in items for v in c['destinatarios'].split(',')))}
        else:e.datos={**e.datos,'correoManual':registro,'correoFinal':final}
        if e.datos.get('informeId'):
            informe=db.get(AppInforme,e.datos['informeId'])
            if informe:informe.estado='MANUAL_DECLARADO' if accion=='CONFIRMAR' else 'MANUAL_PREPARADO'
    f=f or AppConfig(clave=clave_config(codigo,manual=True));f.datos=registro;f.usuario=usuario;db.add(f)
    ajustes.auditar(db,usuario,'CORREO_MANUAL_'+accion,codigo,registro)
    db.commit()
    return {'mensaje':'Envío manual declarado por el supervisor; no es una confirmación de Google.' if accion=='CONFIRMAR' else 'Envíos automáticos detenidos. Copia el correo y adjunta los documentos finales.', 'manual':registro}
