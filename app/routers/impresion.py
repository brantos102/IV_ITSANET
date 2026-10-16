"""Cola ZPL por estación. El agente solo obtiene trabajos de su propio token."""
from datetime import timedelta
import hashlib
import hmac
import re
import secrets
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppConfig, AppImpresion, Operador, utcnow
from app.routers.operacion import admin
from app.security import usuario_actual
from app.services import app_modelo as m, operacion

router = APIRouter(prefix='/api/impresion', tags=['impresion'])


def estacion(db, ident):
    c = db.get(AppConfig, 'operacion')
    p = next((p for p in (c.datos.get('impresoras', []) if c else []) if p['id'] == ident), None)
    if not p: raise HTTPException(404, 'Estación no encontrada')
    return p


def autenticar(db, ident, authorization):
    p = estacion(db, ident)
    token = (authorization or '').removeprefix('Bearer ')
    if not p.get('tokenHash') or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), p['tokenHash']):
        raise HTTPException(401, 'Agente no autorizado')
    return p


def zpl(datos, copias):
    sku = str(datos.get('sku') or '')
    if not re.fullmatch(r'[!-~]{1,42}', sku): raise HTTPException(422, 'SKU de etiqueta inválido')
    if datos.get('serie') and not re.fullmatch(r'[!-~]{1,42}', str(datos['serie'])):
        raise HTTPException(422, 'Serie de etiqueta inválida')
    def texto(x, y, h, ancho, valor, lineas=1):
        codificado = ''.join('\\' + format(b, '02X') for b in str(valor).encode())
        return f'^FO{x},{y}^A0N,{h},{max(12,h-3)}^FB{ancho},{lineas},2,L,0^FH\\^FD{codificado}^FS'
    codigo = ''.join('\\' + format(b, '02X') for b in sku.encode())
    return '\n'.join(['^XA', '^CI28', '^PW800', '^LL400', '^LH0,0',
        texto(22,22,34,480,str(datos.get('cliente') or 'ITSANET').upper()[:40]),
        texto(22,68,19,480,'CODIGO:'),
        f'^FO36,101^BY{1 if len(sku)>20 else 2},2,70^BCN,70,N,N,N,A^FH\\^FD{codigo}^FS',
        texto(70,180,24,440,sku), texto(22,216,18,480,'DESCRIPCION:'),
        texto(22,241,20,480,str(datos.get('descripcion') or '')[:100],2),
        texto(22,300,19,480,'SERIE:'),
        *([f'^FO36,326^BY{1 if len(str(datos["serie"])) > 20 else 2},2,32^BCN,32,N,N,N,A^FH\\^FD' + ''.join('\\' + format(b, '02X') for b in str(datos['serie'])[:42].encode()) + '^FS',
           texto(22,367,18,480,str(datos['serie'])[:42])] if datos.get('serie') else []),
        texto(534,27,28,245,'CUARENTENA' if datos.get('estado') == 'PNC' else str(datos.get('categoria') or 'DISPONIBLE')[:18]),
        texto(534,62,17,245,str(datos.get('despacho') or '')[:28]),
        texto(532,139,23,112,'QTY'),texto(662,139,23,120,'ESTADO'),
        texto(538,185,38,100,'1'),texto(605,226,17,40,str(datos.get('unidad') or 'CS')[:5]),
        texto(667,194,29,110,str(datos.get('estado') or 'NUV')[:15]),
        texto(533,280,23,245,'RESPONSABLE'),texto(534,318,20,245,str(datos.get('responsable') or '')[:48],2),
        f'^PQ{copias}', '^XZ'])


@router.post('/estaciones/{ident}/token')
def token_agente(ident: str, db: Session = Depends(get_db), _: Operador = Depends(admin)):
    estacion(db, ident)
    token = secrets.token_urlsafe(40)
    c = db.get(AppConfig, 'operacion')
    d = dict(c.datos)
    d['impresoras'] = [{**p, 'tokenHash': hashlib.sha256(token.encode()).hexdigest()} if p['id'] == ident else p
                      for p in d['impresoras']]
    c.datos = d; db.commit()
    return {'estacion': ident, 'token': token}


