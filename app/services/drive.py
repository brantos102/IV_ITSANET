"""Cola durable de imágenes: copia durante la recepción, sin detener el conteo."""
import base64
import hashlib
import logging
import time
from datetime import timedelta
import re
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update

from app.db import SessionLocal
from app.models import AppArchivo, AppCopiaDrive, AppEvidencia, AppUnidadLogistica, utcnow
from app.services import archivos, entregas, operacion
from app.services import app_modelo as m

_verificados = {}


def verificar_puente(db, clave, datos):
    from app.services.integraciones import google
    g = google(db, datos['usuario'])
    k = (g['url'], hashlib.sha256(g['secreto'].encode()).hexdigest(), datos['usuario'], datos.get('carpetaRaiz'))
    if _verificados.get(k, 0) > time.monotonic(): return
    r = entregas.llamar('estado', clave, {'usuario': datos['usuario'], 'carpetaRaiz': datos.get('carpetaRaiz', '')})
    if r.get('versionPuente', 0) < 2:
        raise RuntimeError('Actualiza Servidor.gs y publica su versión con rutas de evidencias')
    if str(r.get('remitente') or '').lower() != datos['usuario'].lower():
        raise RuntimeError('El puente no confirma al supervisor responsable')
    if datos.get('carpetaRaiz') and r.get('carpetaId') != datos['carpetaRaiz']:
        raise RuntimeError('El puente no confirmó el repositorio configurado')
    if len(_verificados) > 128: _verificados.clear()
    _verificados[k] = time.monotonic() + 300


def descripcion(db, archivo, evidencia=None):
    es = list(db.scalars(select(AppEvidencia).where(AppEvidencia.archivo_id == archivo.id,
        AppEvidencia.eliminado_en.is_(None)).order_by(AppEvidencia.creado_en, AppEvidencia.id)))
    e = evidencia or (es[0] if es else None)
    d = operacion.destino_drive(db, archivo.recepcion)
    d['usuario'] = d.pop('supervisor')
    d['ruta'] = [e.categoria if e else 'GENERAL']
    if e and e.unidad_id:
        u = db.get(AppUnidadLogistica, e.unidad_id)
        unidades = [u] if u else []
        if u and u.padre_id: unidades.insert(0, db.get(AppUnidadLogistica, u.padre_id))
        d['ruta'] += [f'{u.tipo}_{u.numero:03d}_{u.codigo}' for u in unidades if u]
    if e and e.origen: d['ruta'].append('LISTA_' + e.origen)
    if e and e.sku: d['ruta'].append(e.sku)
    d['sku'] = e.sku if e else ''
    if e: d['ruta'].append(e.tipo)
    d.update(tipoArchivo=archivo.tipo, nombre=archivo.nombre, tipo=archivo.mime,
        recepcion=archivo.recepcion, evidencia=e.id if e else None)
    return d


def encolar(db, archivo):
    j = db.get(AppCopiaDrive, archivo.id)
    if not j:
        d = descripcion(db, archivo)
        j = AppCopiaDrive(archivo_id=archivo.id, recepcion=archivo.recepcion,
            usuario=d['usuario'], estado='PENDIENTE', datos=d)
        db.add(j)
    return j


