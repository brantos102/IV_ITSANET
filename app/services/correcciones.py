"""Sustituir un evento con compensación y nuevo conteo en una transacción."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppEvento, AppSku
from app.services import app_modelo as m, ajustes
import math


def corregir(db, codigo, ident, datos, usuario):
    r = m.obtener(db, codigo, bloquear=True)
    if r.estado not in m.ABIERTAS:
        raise HTTPException(409, 'Reabre la recepción antes de corregir el conteo.')
    nuevo_id = str(datos.get('id') or '')
    if not 8 <= len(nuevo_id) <= 80:
        raise HTTPException(422, 'Falta el identificador de corrección.')
    repetido = db.get(AppEvento, nuevo_id)
    if repetido:
        if repetido.recepcion != r.codigo or (repetido.datos or {}).get('corrigeA') != ident:
            raise HTTPException(409, 'El identificador corresponde a otra operación.')
        return {'duplicado': True, 'eventoId': nuevo_id, 'anulado': ident}
    e = db.scalar(select(AppEvento).where(AppEvento.id == ident).with_for_update())
    if not e or e.recepcion != r.codigo or e.tipo not in ('CONTEO', 'NO_ENCONTRADO'):
        raise HTTPException(422, 'Selecciona un conteo físico de esta recepción.')
    s = db.scalar(select(AppSku).where(AppSku.recepcion == r.codigo, AppSku.sku == e.sku).with_for_update().execution_options(populate_existing=True))
    if datos.get('contadoEsperado') != s.contado:
        raise HTTPException(409, 'Otro usuario cambió este SKU. Actualiza antes de corregir.')
    motivo = str(datos.get('motivo') or '').strip()
    if len(motivo) < 3:
        raise HTTPException(422, 'Explica el motivo de la corrección.')
    original = dict(e.datos or {})
    for q in db.scalars(select(AppEvento).where(AppEvento.recepcion == r.codigo,
            AppEvento.tipo == 'CALIDAD').order_by(AppEvento.creado_en, AppEvento.id)):
        if (q.datos or {}).get('eventoId') == ident:
            original['incidencias'] = q.datos['incidencias']
    p = {**original, 'id': nuevo_id, 'sku': e.sku, 'cantidad': datos.get('cantidad'),
        'pallet': datos.get('pallet', e.pallet), 'origen': datos.get('origen', e.origen),
        'posicionReal': datos.get('posicionReal', e.posicion),
        'observacion': datos.get('observacion', original.get('observacion')),
        'incidencias': datos.get('incidencias', original.get('incidencias', [])),
        'confirmarSobrante': datos.get('confirmarSobrante') is True}
    m.anular_conteo(db, r.codigo, usuario, ident, motivo, confirmar=False)
    resultado = m.registrar_conteo(db, r.codigo, usuario, p, confirmar=False)
    nuevo = db.get(AppEvento, nuevo_id)
    nuevo.datos = {**nuevo.datos, 'corrigeA': ident}
    ajustes.auditar(db, usuario, 'CONTEO_CORREGIDO', r.codigo, {'anterior': ident, 'nuevo': nuevo_id, 'motivo': motivo})
    db.commit()
    return resultado


def repartir(db,codigo,datos,usuario):
    r=m.obtener(db,codigo,bloquear=True)
    ident=str(datos.get('idempotencyKey') or datos.get('id') or '')
    if not 8<=len(ident)<=80:raise HTTPException(422,'Falta el identificador del reparto.')
    previo=db.get(AppEvento,ident)
    if previo:
        if previo.recepcion!=r.codigo or previo.tipo!='REPARTO' or previo.sku!=datos.get('sku'):
            raise HTTPException(409,'El identificador corresponde a otra operación.')
        return {**previo.datos['resultado'],'duplicado':True}
    partes=datos.get('reparto')
    if not isinstance(partes,list) or not 1<=len(partes)<=30:raise HTTPException(422,'Revisa el reparto entre packing lists.')
    s=db.scalar(select(AppSku).where(AppSku.recepcion==r.codigo,AppSku.sku==datos.get('sku')).with_for_update().execution_options(populate_existing=True))
    if not s or datos.get('contadoEsperado')!=s.contado:raise HTTPException(409,'El conteo cambió. Actualiza antes de repartir.')
    n=datos.get('cantidad');vistos=set();total=0
    for p in partes:
        if not isinstance(p,dict) or p.get('origen') not in (s.origenes or []) or p['origen'] in vistos:
            raise HTTPException(422,'Cada lista debe pertenecer a este producto y aparecer una sola vez.')
        c=p.get('cantidad')
        if type(c) not in (int,float) or not math.isfinite(c) or c<=0:raise HTTPException(422,'Cantidad inválida por lista.')
        total+=c;vistos.add(p['origen'])
    if type(n) not in (int,float) or not math.isfinite(n) or not math.isclose(total,n,abs_tol=1e-8):
        raise HTTPException(422,'La suma del reparto debe coincidir con la cantidad contada.')
    from app.services import calidad
    incidencias=[dict(i) for i in calidad.validar(db,datos,n)]
    ultimo=None
    for i,p in enumerate(partes):
        libre=p['cantidad'];fs=[]
        for f in incidencias:
            t=min(libre,f['cantidad'])
            if t>0:fs.append({**f,'cantidad':t});f['cantidad']-=t;libre-=t
        ultimo=m.registrar_conteo(db,r.codigo,usuario,{**datos,**p,'idempotencyKey':ident+f'_{i:02d}','incidencias':fs},confirmar=False)
    resultado={**ultimo,'cantidadRegistrada':n,'reparto':partes,'eventoId':ident}
    db.add(AppEvento(id=ident,recepcion=r.codigo,tipo='REPARTO',sku=s.sku,cantidad=0,usuario=usuario,datos={'resultado':resultado}))
    ajustes.auditar(db,usuario,'CONTEO_REPARTIDO',r.codigo,{'eventoId':ident,'reparto':partes});db.commit()
    return resultado
