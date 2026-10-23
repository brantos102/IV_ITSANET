"""Centro de avisos interno por usuario, sin acciones sobre correo o conteos."""
from fastapi import APIRouter, Depends, Body, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.security import usuario_actual
from app.services import avisos_operativos as servicio

router=APIRouter(prefix='/api/operacion/notificaciones',tags=['notificaciones'])

@router.get('')
def listar(recepcion:str='',limite:int=Query(80,ge=1,le=150),catalogo:bool=True,tipo:str='',
    db:Session=Depends(get_db),op=Depends(usuario_actual)):
    return servicio.consultar(db,op,recepcion,limite,catalogo,tipo)

@router.post('/leidas')
def leidas(datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(usuario_actual)):
    return servicio.marcar_leidos(db,op,datos)