def procesar_uno():
    ahora = utcnow()
    with SessionLocal() as db:
        elegible = or_(AppCopiaDrive.estado == 'PENDIENTE', AppCopiaDrive.estado == 'PROCESANDO')
        aid = db.scalar(select(AppCopiaDrive.archivo_id).where(elegible, AppCopiaDrive.proximo_en <= ahora)
                        .order_by(AppCopiaDrive.proximo_en).limit(1))
        if not aid: return False
        cambio = db.execute(update(AppCopiaDrive).where(AppCopiaDrive.archivo_id == aid,
            elegible, AppCopiaDrive.proximo_en <= ahora).values(estado='PROCESANDO',
            proximo_en=ahora + timedelta(minutes=5)))
        db.commit()
        if cambio.rowcount != 1: return False
        j, a = db.get(AppCopiaDrive, aid), db.get(AppArchivo, aid)
        try:
            j.intentos += 1
            # Permite corregir responsable/repositorio desde ADMIN sin editar tareas pendientes.
            if not a.drive_id and j.datos.get('accion') != 'papelera':
                j.datos = descripcion(db, a)
                j.usuario = j.datos['usuario']
            db.commit()
            if not entregas.configurado(db, j.usuario):
                raise RuntimeError('Pendiente de conexión Drive del supervisor responsable')
            d = dict(j.datos)
            verificar_puente(db, aid + ':' + aid, {**d, 'usuario': j.usuario})
            if d.get('accion') == 'papelera':
                if a.drive_id:
                    entregas.llamar('papelera', aid + ':' + aid, {**d, 'usuario': j.usuario, 'fileId': a.drive_id})
                j.estado = 'ELIMINADA'
            else:
                if not a.drive_id:
                    d['base64'] = base64.b64encode(archivos.ruta(a).read_bytes()).decode()
                    r = entregas.llamar('archivo', aid + ':' + aid, d)
                    ident = str(r.get('fileId') or '')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{5,128}', ident):
                        raise RuntimeError('Drive no confirmó el archivo')
                    a.drive_id, a.drive_url = ident, 'https://drive.google.com/file/d/' + ident + '/view'
                    j.datos = {**j.datos, 'carpeta': r.get('carpeta', ''), 'carpetaRecepcionUrl': r.get('carpetaRecepcionUrl', ''),
                        'carpetaSkuUrl': r.get('carpetaSkuUrl', '')}
                j.estado = 'COPIADA'
            j.error = None
            db.commit()
            try: archivos.ruta(a).unlink(missing_ok=True)
            except OSError: logging.getLogger(__name__).warning('Copia Drive confirmada; limpieza local pendiente')
        except Exception as exc:
            db.rollback()
            j = db.get(AppCopiaDrive, aid)
            if not j: return True
            j.estado = 'PENDIENTE'
            j.error = str(exc)[:160] if type(exc) is RuntimeError else 'Copia pendiente; se reintentará sin perder la foto'
            j.proximo_en = utcnow() + timedelta(seconds=min(1800, 15 * 2 ** min(j.intentos, 7)))
            db.commit()
    return True


def eliminar(db, aid, usuario):
    a = db.get(AppArchivo, aid)
    if not a or a.tipo != 'foto': raise HTTPException(404, 'Foto no encontrada')
    r = m.obtener(db, a.recepcion, bloquear=True)
    if r.estado not in m.ABIERTAS: raise HTTPException(409, 'Reabre la recepción para depurar evidencia')
    j = db.scalar(select(AppCopiaDrive).where(AppCopiaDrive.archivo_id == aid).with_for_update())
    if j and j.estado == 'PROCESANDO': raise HTTPException(409, 'La foto se está copiando; vuelve a intentarlo después')
    for e in db.scalars(select(AppEvidencia).where(AppEvidencia.archivo_id == aid, AppEvidencia.eliminado_en.is_(None))):
        e.eliminado_en = utcnow()
    j = j or encolar(db, a)
    j.estado, j.proximo_en = 'PENDIENTE', utcnow()
    j.datos = {**j.datos, 'accion': 'papelera'}
    operacion.auditoria(db, a.recepcion, usuario, 'EVIDENCIA_RETIRADA', {'archivoId': aid, 'driveId': a.drive_id})
    if not a.drive_id:
        j.estado = 'ELIMINADA'
    db.commit()
    if not a.drive_id: archivos.ruta(a).unlink(missing_ok=True)
    return {'eliminada': True, 'papeleraDrivePendiente': j.estado != 'ELIMINADA'}


def manifiesto(db, codigo):
    retiradas = set(db.scalars(select(AppCopiaDrive.archivo_id).where(
        AppCopiaDrive.recepcion == codigo, or_(AppCopiaDrive.estado == 'ELIMINADA',
        AppCopiaDrive.datos['accion'].as_string() == 'papelera'))))
    filas = list(db.scalars(select(AppArchivo).where(AppArchivo.recepcion == codigo,
        AppArchivo.tipo == 'foto').order_by(AppArchivo.creado_en, AppArchivo.id)))
    grupos = {}
    for a in filas:
        if a.id in retiradas: continue
        es = list(db.scalars(select(AppEvidencia).where(AppEvidencia.archivo_id == a.id,
            AppEvidencia.eliminado_en.is_(None)).order_by(AppEvidencia.creado_en, AppEvidencia.id)))
        for e in es or [None]:
            d = descripcion(db, a, e)
            k = tuple(d['ruta'])
            grupo = grupos.setdefault(k, [])
            if not any(previo.id == a.id for previo, _ in grupo): grupo.append((a, d))
    salida = []
    for grupo in grupos.values():
        for i, (a, d) in enumerate(grupo, 1):
            sku = d['ruta'][-2] if len(d['ruta']) > 1 else 'RECEPCION'
            # No usar '/' en el nombre: la galería muestra i/total, el archivo usa _de_.
            nombre = f'{sku}_{i:02d}_de_{len(grupo):02d}' + ('.png' if a.mime == 'image/png' else '.webp' if a.mime == 'image/webp' else '.jpg')
            salida.append({**d, 'archivoId': a.id, 'fileId': a.drive_id,
                'nombreFinal': nombre, 'indice': i, 'total': len(grupo)})
    return salida
