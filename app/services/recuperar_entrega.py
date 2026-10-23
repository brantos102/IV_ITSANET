"""Recuperación explícita del informe archivado, sin repetir cierre ni conteos."""
import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models import AppArchivo, AppEntrega, AppInforme, utcnow
from app.services import app_modelo as m, ajustes, archivos, entregas, integraciones, operacion, remitentes
from app.services.instantaneas import compactar, expandir


def _grupo(db, codigo, bloquear=False):
    consulta = select(AppEntrega).where(AppEntrega.recepcion == codigo).order_by(AppEntrega.id)
    if bloquear:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    return list(db.scalars(consulta))


def _validar(db, e, grupo, *, manual_confirmado=False):
    if (e.datos.get('correoManual') or {}).get('estado')=='DECLARADO_ENVIADO':
        raise HTTPException(409,'El supervisor ya declaró el envío manual. Se conserva el historial y no se reenvían estos documentos.')
    d = expandir(e.datos)
    r = m.obtener(db, e.recepcion)
    if r.estado != 'CERRADA' and not (d.get('reporteSinCierre') and r.estado in m.ABIERTAS):
        raise HTTPException(409, 'La recepción cambió o fue reabierta. Revisa el conteo y genera su informe al finalizar.')
    ultima = max(grupo, key=lambda g: (g.creado_en, g.id))
    if ultima.id != e.id:
        raise HTTPException(409, 'Selecciona la entrega más reciente de esta recepción; no recuperes un informe antiguo.')
    if e.estado not in ('CANCELADA', 'PENDIENTE', 'REVISION'):
        raise HTTPException(409, 'Esta entrega ya está confirmada o se está procesando. Actualiza el estado.')
    if any(g.estado == 'PROCESANDO' or not manual_confirmado and g.estado == 'REVISION' and
           g.datos.get('revisionMotivo') not in ('ENTREGAS_MULTIPLES','CONEXION_RECHAZADA','FOTOS_RECUPERADAS') for g in grupo):
        raise HTTPException(409, 'Hay un envío en curso o con confirmación interrumpida. Revisa Enviados antes de recuperar; no se repetirá automáticamente.')
    campos = ('sku', 'esperado', 'contado', 'verificado', 'cantidadPnc', 'incidencias', 'pallets', 'descripcion')
    comparar = lambda filas: sorted([{k: s.get(k) for k in campos} for s in filas], key=lambda s: s['sku'])
    if comparar(d.get('skus', [])) != comparar(m.leer_coleccion(db, r.codigo, 'skus', actual=True)):
        raise HTTPException(409, 'El conteo cambió desde este informe. Revisa y finaliza con un informe actualizado.')
    actuales = m.leer_coleccion(db, r.codigo, 'eventos', actual=True)
    # El cierre agrega su propio evento después de congelar el informe.
    # Exportar o auditar tampoco altera el conteo; reaperturas y ajustes sí.
    relevantes = lambda filas: sorted([ev for ev in filas if ev.get('tipo') not in
        ('CIERRE', 'EXPORT', 'AUDITORIA')], key=lambda ev: ev['id'])
    if relevantes(actuales) != relevantes(d.get('eventos', [])):
        raise HTTPException(409, 'La bitácora cambió desde este informe; genera un informe actualizado.')
    if d.get('recepcion', {}).get('formatos', {}) != (r.formatos or {}):
        raise HTTPException(409, 'Cambió el formato de exportación; genera un informe actualizado.')
    for aid in e.datos.get('informes', []):
        a = db.get(AppArchivo, aid)
        if not a or a.recepcion != r.codigo or a.tipo != 'informe' or not (a.drive_id or archivos.ruta(a).is_file()):
            raise HTTPException(409, 'Falta un informe archivado; revisa el almacenamiento antes de enviar.')
    if not e.datos.get('informes'):
        raise HTTPException(409, 'Esta entrega no tiene informes archivados.')


