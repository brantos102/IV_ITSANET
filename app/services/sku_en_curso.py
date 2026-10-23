"""Presencia temporal por SKU; no reserva cantidades ni modifica conteos."""
import hashlib
import re
import time
from sqlalchemy import select
from fastapi import HTTPException
from app.models import AppConfig, Operador
from app.services import app_modelo as m

VIGENCIA=90


def actualizar(db,codigo,op,sesion,datos):
    r=m.obtener(db,codigo,bloquear=True)
    dispositivo=str(datos.get('dispositivo',''));sku=str(datos.get('sku') or '').strip().upper()
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',dispositivo):raise HTTPException(422,'Dispositivo inválido.')
    if len(sku)>80 or any(ord(c)<32 for c in sku):raise HTTPException(422,'SKU inválido.')
    actividad=datos.get('actividad','REVISANDO')
    if actividad not in ('CONTANDO','REVISANDO'):raise HTTPException(422,'Actividad inválida.')
    prefijo='sku:'+hashlib.sha256(r.codigo.encode()).hexdigest()[:12]+':'
    clave=prefijo+hashlib.sha256((dispositivo+sesion).encode()).hexdigest()[:20]
    ahora=time.time();filas=list(db.scalars(select(AppConfig).where(AppConfig.clave.like(prefijo+'%'))))
    otros=[]
    for f in filas:
        if f.datos.get('vence',0)<=ahora:
            if f.clave!=clave:db.delete(f)
            continue
        if f.clave==clave or not sku or f.datos.get('sku')!=sku:continue
        persona=db.get(Operador,f.datos.get('operadorId'))
        if persona and persona.activo:
            otros.append({'nombre':persona.nombre,'actividad':f.datos.get('actividad','REVISANDO'),
                'mismoUsuario':persona.id==op.id,'venceEn':max(0,int(f.datos['vence']-ahora))})
    propia=db.get(AppConfig,clave)
    if sku:
        propia=propia or AppConfig(clave=clave)
        propia.usuario=op.usuario;propia.datos={'dispositivo':dispositivo,'recepcion':r.codigo,'operadorId':op.id,'sku':sku,'actividad':actividad,'vence':ahora+VIGENCIA}
        db.add(propia)
    elif propia:db.delete(propia)
    db.commit()
    return {'sku':sku,'otros':otros,'vigenciaSegundos':VIGENCIA,'compartido':bool(otros),'operadorId':op.id}
