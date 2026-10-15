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
from sqlalchemy import or_, select, update

from app import config
from app.db import SessionLocal
from app.models import AppArchivo, AppEntrega, utcnow
from app.services import app_modelo as m, archivos

log = logging.getLogger('iv_itsanet.entregas')


def configurado(db=None):
    from app.services.integraciones import google
    if db is None:
        with SessionLocal() as sesion:
            return configurado(sesion)
    g = google(db)
    return bool(g['url'] and len(g['secreto']) >= 32)


def documento(e):
    return {'id': e.id, 'recepcion': e.recepcion, 'estado': e.estado,
            'intentos': e.intentos, 'mensaje': e.error,
            'destinatarios': e.datos.get('destinatarios', ''),
            'resultado': e.resultado or {}, 'creadoEn': m._iso(e.creado_en)}


def preparar(db, codigo, datos, usuario):
    """Archiva primero; cierre y cola se confirman en una sola transaccion."""
    destinatarios = str(datos.get('destinatarios') or '').strip()
    correos = [s.strip() for s in destinatarios.split(',') if s.strip()]
    if len(correos) > 20 or any(not re.fullmatch(r'[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+', c) for c in correos):
        raise HTTPException(422, 'Revisa los correos de destino (separados por coma)')
    libros = datos.get('adjuntos')
    if not isinstance(libros, list) or not 1 <= len(libros) <= 30:
        raise HTTPException(422, 'Se requiere un informe por packing list')
    r = m.obtener(db, codigo)
    if r.estado == 'CERRADA':
        anterior = db.scalar(select(AppEntrega).where(AppEntrega.recepcion == r.codigo)
                             .order_by(AppEntrega.creado_en.desc()))
        if anterior and anterior.clave == hashlib.sha256(f'{r.codigo}|{r.cerrada_en}'.encode()).hexdigest():
            return documento(anterior)
        raise HTTPException(409, 'La recepcion ya estaba cerrada sin esta entrega')
    informes = [archivos.guardar(db, r.codigo, 'informe', l, usuario).id for l in libros]
    r = m.obtener(db, codigo, bloquear=True)
    if r.estado == 'CERRADA':
        raise HTTPException(409, 'Otro supervisor ya cerro esta recepcion; actualiza la pantalla')
    skus = m.leer_coleccion(db, r.codigo, 'skus', actual=True)
    if not skus or any(not s.get('verificado') for s in skus):
        raise HTTPException(409, 'Verifica todas las referencias antes de finalizar')
    eventos = m.leer_coleccion(db, r.codigo, 'eventos', actual=True)
    esperados = datos.get('eventos')
    if not isinstance(esperados, list) or set(esperados) != {e['id'] for e in eventos}:
        raise HTTPException(409, 'El conteo cambio mientras se preparaba el informe. Actualiza y vuelve a finalizar')
    cierre = m.cerrar_recepcion(db, r.codigo, usuario, confirmar=False)
    fotos = list(db.scalars(select(AppArchivo.id).where(AppArchivo.recepcion == r.codigo, AppArchivo.tipo == 'foto')))
    e = AppEntrega(id=uuid4().hex, recepcion=r.codigo, usuario=usuario,
        clave=hashlib.sha256(f'{r.codigo}|{r.cerrada_en}'.encode()).hexdigest(),
        estado='PENDIENTE', datos={
            'destinatarios': ','.join(correos), 'informes': informes, 'fotos': fotos,
            'carpetaMes': str(datos.get('carpetaMes') or '')[:100],
            'carpetaRecepcion': str(datos.get('carpetaRecepcion') or r.codigo)[:200],
            'duracion': str(datos.get('duracion') or '')[:100],
            'resumen': datos.get('resumen') or {}, 'exportarSheet': datos.get('exportarSheet') is True,
            'recepcion': cierre, 'skus': skus,
            'lineas': m.leer_coleccion(db, r.codigo, 'lineas', actual=True),
            'eventos': eventos},
        error=None if configurado(db) else 'Pendiente de configurar el puente con Google')
    db.add(e)
    db.commit()
    return documento(e)


class RevisionEntrega(Exception):
    pass


