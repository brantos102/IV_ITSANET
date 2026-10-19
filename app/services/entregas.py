"""Entrega durable. Google no participa en el camino del escaneo."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import timedelta
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import exists, literal, or_, select, update

from app import config
from app.db import SessionLocal
from app.models import AppArchivo, AppConfig, AppEntrega, AppInforme, AppRecepcion, utcnow
from app.services import app_modelo as m, archivos
from app.services.instantaneas import compactar, expandir

log = logging.getLogger('iv_itsanet.entregas')
ACTIVAS = ('PENDIENTE', 'PROCESANDO', 'REVISION')


def conexion_rechazada(mensaje):
    texto=str(mensaje or '').lower()
    return any(p in texto for p in ('servidor_hmac','clave compartida no coincide','misma cuenta google',
        'ejecutarse como el supervisor','archivos de versiones diferentes'))


def recientes(db, limite=100, *, recepcion=None, cliente=None, incluir_archivadas=True):
    """Ordenar claves pequeñas; recuperar las instantáneas sin filesort de JSON.

    MySQL puede agotar sort_buffer_size al ordenar SELECT * con los documentos
    de conteos, líneas y eventos de una entrega, incluso con pocas filas.
    Las dos lecturas conservan el orden y la instantánea de la transacción.
    """
    consulta = select(AppEntrega.id)
    if not incluir_archivadas:
        # El JSON grande tampoco puede participar en el filtro del filesort.
        consulta=consulta.where(~exists(select(AppConfig.clave).where(
            AppConfig.clave==literal('he:')+AppEntrega.id)))
    if recepcion is not None:
        consulta = consulta.where(AppEntrega.recepcion == recepcion)
    if cliente is not None:
        consulta = consulta.join(AppRecepcion, AppEntrega.recepcion == AppRecepcion.codigo).where(
            AppRecepcion.cliente == cliente)
    ids = list(db.scalars(consulta.order_by(AppEntrega.creado_en.desc(), AppEntrega.id.desc()).limit(limite)))
    if not ids:
        return []
    # No añadir ORDER BY aquí: volvería a meter los documentos en la ordenación.
    filas = {e.id: e for e in db.scalars(select(AppEntrega).where(AppEntrega.id.in_(ids)))}
    return [filas[ident] for ident in ids if ident in filas]


def activas(db, codigo):
    return list(db.scalars(select(AppEntrega).where(AppEntrega.recepcion == codigo,
        AppEntrega.estado.in_(ACTIVAS)).order_by(AppEntrega.id).with_for_update()
        .execution_options(populate_existing=True)))


def configurado(db=None, supervisor=None):
    from app.services.integraciones import google, puentes_publicos
    if db is None:
        with SessionLocal() as sesion:
            return configurado(sesion, supervisor)
    g = google(db, supervisor)
    return bool(g['url'] and len(g['secreto']) >= 32) or (not supervisor and bool(puentes_publicos(db)))


def documento(e, tecnico=False):
    mensajes = {
        'PENDIENTE': 'Entrega pendiente. Los informes y las evidencias permanecen guardados; no se ha confirmado el envío.',
        'PROCESANDO': 'Preparando archivos y envío. Espera la confirmación.',
        'REVISION': 'La entrega necesita revisión del administrador antes de repetir el envío.',
        'ENTREGADA': 'Envío confirmado.' if e.datos.get('destinatarios') else 'Archivos confirmados en Drive. Sin envío de correo.',
        'CANCELADA': 'Envío automático anulado. Se conservan los informes y su auditoría.',
    }
    if e.datos.get('revisionMotivo') == 'ENTREGAS_MULTIPLES':
        mensajes['REVISION'] = 'Hay varias entregas de esta recepción. ADMIN debe revisar fechas e informes y anular los envíos que no correspondan antes de reintentar.'
    if e.datos.get('revisionMotivo') == 'CONEXION_RECHAZADA':
        mensajes['REVISION'] = 'Envío pausado: autoriza tu conexión en Mi cuenta y correo. Después revisa y confirma los documentos finales; no se reintenta automáticamente.'
    if e.datos.get('revisionMotivo')=='FOTOS_RECUPERADAS':mensajes['REVISION']='Fotos en recuperación; al confirmarse, revisa y confirma los documentos finales desde tu correo.'
    if e.datos.get('correoManual'):
        mensajes['CANCELADA']='Envío manual declarado por el supervisor; sin confirmación de Google.' if e.datos['correoManual'].get('estado')=='DECLARADO_ENVIADO' else 'Preparado para envío manual. El envío automático está detenido.'
    gestion=hashlib.sha256(json.dumps([e.id,e.estado,e.intentos,e.error,e.datos],sort_keys=True,default=str).encode()).hexdigest()
    return {'correos':[{'origen':c['origen'],'estado':c['estado'],'nombre':c.get('nombre',c['origen']),'destinatarios':c['destinatarios'],'confirmadoEn':c.get('confirmadoEn')} for c in e.datos.get('correosPorOrigen',[])],
            'versionGestion':gestion,'archivado':bool(e.datos.get('historialOculto')),'correoManual':e.datos.get('correoManual'),'confirmarConCuenta':e.datos.get('confirmarConCuenta',''),'id': e.id, 'recepcion': e.recepcion, 'estado': e.estado,
            'conexionRechazada': conexion_rechazada(e.error) or e.datos.get('revisionMotivo') == 'CONEXION_RECHAZADA',
            'intentos': e.intentos, 'mensaje': (e.error if tecnico and e.estado in ACTIVAS and e.error
                else mensajes.get(e.estado, 'Comprobando entrega.')),
            **({'errorAnterior': e.error, 'anulacion': e.datos.get('anulacion')} if tecnico else {}),
            'destinatarios': e.datos.get('destinatarios', ''), 'supervisor': e.usuario,
            'remitente': e.datos.get('remitente') or e.usuario,
            'proximoIntento': m._iso(e.proximo_en) if e.estado=='PENDIENTE' and not conexion_rechazada(e.error) else None,
            'ayuda': ('La conexión de esta cuenta no fue aceptada. El supervisor puede verificar su propio puente en Mi cuenta y correo; no se solicita la clave por cada envío.'
                if e.estado in ('PENDIENTE','REVISION') and 'hmac' in str(e.error or '').lower() else
                'Se espera la copia de las fotos. Revisa las imágenes pendientes.' if e.estado == 'PENDIENTE' and 'copi' in str(e.error or '').lower() else ''),
            'revisionMotivo': e.datos.get('revisionMotivo'),
            'resultado': (e.resultado or {}) if tecnico else {
                k: v for k, v in (e.resultado or {}).items() if k in ('carpeta', 'carpetaFotos', 'sheet', 'enviadoA', 'remitente')},
            'informe': e.datos.get('informe'),
            'creadoEn': m._iso(e.creado_en)}


def resumen_final(skus, eventos=None):
    """Las cifras del correo salen de la instantanea SQL del cierre."""
    r = {'ok': 0, 'faltante': 0, 'sobrante': 0, 'unidadesEsperadas': 0,
         'unidadesFisicas': 0, 'adicionales': 0, 'discrepancias': [], 'unidadesPnc': 0, 'novedades': []}
    anulados = {e.get('anulaA') for e in eventos or [] if e.get('tipo') == 'ANULACION'}
    for s in skus:
        e, f = s.get('esperado', 0), s.get('contado', 0)
        detalle = {'sku': s['sku'], 'descripcion': s.get('descripcion', ''),
            'esperado': e, 'fisico': f, 'diferencia': f - e,
            'pallets': ', '.join(str(p) for p, n in (s.get('pallets') or {}).items() if n),
            'observacion': ' · '.join(dict.fromkeys(str(ev.get('observacion') or '').strip()
                for ev in eventos or [] if ev.get('sku') == s['sku'] and ev.get('id') not in anulados
                and not ev.get('anulaA') and str(ev.get('observacion') or '').strip()))}
        r['unidadesEsperadas'] += e
        r['unidadesFisicas'] += f
        r['adicionales'] += s.get('enPackingList') is False
        r['unidadesPnc'] += s.get('cantidadPnc') or 0
        if s.get('incidencias') or s.get('tienePnc'):
            r['novedades'].append({**detalle, 'contado': f, 'cantidadPnc': s.get('cantidadPnc'),
                'cantidadConforme': s.get('cantidadConforme'), 'incidencias': s.get('incidencias', [])})
        if f == e:
            r['ok'] += 1
        else:
            r['faltante' if f < e else 'sobrante'] += 1
            r['discrepancias'].append({**detalle, 'estado': 'Faltante' if f < e else 'Sobrante'})
    r['exactitud'] = round(r['ok'] / len(skus) * 100, 1) if skus else 0
    return r


def validar_destinatarios(valor):
    correos=[s.strip() for s in str(valor or '').split(',') if s.strip()]
    if len(correos)>20 or any(not re.fullmatch(r'[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+',c) for c in correos):
        raise HTTPException(422,'Revisa los correos de destino (máximo 20, separados por coma).')
    return ','.join(dict.fromkeys(c.lower() for c in correos))


def preparar(db, codigo, datos, usuario):
    """Archiva primero; cierre y cola se confirman en una sola transaccion."""
    destinatarios = str(datos.get('destinatarios') or '').strip()
    correos = [s.strip() for s in destinatarios.split(',') if s.strip()]
    r = m.obtener(db, codigo)
    from app.services.agrupacion_correo import configuracion as plan_correos
    plan_envio=plan_correos(db,r.codigo)
    if len(r.origenes or [])<=1 and plan_envio['modo']!='EMBARQUE' and (len(correos) > 20 or any(not re.fullmatch(r'[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+', c) for c in correos)):
        raise HTTPException(422, 'Revisa los correos de destino (separados por coma)')
    destinatarios=','.join(correos)
    libros = datos.get('adjuntos')
    if not datos.get('informeId') and (not isinstance(libros, list) or not 1 <= len(libros) <= 30):
        raise HTTPException(422, 'Se requiere un informe por packing list')
    firma_solicitud=hashlib.sha256(json.dumps([usuario,datos],sort_keys=True,default=str).encode()).hexdigest()
    if r.estado == 'CERRADA':
        anteriores = recientes(db, 1, recepcion=r.codigo)
        anterior = anteriores[0] if anteriores else None
        if anterior and anterior.datos.get('solicitudCierre')==firma_solicitud:
            return documento(anterior)
        raise HTTPException(409, 'La recepcion ya estaba cerrada sin esta entrega')
    r = m.obtener(db, codigo, bloquear=True)
    if r.estado == 'CERRADA':
        raise HTTPException(409, 'Otro supervisor ya cerro esta recepcion; actualiza la pantalla')
    plan_envio=plan_correos(db,r.codigo,actual=True)
    from app.services.agrupacion_correo import embarque
    ls=m.leer_coleccion(db,r.codigo,'lineas',actual=True)
    if len({embarque(l,plan_envio) for l in ls if embarque(l,plan_envio)})>1 and plan_envio['modo']!='EMBARQUE':
        raise HTTPException(409,'Revisa un correo y sus archivos por cada embarque antes de finalizar.')
    if activas(db, r.codigo):
        raise HTTPException(409, 'Esta recepción ya tiene una entrega sin resolver. Revisa Entrega del informe antes de generar otro envío.')
    from app.services.remitentes import elegir
    modo_entrega=datos.get('modoEntrega','AUTOMATICO')
    if modo_entrega not in ('AUTOMATICO','MANUAL','MANUAL_ENVIADO'):
        raise HTTPException(422,'Selecciona envío automático, preparación manual o envío manual declarado.')
    declarado=modo_entrega=='MANUAL_ENVIADO'
    motivo=str(datos.get('motivoManual') or '').strip()
    if declarado and (datos.get('confirmarEnviadoManual') is not True or not 10<=len(motivo)<=300):
        raise HTTPException(422,'Confirma que revisaste Enviados e indica cómo se enviaron los documentos (10–300 caracteres).')
    manual = modo_entrega in ('MANUAL','MANUAL_ENVIADO')
    if manual:
        if not (datos.get('correoVersion') or datos.get('correos')) or not destinatarios:
            raise HTTPException(422,'Revisa el correo y completa los destinatarios antes de preparar el envío manual.')
        remitente, modo_remitente = usuario, 'PERSONAL'
    else:
        remitente, modo_remitente = elegir(db, r.codigo, datos, usuario)
    from app.services.correo_redactado import congelar, clave_config
    informe = db.get(AppInforme, datos.get('informeId')) if datos.get('informeId') else None
    lote_correos=[];asignaciones_cierre={}
    if len(r.origenes or [])>1 or plan_envio['modo']=='EMBARQUE':
        from app.services.correos_embarque import congelar as congelar_embarques,asignaciones
        lote_correos=congelar_embarques(db,r,datos,usuario,informe)
        asignaciones_cierre=asignaciones(db,r.codigo)
        destinatarios=','.join(dict.fromkeys(c for item in lote_correos for c in item['destinatarios'].split(',')))
        correo_final=None
    else:correo_final = congelar(db, r.codigo, datos, usuario)
    if datos.get('informeId'):
        from app.services.informes import huella
        if not informe or informe.recepcion != r.codigo or informe.usuario != usuario or informe.tipo not in (('CORREO','DESCARGA') if manual else ('CORREO',)):
            raise HTTPException(409, 'La generación del informe no corresponde a este cierre')
        if informe.estado != 'GENERADO' or informe.huella != huella(db, r):
            raise HTTPException(409, 'El informe cambió o ya se utilizó; actualiza antes de finalizar')
        informes = [a['id'] for a in informe.datos.get('archivos', [])]
        if not informes:
            raise HTTPException(422, 'Archiva los informes antes de finalizar')
        if any(not (a:=db.get(AppArchivo,ident)) or a.recepcion!=r.codigo or not (a.drive_id or archivos.ruta(a).is_file()) for ident in informes):
            raise HTTPException(409,'Falta un documento archivado. Genera el informe actualizado antes de cerrar.')
    else:
        informes = [archivos.guardar(db, r.codigo, 'informe', l, usuario, confirmar=False).id for l in libros]
    skus = m.leer_coleccion(db, r.codigo, 'skus', actual=True)
    if not skus or any(not s.get('verificado') for s in skus):
        raise HTTPException(409, 'Verifica todas las referencias antes de finalizar')
    eventos = m.leer_coleccion(db, r.codigo, 'eventos', actual=True)
    esperados = datos.get('eventos')
    if not isinstance(esperados, list) or set(esperados) != {e['id'] for e in eventos}:
        raise HTTPException(409, 'El conteo cambio mientras se preparaba el informe. Actualiza y vuelve a finalizar')
    cierre = m.cerrar_recepcion(db, r.codigo, usuario, confirmar=False)
    fotos = list(db.scalars(select(AppArchivo.id).where(AppArchivo.recepcion == r.codigo, AppArchivo.tipo == 'foto')))
    from app.services.drive import manifiesto
    from app.services.operacion import destino_drive
    manifest = manifiesto(db, r.codigo)
    fotos = list(dict.fromkeys(f['archivoId'] for f in manifest))
    destino = destino_drive(db, r.codigo)
    destino.pop('supervisor', None)
    e = AppEntrega(id=uuid4().hex, recepcion=r.codigo, usuario=usuario,
        clave=hashlib.sha256(f'{r.codigo}|{r.cerrada_en}'.encode()).hexdigest(),
        estado='CANCELADA' if manual else 'PENDIENTE', datos={
            'solicitudCierre':firma_solicitud,
            'destinatarios': destinatarios, 'informes': informes, 'fotos': fotos,
            **({'correosPorOrigen':lote_correos,'asignacionesAdicionales':asignaciones_cierre,'planCorreos':plan_envio} if lote_correos else {}),
            **({'correoFinal':correo_final} if correo_final else {}),
            'remitente': remitente, 'modoRemitente': modo_remitente,
            'carpetaMes': str(datos.get('carpetaMes') or '')[:100],
            'carpetaRecepcion': str(datos.get('carpetaRecepcion') or r.codigo)[:200],
            'duracion': str(datos.get('duracion') or '')[:100],
            'resumen': resumen_final(skus, eventos), 'exportarSheet': datos.get('exportarSheet') is True,
            'recepcion': cierre, 'skus': skus, 'destino': destino,
            'lineas': m.leer_coleccion(db, r.codigo, 'lineas', actual=True),
            'eventos': eventos},
        error=None if manual or configurado(db) else 'Pendiente de configurar el puente con Google')
    db.add(e)
    if informe:
        informe.estado = ('MANUAL_DECLARADO' if declarado else 'MANUAL_PREPARADO') if manual else 'EN_COLA'
        informe.datos = {**informe.datos, 'entregaId': e.id}
        e.datos = {**e.datos, 'informeId': informe.id, 'informe': {
            'id': informe.id, 'numero': informe.numero, 'usuario': informe.usuario,
            'creadoEn': m._iso(informe.creado_en)}}
    if manual:
        registro={'estado':'DECLARADO_ENVIADO' if declarado else 'PREPARADO','usuario':usuario,'fecha':utcnow().isoformat(),'entregaId':e.id,
                  **({'motivo':motivo} if declarado else {}),
                  'version':datos.get('correoVersion',''),'destinatarios':destinatarios,'asunto':correo_final['asunto'] if correo_final else 'Correos por packing list · '+r.codigo}
        e.datos={**e.datos,'correoManual':registro}
        if declarado and lote_correos:
            e.datos={**e.datos,'correosPorOrigen':[{**c,'estado':'MANUAL_DECLARADO'} for c in lote_correos]}
        from app.models import AppConfig
        f=db.get(AppConfig,clave_config(r.codigo,manual=True)) or AppConfig(clave=clave_config(r.codigo,manual=True))
        f.datos=registro;f.usuario=usuario;db.add(f)
        from app.services.ajustes import auditar
        auditar(db,usuario,'CIERRE_ENVIO_MANUAL',r.codigo,registro)
    e.datos = compactar(e.datos)
    db.commit()
    return documento(e)


class RevisionEntrega(Exception):
    pass


def _error_google(respuesta):
    """Traducir solo categorías conocidas; nunca reenviar textos con secretos."""
    mensaje = str(respuesta.get('mensaje') or respuesta.get('error') or '').lower()
    if 'proxy.gs' in mensaje or 'servidor.gs' in mensaje:
        return 'El puente tiene archivos de versiones diferentes. ADMIN debe actualizar Proxy.gs y Servidor.gs juntos y publicar una nueva versión del mismo despliegue /exec. Se conserva la clave guardada.'
    if 'firma' in mensaje or 'hmac' in mensaje:
        return 'La clave compartida no coincide con SERVIDOR_HMAC de este Apps Script.'
    if 'userinfo.email' in mensaje or 'session.geteffectiveuser' in mensaje:
        return 'Google no autorizó leer la cuenta remitente. Ejecuta verificarGoogleServidor en Apps Script con la cuenta responsable, acepta los permisos y actualiza el despliegue /exec.'
    if 'cuota' in mensaje or 'quota' in mensaje:
        return 'Google informa que no hay cuota de correo disponible. Revisa la cuota de la cuenta responsable antes de reintentar.'
    if any(c in mensaje for c in ('script.send_mail', 'mailapp', 'permiso de correo', 'sendemail')):
        return 'Falta autorización para enviar correo. Ejecuta verificarGoogleServidor con la cuenta responsable, acepta el permiso de correo y publica una versión nueva del despliegue /exec.'
    if 'carpeta_evidencias' in mensaje or 'repositorio invalido' in mensaje or 'repositorio inválido' in mensaje:
        return 'La carpeta raíz de Drive no está configurada correctamente. Revisa CARPETA_EVIDENCIAS en Apps Script y el ID del repositorio en Administración.'
    if any(c in mensaje for c in ('driveapp', 'getfolderbyid', 'getfilebyid', 'carpeta drive', 'file not found', 'no item with the given id')):
        return 'La cuenta responsable no puede abrir la carpeta o archivo de Drive, o le falta autorización. Comparte la carpeta con esa cuenta, revisa su ID y ejecuta verificarGoogleServidor para autorizar Drive.'
    if 'supervisor' in mensaje or 'ejecut' in mensaje:
        return 'El despliegue debe ejecutarse con la misma cuenta Google que el remitente seleccionado. Revisa «Ejecutar como: Yo» y la cuenta que publicó el puente.'
    if 'unknown' in mensaje or 'desconocida' in mensaje or 'no permitida' in mensaje:
        return 'El puente publicado no reconoce esta operación. Copia los archivos actuales del puente y actualiza su despliegue /exec con una versión nueva.'
    return 'Google no confirmó la operación. Ejecuta verificarGoogleServidor en Apps Script con la cuenta responsable para identificar el permiso o carpeta que falla; después actualiza el despliegue /exec.'


def llamar(operacion, clave, datos):
    from app.services.integraciones import google
    with SessionLocal() as db:
        destino = google(db, datos.get('usuario'))
    return llamar_conexion(operacion, clave, datos, destino)


def llamar_conexion(operacion, clave, datos, destino):
    """Verifica una conexión candidata sin guardarla ni cambiar tareas pendientes."""
    payload = json.dumps({'operacion': operacion, 'clave': clave,
        'fecha': int(time.time()), 'datos': datos}, ensure_ascii=False, separators=(',', ':'))
    if not destino['url'] or len(destino['secreto']) < 32:
        raise RuntimeError('Guarda el enlace /exec y la clave compartida del puente de este supervisor en Administración.')
    firma = hmac.new(destino['secreto'].encode(), payload.encode(), hashlib.sha256).hexdigest()
    # Solo el servidor contacta Google; nunca se envia esta clave al navegador.
    # La consulta de estado no sube archivos ni envía correo. Debe devolver
    # un diagnóstico antes de agotar el tiempo del proxy público.
    timeout = httpx.Timeout(25, connect=8) if operacion == 'estado' else 120
    with httpx.Client(timeout=timeout, follow_redirects=True) as cliente:
        try:
            respuesta = cliente.post(destino['url'],
                json={'accion': 'entregaServidor', 'payload': payload, 'firma': firma})
        except httpx.TimeoutException:
            if operacion != 'estado': raise
            raise RuntimeError('La verificación de Google agotó el tiempo de espera. Comprueba salida HTTPS desde la PC/servidor y ejecuta verificarGoogleServidor en Apps Script. Esta consulta no envía correo ni modifica Drive.') from None
        except httpx.RequestError:
            if operacion != 'estado': raise
            raise RuntimeError('La PC/servidor no pudo conectar con el puente Google. Revisa DNS, salida HTTPS de Docker, proxy de red y confianza del certificado. No cambies la clave compartida por este error de conexión; esta consulta no envía correo.') from None
        if respuesta.status_code == 404:
            raise RuntimeError('Google respondió HTTP 404: la URL del despliegue /exec no está disponible para el servidor. En Apps Script → Implementar → Administrar implementaciones, copia la URL de la aplicación web activa (no el ID del proyecto ni la carpeta Drive), guárdala en Guardar puente y vuelve a verificar. Conserva la clave compartida.')
        if respuesta.status_code >= 400:
            raise RuntimeError(f'Google respondió HTTP {respuesta.status_code}. Revisa el despliegue web /exec y su acceso; vuelve a publicarlo después de actualizar el script.')
        try:
            r = respuesta.json()
        except ValueError:
            raise RuntimeError('El enlace devolvió una página web en lugar del puente. Usa el despliegue /exec, ejecutado como el supervisor y con acceso para las peticiones del servidor.') from None
    if not isinstance(r, dict):
        raise RuntimeError('La respuesta de Google no corresponde al puente de ITSANET.')
    if not r.get('exito'):
        if r.get('revision'):
            raise RevisionEntrega('Google requiere revisar el correo antes de reintentar')
        raise RuntimeError(_error_google(r))
    return r


def procesar_uno():
    if not configurado():
        return False
    ahora = utcnow()
    with SessionLocal() as db:
        # Arrendamiento permite recuperacion tras reinicio, sin dos workers simultaneos.
        elegible = or_(AppEntrega.estado == 'PENDIENTE', AppEntrega.estado == 'PROCESANDO')
        ident = db.scalar(select(AppEntrega.id).where(elegible, AppEntrega.proximo_en <= ahora)
                          .order_by(AppEntrega.creado_en).limit(1))
        if not ident:
            return False
        seleccionada = db.get(AppEntrega, ident)
        m.obtener(db, seleccionada.recepcion, bloquear=True)
        grupo = activas(db, seleccionada.recepcion)
        if len(grupo) > 1:
            for pendiente in grupo:
                if pendiente.estado == 'PENDIENTE':
                    pendiente.estado = 'REVISION'
                    pendiente.datos = {**pendiente.datos, 'revisionMotivo': 'ENTREGAS_MULTIPLES'}
                    pendiente.error = 'Hay varias entregas de esta recepción. Revisa fechas e informes, anula las que no correspondan y reintenta únicamente la entrega elegida.'
                elif pendiente.estado == 'PROCESANDO' and pendiente.proximo_en.replace(tzinfo=None) <= ahora.replace(tzinfo=None):
                    pendiente.estado = 'REVISION'
                    pendiente.datos = {**pendiente.datos, 'revisionMotivo': 'ENTREGA_INTERRUMPIDA'}
                    pendiente.error = 'Entrega interrumpida con otras versiones pendientes. Revisa Enviados antes de decidir qué informe corresponde; no se reenvía automáticamente.'
            db.commit()
            return True
        cambio = db.execute(update(AppEntrega).where(AppEntrega.id == ident, elegible,
            AppEntrega.proximo_en <= ahora).values(estado='PROCESANDO', proximo_en=ahora + timedelta(minutes=15))
            .execution_options(synchronize_session=False))
        db.commit()
        if cambio.rowcount != 1:
            return False
        e = db.get(AppEntrega, ident)
        db.refresh(e)
        e.intentos += 1
        db.commit()
        try:
            d = expandir(e.datos)
            # También protege entregas preparadas antes de la actualización:
            # COPIADA no confirma que la foto siga en el embarque vigente.
            from app.services.drive import ubicacion_evidencia
            from app.services.fotos_embarques import informacion
            from app.models import AppEvidencia, AppCopiaDrive
            fuente_fotos=informacion(db,e.recepcion)
            if fuente_fotos[3]:
                for ev in db.scalars(select(AppEvidencia).where(AppEvidencia.recepcion==e.recepcion,AppEvidencia.eliminado_en.is_(None))):
                    ubicacion=ubicacion_evidencia(db,ev,db.get(AppCopiaDrive,ev.archivo_id),fuente=fuente_fotos)
                    if ubicacion['estado'] in ('ASIGNAR_EMBARQUE','ACTUALIZAR_CARPETAS'):
                        raise RuntimeError('Organiza las fotos por embarque en Fotos → Actualizar carpetas por embarque. La entrega esperará su confirmación; no se envió correo.')
            if conexion_rechazada(e.error):
                raise RuntimeError(e.error)
            remitente = d.get('remitente') or e.usuario
            estado = llamar('estado', e.id, {**d.get('destino', {}), 'usuario': remitente})
            if str(estado.get('remitente') or '').strip().lower() != remitente.strip().lower():
                raise RuntimeError('El puente no verifica la cuenta del supervisor responsable. No se enviaron archivos ni correo.')
            if (d.get('correoFinal') or d.get('correosPorOrigen')) and 'correoEditable' not in estado.get('capacidades',[]):
                raise RuntimeError('El puente tiene archivos de versiones diferentes. Actualiza Proxy.gs y Servidor.gs y publica una nueva versión del mismo /exec para enviar el correo revisado.')
            from app.services.drive import manifiesto
            # Las fotos finales pueden agregarse después del cierre. Incluirlas
            # antes de preparar el correo, sin alterar los informes de conteo.
            fotos_actuales = list(dict.fromkeys(f['archivoId'] for f in manifiesto(db, e.recepcion)))
            if fotos_actuales != d['fotos']:
                d = {**d, 'fotos': fotos_actuales}
                if d.get('informeEvidencias'):
                    anterior = d['informeEvidencias']
                    d = {**d, 'informes': [a for a in d['informes'] if a != anterior],
                        'informeEvidencias': None,
                        'evidenciasAnteriores': [*d.get('evidenciasAnteriores', []), anterior]}
                e.datos = compactar(d)
                db.commit()
            if d['fotos'] and not d.get('informeEvidencias') and not d.get('correosPorOrigen'):
                imagenes=[db.get(AppArchivo,aid) for aid in d['fotos']]
                if all(a and a.drive_id for a in imagenes):
                    from app.services.reporte_evidencias import generar
                    generacion=db.get(AppInforme,d['informeId']) if d.get('informeId') else None
                    sufijo=generacion.datos.get('sufijo','') if generacion else ''
                    informe=archivos.guardar(db,e.recepcion,'informe',{
                        'nombre':'Evidencias_'+e.recepcion+sufijo+'_'+hashlib.sha256('|'.join(d['fotos']).encode()).hexdigest()[:8]+'.xlsx',
                        'base64':base64.b64encode(generar(db,e.recepcion,generacion)).decode()},e.usuario,confirmar=False)
                    d={**d,'informes':d['informes']+[informe.id],'informeEvidencias':informe.id}
                    e.datos=compactar(d);db.commit()
            guardados = []
            for aid in d['informes'] + d['fotos']:
                a = db.get(AppArchivo, aid)
                if not a:
                    raise RuntimeError('Falta un archivo de la entrega; revisa el almacenamiento')
                from app.models import AppCopiaDrive
                copia_pendiente = db.get(AppCopiaDrive, aid)
                if copia_pendiente and copia_pendiente.estado in ('PENDIENTE', 'PROCESANDO','REVISION'):
                    raise RuntimeError('Las evidencias siguen copiándose a Drive; la entrega esperará su confirmación')
                e.proximo_en = utcnow() + timedelta(minutes=15)
                db.commit()
                if a.drive_id:
                    copia = {'exito': True, 'fileId': a.drive_id, 'nombre': a.nombre,
                        'tipoArchivo': a.tipo, 'enlace': a.drive_url,
                        'url': 'https://drive.google.com/uc?id=' + a.drive_id}
                else:
                    if not archivos.ruta(a).is_file():
                        raise RuntimeError('Falta un archivo local; revisa el almacenamiento antes de entregar')
                    copia = llamar('archivo', e.id + ':' + aid, {
                        **d.get('destino', {}),
                        'recepcion': e.recepcion, 'usuario': remitente, 'tipoArchivo': a.tipo,
                        'nombre': a.nombre, 'tipo': a.mime,
                        'base64': base64.b64encode(archivos.ruta(a).read_bytes()).decode(),
                        'carpetaMes': d['carpetaMes'], 'carpetaRecepcion': d['carpetaRecepcion']})
                    drive_id = str(copia.get('fileId') or '')
                    if not re.fullmatch(r'[a-zA-Z0-9_-]{5,128}', drive_id):
                        raise RuntimeError('Google no confirmo un identificador de archivo valido')
                    a.drive_id, a.drive_url = drive_id, 'https://drive.google.com/file/d/' + drive_id + '/view'
                    db.commit()
                guardados.append({**copia,'nombre':a.nombre,'tipoArchivo':a.tipo})
                # La imagen no ocupa MySQL ni queda duplicada tras confirmar Drive.
                if a.tipo == 'foto':
                    try:
                        archivos.ruta(a).unlink(missing_ok=True)
                    except OSError:
                        log.warning('Entrega %s: foto copiada, limpieza local pendiente', e.id)
            manifest = manifiesto(db, e.recepcion)
            if {f['archivoId'] for f in manifest} != set(d['fotos']):
                raise RuntimeError('Se actualizaron las fotos durante la preparación. La entrega se preparará nuevamente con las evidencias actuales.')
            payload = {**d, **d.get('destino', {}), 'manifiesto': manifest,
                'archivos': guardados, 'codigo': e.recepcion, 'usuario': remitente, 'solicitadoPor': e.usuario}
            if d.get('exportarSheet'):
                referencias = {a.id: a.drive_url for a in db.scalars(select(AppArchivo).where(AppArchivo.recepcion == e.recepcion)) if a.drive_url}
                def enlace_foto(url):
                    ident = str(url).split('/api/app/archivos/')[-1].split('?')[0]
                    return referencias.get(ident, url)
                payload['eventos'] = [{**ev, 'fotos': [enlace_foto(url) for url in ev.get('fotos', [])]} for ev in d['eventos']]
            else:
                for campo in ('skus', 'lineas', 'eventos'):
                    payload.pop(campo, None)
            if d.get('correosPorOrigen'):
                from app.services.correos_embarque import enviar_lote
                resultado=enviar_lote(db,e,d,guardados,manifest,llamar)
            else:resultado = llamar('finalizar', e.id, payload)
            if d.get('modoRemitente') in ('PERSONAL','RESPONSABLE') and d.get('destinatarios'):
                normalizar=lambda v:{c.strip().lower() for c in str(v or '').split(',') if c.strip()}
                if normalizar(resultado.get('enviadoA')) != normalizar(d['destinatarios']):
                    raise RevisionEntrega('Google confirmó una operación, pero no confirmó los destinatarios del correo. Revisa Enviados; el informe no se reenviará automáticamente.')
            if (d.get('modoRemitente') in ('RESPONSABLE', 'PERSONAL')
                    and str(resultado.get('remitente') or '').strip().lower() != remitente.strip().lower()):
                raise RevisionEntrega('Google no confirmó el remitente del envío final. Revisa Enviados antes de reintentar; el informe no se reenviará automáticamente.')
            resultado = {**resultado, 'confirmadoEn': resultado.get('confirmadoEn') or m._iso(utcnow())}
            e.estado, e.resultado, e.error = 'ENTREGADA', resultado, None
            if d.get('informeId'):
                informe = db.get(AppInforme, d['informeId'])
                if informe:
                    informe.estado = 'ENVIADO' if d.get('destinatarios') else 'EN_DRIVE'
                    informe.datos = {**informe.datos, 'confirmadoEn': resultado['confirmadoEn'],
                        'destinatarios': d.get('destinatarios', '')}
                    from app.services.ajustes import auditar
                    auditar(db, e.usuario, 'ENTREGA_CONFIRMADA', e.recepcion,
                        {'informeId': informe.id, 'destinatarios': d.get('destinatarios', ''),
                         'confirmadoEn': resultado['confirmadoEn'], 'remitente': remitente})
        except RevisionEntrega as exc:
            e.estado, e.error = 'REVISION', str(exc)
            if d.get('informeId'):
                informe = db.get(AppInforme, d['informeId'])
                if informe:
                    informe.estado = 'REVISION'
        except Exception as exc:
            # No persistir textos HTTP que pueden contener URL firmada o datos secretos.
            e.estado = 'PENDIENTE'
            e.error = str(exc)[:300] if type(exc) is RuntimeError else 'No hubo confirmacion de Google; se reintentara'
            e.proximo_en = utcnow() + timedelta(seconds=min(3600, 30 * 2 ** min(e.intentos, 7)))
            if type(exc) is RuntimeError and conexion_rechazada(e.error):
                e.estado='REVISION'
                e.datos={**e.datos,'revisionMotivo':'CONEXION_RECHAZADA','conexionFallidaEn':m._iso(utcnow())}
            log.warning('Entrega %s pendiente (%s)', e.id, type(exc).__name__)
        db.commit()
    return True


async def trabajador():
    while True:
        try:
            ocupado = await asyncio.to_thread(procesar_uno)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning('No se pudo revisar la cola de entregas')
            ocupado = False
        await asyncio.sleep(1 if ocupado else 15)
