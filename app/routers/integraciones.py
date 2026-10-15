"""Administracion local de integraciones. Todos los cambios exigen ADMIN."""
import httpx
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
            'puentes': svc.puentes_publicos(db),
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
    except depot.DepotRechazado:
        raise HTTPException(502, 'gettoken: Depot rechazo la autenticacion. El servidor envia userid y password, como Clientes.gs. Revisa la cuenta y URL de este cliente.') from None
    except depot.DepotNoDisponible as exc:
        causa = exc.__cause__
        if exc.codigo_http:
            raise HTTPException(502, f'gettoken: HTTP {exc.codigo_http}. Revisa la URL raiz y la ruta del endpoint; no se siguen redirecciones hacia otro origen.') from None
        motivo = 'Tiempo de espera agotado' if isinstance(causa, httpx.TimeoutException) else 'No hubo respuesta HTTP valida'
        raise HTTPException(502, 'gettoken: ' + motivo + '. Comprueba DNS, HTTPS y salida de red desde el servidor empresarial.') from None
    try:
        filas = api.stock()
        return {'ok': True, 'pasos': ['gettoken', 'getstock'], 'productos': len({f['sku'] for f in filas}),
                'filas': len(filas), 'clientes': sorted({f['cliente'] for f in filas if f.get('cliente')}),
                'mensaje': f'Autenticacion y lectura de stock correctas: {len(filas)} filas. Sincroniza el catalogo para usarlas en el escaneo.'}
    except (depot.DepotNoDisponible, depot.DepotRechazado):
        raise HTTPException(502, 'gettoken correcto; getstock fallo. Las credenciales autentican, pero Depot no confirmo una respuesta de inventario valida.') from None


@router.put('/google')
def guardar_google(datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(admin)):
    return svc.guardar_google(db, datos, op.usuario)


@router.post('/google/probar')
def probar_google(datos: dict = Body(...), db: Session = Depends(get_db), _: Operador = Depends(admin)):
    from app.services import entregas
    from uuid import uuid4
    supervisor = str(datos.get('supervisor') or '').strip().lower()
    if not supervisor:
        raise HTTPException(422, 'Indica el correo del supervisor responsable')
    try:
        r = entregas.llamar('estado', uuid4().hex, {'usuario': supervisor})
        if str(r.get('remitente') or '').lower() != supervisor:
            raise HTTPException(409, 'El despliegue no pertenece a este supervisor')
        return {'ok': True, 'remitente': supervisor, 'mensaje': 'Remitente y acceso a la carpeta Drive verificados. No se envio correo.'}
    except (RuntimeError, httpx.HTTPError):
        raise HTTPException(502, 'No se pudo verificar el puente. Revisa despliegue, cuenta ejecutora, carpeta y clave compartida.') from None


@router.put('/oauth-google')
def guardar_oauth(datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(admin)):
    return svc.guardar_oauth(db, datos, op.usuario)