def llamar(operacion, clave, datos):
    """El HMAC firma el texto exacto, incluida accion, clave y caducidad."""
    payload = json.dumps({'operacion': operacion, 'clave': clave,
        'fecha': int(time.time()), 'datos': datos}, ensure_ascii=False, separators=(',', ':'))
    from app.services.integraciones import google
    with SessionLocal() as db:
        destino = google(db)
    firma = hmac.new(destino['secreto'].encode(), payload.encode(), hashlib.sha256).hexdigest()
    # Solo el servidor contacta Google; nunca se envia esta clave al navegador.
    with httpx.Client(timeout=120, follow_redirects=True) as cliente:
        respuesta = cliente.post(destino['url'],
            json={'accion': 'entregaServidor', 'payload': payload, 'firma': firma})
        respuesta.raise_for_status()
        r = respuesta.json()
    if not r.get('exito'):
        if r.get('revision'):
            raise RevisionEntrega('Google requiere revisar el correo antes de reintentar')
        raise RuntimeError('Google no confirmo la entrega; revisa el despliegue, permisos y cuota')
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
        cambio = db.execute(update(AppEntrega).where(AppEntrega.id == ident, elegible,
            AppEntrega.proximo_en <= ahora).values(estado='PROCESANDO', proximo_en=ahora + timedelta(minutes=15)))
        db.commit()
        if cambio.rowcount != 1:
            return False
        e = db.get(AppEntrega, ident)
        e.intentos += 1
        db.commit()
        try:
            d = e.datos
            guardados = []
            for aid in d['informes'] + d['fotos']:
                a = db.get(AppArchivo, aid)
                if not a:
                    raise RuntimeError('Falta un archivo de la entrega; revisa el almacenamiento')
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
                        'recepcion': e.recepcion, 'usuario': e.usuario, 'tipoArchivo': a.tipo,
                        'nombre': a.nombre, 'tipo': a.mime,
                        'base64': base64.b64encode(archivos.ruta(a).read_bytes()).decode(),
                        'carpetaMes': d['carpetaMes'], 'carpetaRecepcion': d['carpetaRecepcion']})
                    drive_id = str(copia.get('fileId') or '')
                    if not re.fullmatch(r'[a-zA-Z0-9_-]{5,128}', drive_id):
                        raise RuntimeError('Google no confirmo un identificador de archivo valido')
                    a.drive_id, a.drive_url = drive_id, 'https://drive.google.com/file/d/' + drive_id + '/view'
                    db.commit()
                guardados.append(copia)
                # La imagen no ocupa MySQL ni queda duplicada tras confirmar Drive.
                if a.tipo == 'foto':
                    try:
                        archivos.ruta(a).unlink(missing_ok=True)
                    except OSError:
                        log.warning('Entrega %s: foto copiada, limpieza local pendiente', e.id)
            payload = {**d, 'archivos': guardados, 'codigo': e.recepcion, 'usuario': e.usuario}
            if d.get('exportarSheet'):
                referencias = {a.id: a.drive_url for a in db.scalars(select(AppArchivo).where(AppArchivo.recepcion == e.recepcion)) if a.drive_url}
                def enlace_foto(url):
                    ident = str(url).split('/api/app/archivos/')[-1].split('?')[0]
                    return referencias.get(ident, url)
                payload['eventos'] = [{**ev, 'fotos': [enlace_foto(url) for url in ev.get('fotos', [])]} for ev in d['eventos']]
            else:
                for campo in ('skus', 'lineas', 'eventos'):
                    payload.pop(campo, None)
            resultado = llamar('finalizar', e.id, payload)
            e.estado, e.resultado, e.error = 'ENTREGADA', resultado, None
        except RevisionEntrega as exc:
            e.estado, e.error = 'REVISION', str(exc)
        except Exception as exc:
            # No persistir textos HTTP que pueden contener URL firmada o datos secretos.
            e.estado = 'PENDIENTE'
            e.error = str(exc)[:300] if type(exc) is RuntimeError else 'No hubo confirmacion de Google; se reintentara'
            e.proximo_en = utcnow() + timedelta(seconds=min(3600, 30 * 2 ** min(e.intentos, 7)))
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
