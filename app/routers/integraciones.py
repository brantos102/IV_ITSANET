"""Administracion local de integraciones. Todos los cambios exigen ADMIN."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Operador, Rol
from app.security import usuario_actual
from app.services import integraciones as svc, depot

router = APIRouter(prefix='/api/app/integraciones', tags=['integraciones'])


def admin(op: Operador = Depends(usuario_actual)):
    if op.rol != Rol.ADMIN:
        raise HTTPException(403, 'Solo ADMIN puede consultar o modificar credenciales')
    return op


@router.get('')
def estado(db: Session = Depends(get_db), _: Operador = Depends(admin)):
    g = svc.google(db)
    oauth = svc.oauth(db)
    return {'clientes': svc.lista_publica(db), 'google': {'url': g['url'], 'secretoConfigurado': bool(g['secreto'])},
            'oauth': {k: oauth.get(k) for k in ('clientId', 'redirectUri', 'activo')} | {'secretoConfigurado': bool(oauth.get('clientSecret'))},
            'depotEntornoConfigurado': depot.DepotAPI().configurada}


@router.put('/depot/{ident}')
def guardar(ident: str, datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(admin)):
    return svc.guardar_cliente(db, ident, datos, op.usuario)


@router.post('/depot/{ident}/probar')
def probar(ident: str, db: Session = Depends(get_db), _: Operador = Depends(admin)):
    api = depot.DepotAPI.desde_db(db, ident.upper())
    if api is None:
        raise HTTPException(404, 'Cliente no configurado o desactivado')
    try:
        api.token(forzar=True)
        return {'ok': True, 'mensaje': 'Conexion y autenticacion correctas'}
    except (depot.DepotNoDisponible, depot.DepotRechazado):
        raise HTTPException(502, 'Depot no confirmo la conexion. Revisa URL, credenciales y conectividad del servidor.') from None


@router.put('/google')
def guardar_google(datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(admin)):
    return svc.guardar_google(db, datos, op.usuario)


@router.put('/oauth-google')
def guardar_oauth(datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(admin)):
    return svc.guardar_oauth(db, datos, op.usuario)