def vista(db, ident, usuario, modo='RESPONSABLE'):
    e = db.get(AppEntrega, ident)
    if not e:
        raise HTTPException(404, 'Entrega no encontrada')
    grupo = _grupo(db, e.recepcion)
    _validar(db, e, grupo)
    opcion = next(o for o in remitentes.opciones(db, e.recepcion, usuario)['opciones'] if o['modo'] == modo)
    return {'entrega': entregas.documento(e, tecnico=True), 'responsable': opcion,
        'sustituye': [entregas.documento(g, tecnico=True) for g in grupo
            if g.id != e.id and g.estado in entregas.ACTIVAS],
        'archivos': [db.get(AppArchivo, aid).nombre for aid in e.datos['informes']]}


def _firma_config(db, correo, codigo):
    g = integraciones.google(db, correo)
    d = operacion.destino_drive(db, codigo)
    return hashlib.sha256(json.dumps([g, d], sort_keys=True).encode()).hexdigest()


def recuperar(db, ident, datos, usuario):
    modo_solicitado = datos.get('modoRemitente', 'RESPONSABLE')
    motivo = str(datos.get('motivo') or '').strip()
    if not 10 <= len(motivo) <= 300 or datos.get('confirmarNoEnviado') is not True:
        raise HTTPException(422, 'Indica el motivo (10–300 caracteres) y confirma que revisaste Enviados y que este informe no fue enviado.')
    vista(db, ident, usuario, modo_solicitado)
    e = db.get(AppEntrega, ident)
    codigo = e.recepcion
    destinatarios=entregas.validar_destinatarios(datos.get('destinatarios',e.datos.get('destinatarios',''))) if not e.datos.get('correosPorOrigen') else e.datos.get('destinatarios','')
    if 'destinatarios' in datos and not destinatarios:raise HTTPException(422,'Indica al menos un destinatario para enviar los documentos finales.')
    correo, modo = remitentes.elegir(db, codigo, {'modoRemitente': modo_solicitado,
        'remitenteConfirmado': datos.get('remitenteConfirmado', '')}, usuario)
    firma = _firma_config(db, correo, codigo)
    instantanea = json.dumps(e.datos, sort_keys=True)
    destino = operacion.destino_drive(db, codigo)
    # La llamada externa no retiene bloqueos de recepción o entrega.
    db.rollback()
    try:
        estado = entregas.llamar('estado', uuid4().hex, {'usuario': correo, 'carpetaRaiz': destino['carpetaRaiz']})
        if str(estado.get('remitente') or '').lower() != correo or estado.get('versionPuente', 0) < 2:
            raise RuntimeError('Google no confirmó la cuenta responsable o la versión del puente.')
        if modo_solicitado == 'PERSONAL' and 'correoVerificado' not in estado.get('capacidades', []):
            raise RuntimeError('Actualiza Proxy.gs y Servidor.gs juntos y publica una versión nueva del despliegue /exec antes de solicitar el envío.')
        if destino['carpetaRaiz'] and estado.get('carpetaId') != destino['carpetaRaiz']:
            raise RuntimeError('Google no confirmó la carpeta raíz configurada.')
    except Exception as exc:
        mensaje = str(exc) if type(exc) is RuntimeError else 'No se pudo verificar el puente de la cuenta responsable. Revisa Drive y envío de correo.'
        raise HTTPException(502, mensaje + ' No se recuperó ni envió el informe.') from None
    db.rollback()
    m.obtener(db, codigo, bloquear=True)
    grupo = _grupo(db, codigo, bloquear=True)
    e = next(g for g in grupo if g.id == ident)
    _validar(db, e, grupo)
    if json.dumps(e.datos, sort_keys=True) != instantanea or _firma_config(db, correo, codigo) != firma:
        raise HTTPException(409, 'Cambió el envío o la configuración mientras se verificaba. Actualiza antes de recuperar.')
    remitentes.elegir(db, codigo, {'modoRemitente': modo_solicitado, 'remitenteConfirmado': correo}, usuario)
    ahora = utcnow()
    for g in grupo:
        if g.id != ident and g.estado in entregas.ACTIVAS:
            g.estado = 'CANCELADA'
            g.datos = {**g.datos, 'anulacion': {'usuario': usuario, 'fecha': m._iso(ahora),
                'motivo': motivo, 'sustituidaPor': ident}}
            ajustes.auditar(db, usuario, 'ENVIO_ANULADO', codigo, {'entregaId': g.id, 'sustituidaPor': ident, 'motivo': motivo})
            if g.datos.get('informeId'):
                informe = db.get(AppInforme, g.datos['informeId'])
                if informe and informe.datos.get('entregaId') == g.id:
                    informe.estado = 'CANCELADO'
    recuperacion = {'usuario': usuario, 'fecha': m._iso(ahora), 'motivo': motivo,
        'remitenteAnterior': e.datos.get('remitente') or e.usuario, 'remitente': correo,
        'estadoAnterior': e.estado, 'confirmarNoEnviado': True,
        'destinatariosAnteriores':e.datos.get('destinatarios',''),'destinatarios':destinatarios}
    completo = expandir(e.datos)
    from app.services.correo_redactado import congelar
    lote={}
    if e.datos.get('correosPorOrigen'):
        from app.services.correos_embarque import congelar as congelar_lote
        items=congelar_lote(db,m.obtener(db,codigo),datos,usuario,db.get(AppInforme,e.datos['informeId']),ident)
        # Un cambio de remitente no modifica mensajes ya confirmados.
        if any(c.get('estado')=='ENTREGADA' for c in items) and correo!=(e.datos.get('remitente') or e.usuario):
            raise HTTPException(409,'Conserva la cuenta remitente que inició este lote; algunos embarques ya están confirmados.')
        lote={'correosPorOrigen':items,'correoManual':None}
        if e.datos.get('correoManual'):recuperacion['preparacionManualAnterior']=e.datos['correoManual']
        destinatarios=','.join(dict.fromkeys(v for c in items for v in c['destinatarios'].split(',')))
        correo_final=None
    else:correo_final = congelar(db,codigo,datos,usuario,ident)
    e.datos = compactar({**completo, 'remitente': correo, 'modoRemitente': modo,'destinatarios':destinatarios,'confirmarConCuenta':correo,
        **({'correoFinal':correo_final} if correo_final else {}),**lote,
        'destino': {k: v for k, v in destino.items() if k != 'supervisor'},
        'resumen': entregas.resumen_final(completo['skus'], completo['eventos']),
        'revisionMotivo': None, 'recuperaciones': [*e.datos.get('recuperaciones', []), recuperacion]})
    e.estado, e.error, e.proximo_en = 'PENDIENTE', None, ahora
    if e.datos.get('informeId'):
        informe = db.get(AppInforme, e.datos['informeId'])
        if informe and informe.datos.get('entregaId') == e.id:
            informe.estado = 'EN_COLA'
    ajustes.auditar(db, usuario, 'ENVIO_RECUPERADO', codigo, {'entregaId': ident, **recuperacion})
    db.commit()
    return entregas.documento(e, tecnico=True)


