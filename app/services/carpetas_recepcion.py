"""Carpetas bajo demanda: registrar una recepción no crea directorios vacíos."""
import hashlib
from sqlalchemy import select
from app.models import AppConfig


def clave(codigo):return 'drive:r:'+hashlib.sha256(codigo.encode()).hexdigest()[:30]


def encolar(db,codigo):
    from app.services.fotos_embarques import informacion
    from app.services.enlaces_correo import base_embarque,raiz
    embarques=[base_embarque(e)[0] for e in informacion(db,codigo)[3]]
    f=db.get(AppConfig,clave(codigo)) or AppConfig(clave=clave(codigo))
    carpeta=(f.datos or {}).get('carpeta','') or raiz(db,codigo)
    f.datos={'recepcion':codigo,'embarques':embarques,'estado':'LISTA' if carpeta else 'BAJO_DEMANDA',
        'carpeta':carpeta,'proximo':0}
    db.add(f)


def procesar_uno(db):
    """Retirar preparaciones antiguas; las colas de archivos conservan sus reintentos.

    No llamar al preparador de un puente antiguo que crea todas las categorías.
    """
    candidatas=list(db.scalars(select(AppConfig).where(AppConfig.clave.like('drive:r:%'))))
    f=next((f for f in candidatas if f.datos.get('estado') not in ('LISTA','BAJO_DEMANDA')),None)
    if not f:return False
    f=db.scalar(select(AppConfig).where(AppConfig.clave==f.clave).with_for_update().execution_options(populate_existing=True))
    if f.datos.get('estado') in ('LISTA','BAJO_DEMANDA'):return True
    encolar(db,f.datos['recepcion']);db.commit();return True


def trabajar():
    from app.db import SessionLocal
    with SessionLocal() as db:return procesar_uno(db)