@router.post('/trabajos', status_code=201)
def solicitar(datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(usuario_actual)):
    p = estacion(db, datos.get('estacion'))
    if not p.get('activo', True) or not p.get('tokenHash'): raise HTTPException(409, 'Estación no habilitada')
    copias = datos.get('copias', 1)
    if type(copias) is not int or not 1 <= copias <= operacion.configuracion(db)['maxCopias']:
        raise HTTPException(422, 'Número de copias fuera del rango configurado')
    clave = str(datos.get('clave') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,80}', clave): raise HTTPException(422, 'Falta identificador de solicitud')
    previo = db.scalar(select(AppImpresion).where(AppImpresion.clave == clave))
    if previo:
        if previo.usuario != (op.email or op.usuario): raise HTTPException(409, 'Solicitud de otro usuario')
        return {'id': previo.id, 'estado': previo.estado}
    etiqueta = datos.get('etiqueta') or {}
    codigo = datos.get('recepcion')
    if codigo:
        try: m.obtener(db, codigo)
        except m.ErrorApp as exc: raise HTTPException(404, str(exc)) from None
    j = AppImpresion(id=uuid4().hex, clave=clave, estacion=p['id'], recepcion=codigo,
        usuario=op.email or op.usuario, datos={'zpl': zpl(etiqueta, copias), 'sku': str(etiqueta.get('sku')),
        'copias': copias, 'cantidadPorEtiqueta': 1})
    db.add(j)
    if codigo: operacion.auditoria(db, codigo, j.usuario, 'ETIQUETA_SOLICITADA', {'trabajoId': j.id, 'sku': etiqueta.get('sku'), 'copias': copias})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previo = db.scalar(select(AppImpresion).where(AppImpresion.clave == clave))
        if not previo or previo.usuario != (op.email or op.usuario):
            raise HTTPException(409, 'Solicitud de impresión en conflicto') from None
        return {'id': previo.id, 'estado': previo.estado}
    return {'id': j.id, 'estado': j.estado}


@router.get('/trabajos/{ident}')
def trabajo(ident: str, db: Session = Depends(get_db), op: Operador = Depends(usuario_actual)):
    j = db.get(AppImpresion, ident)
    if not j: raise HTTPException(404, 'Solicitud no encontrada')
    if op.rol.value == 'OPERADOR' and j.usuario != (op.email or op.usuario): raise HTTPException(403, 'Solicitud de otro usuario')
    return {'id': j.id, 'estado': j.estado, 'sku': j.datos['sku'], 'copias': j.datos['copias']}


@router.post('/agente/{ident}/siguiente')
def siguiente(ident: str, datos: dict = Body(default={}), authorization: str | None = Header(None), db: Session = Depends(get_db)):
    p = autenticar(db, ident, authorization)
    if not p.get('activo', True): return {'trabajo': None}
    if p.get('equipo') and str(datos.get('equipo') or '').lower() != p['equipo'].lower():
        raise HTTPException(403, 'Este token pertenece a otra computadora puente')
    ahora = utcnow()
    # Un trabajo reservado de resultado desconocido nunca se reenvía automáticamente.
    db.execute(update(AppImpresion).where(AppImpresion.estacion == ident,
        AppImpresion.estado == 'RESERVADA', AppImpresion.reservado_en < ahora - timedelta(minutes=5))
        .values(estado='REVISION', actualizado_en=ahora))
    db.commit()
    jid = db.scalar(select(AppImpresion.id).where(AppImpresion.estacion == ident,
        AppImpresion.estado == 'PENDIENTE').order_by(AppImpresion.creado_en).limit(1))
    if not jid: return {'trabajo': None}
    reserva = secrets.token_hex(24)
    r = db.execute(update(AppImpresion).where(AppImpresion.id == jid, AppImpresion.estado == 'PENDIENTE')
        .values(estado='RESERVADA', reserva=reserva, reservado_en=ahora, actualizado_en=ahora))
    db.commit()
    if r.rowcount != 1: return {'trabajo': None}
    j = db.get(AppImpresion, jid)
    return {'trabajo': {'id': j.id, 'reserva': reserva, 'zpl': j.datos['zpl'],
        'host': p['host'], 'puerto': p.get('puerto', 9100)}}


@router.post('/agente/{ident}/confirmar')
def confirmar(ident: str, datos: dict = Body(...), authorization: str | None = Header(None), db: Session = Depends(get_db)):
    autenticar(db, ident, authorization)
    j = db.scalar(select(AppImpresion).where(AppImpresion.id == datos.get('id')).with_for_update())
    if not j or j.estacion != ident or not j.reserva or not hmac.compare_digest(j.reserva, str(datos.get('reserva') or '')):
        raise HTTPException(409, 'Reserva no válida')
    estado = datos.get('estado')
    if estado not in ('ENVIADA', 'REVISION'): raise HTTPException(422, 'Resultado inválido')
    if j.estado not in ('ENVIADA', 'REVISION'):
        j.estado, j.actualizado_en = estado, utcnow()
        db.commit()
    return {'estado': j.estado}
