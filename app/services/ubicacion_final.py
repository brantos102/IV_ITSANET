"""Asignación posterior de posición: conserva unidades, pallet, autor y fotos."""
import re
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppEvento
from app.services import app_modelo as m, operacion


def asignar(db,codigo,ident,datos,usuario):
    r=m.obtener(db,codigo,bloquear=True)
    if r.estado not in m.ABIERTAS:raise HTTPException(409,'La recepción debe estar abierta para asignar la posición final.')
    e=db.scalar(select(AppEvento).where(AppEvento.id==ident).with_for_update().execution_options(populate_existing=True))
    if not e or e.recepcion!=r.codigo or e.tipo!='CONTEO' or float(e.cantidad or 0)<=0 or not e.pallet:
        raise HTTPException(422,'Selecciona un conteo de esta recepción que tenga pallet y unidades físicas.')
    if db.scalar(select(AppEvento.id).where(AppEvento.recepcion==r.codigo,AppEvento.anula_a==e.id)):
        raise HTTPException(409,'Ese conteo fue anulado. Actualiza antes de asignar su posición.')
    posicion=re.sub(r'\s','',str(datos.get('posicionReal') or '')).upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9._/-]{0,59}',posicion):raise HTTPException(422,'Indica una posición de hasta 60 caracteres: letras, números, punto, guion, barra o guion bajo.')
    if posicion==(e.posicion or ''):return {'eventoId':e.id,'sku':e.sku,'pallet':e.pallet,'posicionReal':posicion,'sinCambios':True}
    if datos.get('posicionAnterior')!=(e.posicion or ''):raise HTTPException(409,'Otra persona cambió esta posición. Actualiza antes de guardar.')
    anterior=e.posicion;e.posicion=posicion
    operacion.auditoria(db,r.codigo,usuario,'POSICION_FINAL_ASIGNADA',{'eventoId':e.id,'sku':e.sku,
        'pallet':e.pallet,'origen':e.origen,'anterior':anterior,'posicionReal':posicion,'unidadesConservadas':float(e.cantidad)})
    db.commit()
    return {'eventoId':e.id,'sku':e.sku,'pallet':e.pallet,'posicionReal':posicion,'sinCambios':False}