def comprobar_solicitud(db,ident,usuario):
    v=vista(db,ident,usuario,'PERSONAL')
    if not v['responsable']['disponible']:
        raise HTTPException(409,'Autoriza primero tu propia conexión en Mi cuenta y correo. No se envió ningún documento.')
    email=v['responsable']['correo'];codigo=v['entrega']['recepcion']
    from app.services.drive import resumen_fotos
    if resumen_fotos(db,codigo)['pendientes']:
        raise HTTPException(409,'Todavía hay fotos pendientes en Drive. Revisa Drive y fotos antes de confirmar el correo final.')
    destino=operacion.destino_drive(db,codigo);db.rollback()
    try:
        r=entregas.llamar('estado',uuid4().hex,{'usuario':email,'carpetaRaiz':destino['carpetaRaiz']})
        if str(r.get('remitente') or '').lower()!=email or 'correoVerificado' not in r.get('capacidades',[]):
            raise RuntimeError('Google no confirmó tu cuenta y la versión publicada del puente. Autoriza tu propio /exec en Mi cuenta y correo.')
    except RuntimeError as exc:
        raise HTTPException(502,str(exc)+' No se envió ningún documento.') from None
    db.rollback();v=vista(db,ident,usuario,'PERSONAL')
    return {**v,'conexionVerificada':True}
