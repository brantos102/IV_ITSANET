"""Administracion local de integraciones. Todos los cambios exigen ADMIN."""
import logging
import traceback
from uuid import uuid4

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Operador, Rol
from app.security import usuario_actual
from app.services import integraciones as svc, depot

router = APIRouter(prefix='/api/app/integraciones', tags=['integraciones'])
log = logging.getLogger('iv_itsanet.integraciones')


def _fallo_interno(exc, paso):
    """Correlacionar fallos sin registrar secretos, cuerpos ni mensajes HTTP."""
    referencia = uuid4().hex[:12]
    ubicaciones = ' > '.join(f'{f.filename.rsplit("/", 1)[-1]}:{f.lineno}:{f.name}'
                             for f in traceback.extract_tb(exc.__traceback__))
    log.error('Depot ref=%s paso=%s tipo=%s ubicacion=%s',
              referencia, paso, type(exc).__name__, ubicaciones)
    raise HTTPException(500, {'codigo': 'DEPOT_INTERNO',
        'mensaje': f'Depot: fallo interno en {paso}. Referencia {referencia}. ADMIN puede localizar esta referencia en el registro del servicio.'}) from None


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
    try:
        api = depot.DepotAPI.desde_db(db, ident.upper())
    except HTTPException:
        raise
    except Exception as exc:
        _fallo_interno(exc, 'configuracion')
    if api is None:
        raise HTTPException(404, 'Cliente no configurado o desactivado')
    try:
        api.token(forzar=True)
    except depot.DepotRechazado:
        raise HTTPException(502, 'gettoken: Depot rechazo la autenticacion. El servidor envia userid y password, como Clientes.gs. Revisa la cuenta y URL de este cliente.') from None
    except depot.DepotNoDisponible as exc:
        causa = exc.__cause__
        if exc.motivo == 'RESPUESTA_TOKEN':
            raise HTTPException(502, 'gettoken: Depot respondio, pero no entrego un token valido. Revisa la URL raiz; una pagina HTML no es una respuesta de autenticacion.') from None
        if exc.codigo_http:
            raise HTTPException(502, f'gettoken: HTTP {exc.codigo_http}. Revisa la URL raiz y la ruta del endpoint; no se siguen redirecciones hacia otro origen.') from None
        motivo = 'Tiempo de espera agotado' if isinstance(causa, httpx.TimeoutException) else 'No hubo respuesta HTTP valida'
        raise HTTPException(502, 'gettoken: ' + motivo + '. Comprueba DNS, HTTPS y salida de red desde el servidor empresarial.') from None
    except Exception as exc:
        _fallo_interno(exc, 'gettoken')
    try:
        filas = api.stock()
        return {'ok': True, 'pasos': ['gettoken', 'getstock'], 'productos': len({f['sku'] for f in filas}),
                'filas': len(filas), 'clientes': sorted({f['cliente'] for f in filas if f.get('cliente')}),
                'mensaje': f'Autenticacion y lectura de stock correctas: {len(filas)} filas. Sincroniza el catalogo para usarlas en el escaneo.'}
    except (depot.DepotNoDisponible, depot.DepotRechazado):
        raise HTTPException(502, 'gettoken correcto; getstock fallo. Las credenciales autentican, pero Depot no confirmo una respuesta de inventario valida.') from None
    except Exception as exc:
        _fallo_interno(exc, 'getstock')


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
        return {'ok': True, 'remitente': supervisor, 'carpeta': r.get('carpeta', ''), 'nombreCarpeta': r.get('nombreCarpeta', ''),
                'mensaje': 'Remitente y acceso a la carpeta Drive verificados. No se envio correo.'}
    except (RuntimeError, httpx.HTTPError):
        raise HTTPException(502, 'No se pudo verificar el puente. Revisa despliegue, cuenta ejecutora, carpeta y clave compartida.') from None


@router.put('/oauth-google')
def guardar_oauth(datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(admin)):
    return svc.guardar_oauth(db, datos, op.usuario)
