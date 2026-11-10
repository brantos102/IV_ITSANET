"""Reserva compartida y reutilización breve del catálogo, sin bloquear conteos."""
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppConfig, utcnow

CLAVE='catalogo:actualizacion-compartida'


def reservar(db,usuario,alcance='TODOS',ahora=None):
    ahora=ahora or utcnow()
    if db.get_bind().dialect.name=='mysql':
        from sqlalchemy.dialects.mysql import insert
        q=insert(AppConfig).values(clave=CLAVE,datos={});q=q.on_duplicate_key_update(clave=q.inserted.clave)
    else:
        from sqlalchemy.dialects.sqlite import insert
        q=insert(AppConfig).values(clave=CLAVE,datos={}).on_conflict_do_nothing(index_elements=['clave'])
    db.execute(q)
    f=db.scalar(select(AppConfig).where(AppConfig.clave==CLAVE).with_for_update().execution_options(populate_existing=True))
    d=f.datos or {}
    if d.get('hasta','')>ahora.isoformat():
        db.rollback();raise HTTPException(409,'El catálogo ya se está actualizando. Puedes seguir contando; no hace falta repetir la consulta.')
    if d.get('vigenteHasta','')>ahora.isoformat() and d.get('alcanceVigente') in ('TODOS',alcance):
        resultado={**d.get('resultado',{}),'reutilizado':True,'actualizadoEn':d.get('actualizadoEn')};db.rollback();return None,resultado
    token=uuid4().hex;f.datos={**d,'token':token,'alcance':alcance,'hasta':(ahora+timedelta(minutes=15)).isoformat()};f.usuario=usuario;db.commit()
    return token,None


def terminar(db,token,resultado=None,ahora=None):
    db.rollback()
    f=db.scalar(select(AppConfig).where(AppConfig.clave==CLAVE).with_for_update().execution_options(populate_existing=True))
    if not f or f.datos.get('token')!=token:return
    d={**f.datos,'hasta':'','token':''}
    if resultado is not None:
        ahora=ahora or utcnow();d.update(actualizadoEn=ahora.isoformat(),alcanceVigente=d.get('alcance','TODOS'),vigenteHasta=(ahora+timedelta(minutes=15)).isoformat(),
            resultado={k:resultado[k] for k in ('productos','clientes','errores') if k in resultado})
    f.datos=d;db.commit()


def ejecutar(db,usuario,accion,alcance='TODOS'):
    token,previo=reservar(db,usuario,alcance)
    if previo is not None:return previo
    try:
        resultado=accion()
    except BaseException:
        terminar(db,token);raise
    terminar(db,token,resultado if not resultado.get('errores') else None)
    return resultado
