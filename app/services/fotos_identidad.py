"""Nombres trazables; asignar secuencias solo bajo el bloqueo de recepción."""
from datetime import timezone
import hashlib
import re
import unicodedata
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models import AppArchivo, AppArchivoIdentidad, AppRecepcion, AppUnidadLogistica


def componente(valor, limite=60):
    texto=unicodedata.normalize('NFKD',str(valor)).encode('ascii','ignore').decode()
    texto=re.sub(r'[^A-Za-z0-9._-]+','-',texto).strip('.-_') or 'SIN-DATO'
    if len(texto)>limite:
        texto=texto[:limite-9]+'-'+hashlib.sha256(texto.encode()).hexdigest()[:8]
    return texto


def embarques(recepcion):
    return sorted(set(str(e).strip() for e in (recepcion.embarques or []) if str(e).strip()))


def parte_embarques(recepcion):
    return componente('+'.join(embarques(recepcion)) or 'SIN-EMBARQUE',70)


def nombre(db, archivo, identidad=None):
    identidad=identidad or db.get(AppArchivoIdentidad,archivo.id)
    if not identidad:return archivo.nombre
    r=db.get(AppRecepcion,archivo.recepcion)
    fecha=archivo.creado_en
    if fecha.tzinfo is None:fecha=fecha.replace(tzinfo=timezone.utc)
    fecha=fecha.astimezone(ZoneInfo('America/Guayaquil')).strftime('%Y%m%d')
    extension='.png' if archivo.mime=='image/png' else '.webp' if archivo.mime=='image/webp' else '.jpg'
    return f'{componente(r.codigo)}_{parte_embarques(r)}_{fecha}_{identidad.secuencia:05d}{extension}'


def asegurar_recepcion(db,codigo):
    """Incluye fotos retiradas: un número ya asignado nunca se reutiliza."""
    existentes={x.archivo_id:x for x in db.scalars(select(AppArchivoIdentidad).where(AppArchivoIdentidad.recepcion==codigo)
        .order_by(AppArchivoIdentidad.archivo_id).with_for_update().execution_options(populate_existing=True))}
    secuencia=max((x.secuencia for x in existentes.values()),default=0)
    fotos=list(db.scalars(select(AppArchivo).where(AppArchivo.recepcion==codigo,AppArchivo.tipo=='foto').order_by(AppArchivo.creado_en,AppArchivo.id)
        .with_for_update().execution_options(populate_existing=True)))
    for a in fotos:
        if a.id not in existentes:
            secuencia+=1
            identidad=AppArchivoIdentidad(archivo_id=a.id,recepcion=codigo,secuencia=secuencia,nombre_original=a.nombre,datos={})
            db.add(identidad);existentes[a.id]=identidad
        actualizar_nombre(db,a,existentes[a.id])
    db.flush()
    return existentes


def actualizar_nombre(db,a,identidad):
    nuevo=nombre(db,a,identidad)
    historial=list((identidad.datos or {}).get('nombresAnteriores',[]))
    if a.nombre!=nuevo and a.nombre not in historial:historial.append(a.nombre)
    datos={**(identidad.datos or {}),'nomenclaturaVersion':2,
        'embarques':embarques(db.get(AppRecepcion,a.recepcion)),'nombreActual':nuevo,'nombresAnteriores':historial}
    if datos!=identidad.datos:identidad.datos=datos
    a.nombre=nuevo


def asegurar_archivo(db,a):
    """El bloqueo de recepción serializa; las lecturas actuales evitan snapshots viejos."""
    identidad=db.scalar(select(AppArchivoIdentidad).where(AppArchivoIdentidad.archivo_id==a.id)
        .with_for_update().execution_options(populate_existing=True))
    if not identidad:
        ultimo=db.scalar(select(AppArchivoIdentidad).where(AppArchivoIdentidad.recepcion==a.recepcion)
            .order_by(AppArchivoIdentidad.secuencia.desc()).limit(1).with_for_update().execution_options(populate_existing=True))
        if not ultimo:return asegurar_recepcion(db,a.recepcion)[a.id]
        identidad=AppArchivoIdentidad(archivo_id=a.id,recepcion=a.recepcion,secuencia=ultimo.secuencia+1,nombre_original=a.nombre,datos={})
        db.add(identidad)
    actualizar_nombre(db,a,identidad);db.flush()
    return identidad


def ruta_bulto(db,e):
    if not e or not e.unidad_id:return []
    u=db.get(AppUnidadLogistica,e.unidad_id)
    if not u or u.recepcion!=e.recepcion:return []
    b=db.get(AppUnidadLogistica,u.padre_id) if u.padre_id else u
    if not b:return []
    r=db.get(AppRecepcion,e.recepcion)
    ruta=['BULTOS',f'Bulto{b.numero:02d}_{componente(r.codigo)}_{parte_embarques(r)}']
    if u.padre_id:ruta.append(f'Caja{u.numero:02d}_{componente(u.codigo or "SIN-CODIGO",60)}')
    return ruta
