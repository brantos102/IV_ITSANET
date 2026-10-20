"""Cierre declarado desde Recepciones: no envía ni inventa un acuse de Google."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppEvento
from app.services import app_modelo as m, agrupacion_correo as ag, ajustes


def vista(db,codigo):
    try:r=m.obtener(db,codigo)
    except m.ErrorApp as exc:raise HTTPException(404,str(exc)) from None
    f=ag.fuente(db,r.codigo);c=ag.configuracion(db,r.codigo)
    embarques={ag.embarque(l,c) for l in f['lineas'] if ag.embarque(l,c)}
    gs=ag.grupos(f['lineas'],r.origenes or [],{**c,'modo':'EMBARQUE'} if len(embarques)>1 else {'modo':'PACKING_LIST'})
    firma=ag.firma([m.doc_recepcion(r),f])
    return {'codigo':r.codigo,'estado':r.estado,'version':firma,'grupos':gs,'sinVerificar':sum(not s.get('verificado') for s in f['skus']),
        'referencias':len(f['skus'])}


def cerrar(db,codigo,datos,usuario):
    from app.services.entregas import activas
    from app.services.operacion import auditoria
    try:r=m.obtener(db,codigo,bloquear=True)
    except m.ErrorApp as exc:raise HTTPException(404,str(exc)) from None
    solicitud=hashlib.sha256(json.dumps([usuario,datos],sort_keys=True).encode()).hexdigest()
    if r.estado=='CERRADA':
        previo=db.scalar(select(AppEvento).where(AppEvento.recepcion==r.codigo,AppEvento.motivo=='CIERRE_MANUAL_EXTERNO').order_by(AppEvento.creado_en.desc()).limit(1))
        if previo and previo.datos.get('solicitud')==solicitud:return {'recepcion':m.doc_recepcion(r),'mensaje':'Cierre manual ya registrado. No se envió correo desde ITSANET.'}
        raise HTTPException(409,'La recepción ya está cerrada. Actualiza el listado.')
    p=vista(db,codigo)
    if datos.get('version')!=p['version']:raise HTTPException(409,'Cambió la recepción. Revisa nuevamente sus embarques antes de cerrar.')
    if not p['referencias'] or p['sinVerificar']:raise HTTPException(409,'Quedan referencias sin validar. Completa la validación antes de declarar el cierre.')
    confirmaciones=datos.get('confirmaciones',{})
    if not isinstance(confirmaciones,dict) or set(confirmaciones)!={g['id'] for g in p['grupos']} or any(not isinstance(v,dict) or v.get('correo') is not True or v.get('validacion') is not True for v in confirmaciones.values()):
        raise HTTPException(422,'Confirma para cada embarque que el correo fue enviado y que se incluyeron su recepción y validación.')
    motivo=str(datos.get('motivo') or '').strip()
    if not 10<=len(motivo)<=300:raise HTTPException(422,'Indica cómo y cuándo se enviaron los correos (10–300 caracteres).')
    pendientes=activas(db,r.codigo)
    if any(e.estado=='PROCESANDO' for e in pendientes):raise HTTPException(409,'Hay un correo procesándose. Espera su resultado antes de declarar otro envío.')
    for e in pendientes:
        e.estado='CANCELADA';e.error=None;e.datos={**e.datos,'cancelacion':{'usuario':usuario,'motivo':'Envío externo confirmado al cerrar desde Recepciones: '+motivo}}
    resultado=m.cerrar_recepcion(db,r.codigo,usuario,confirmar=False)
    auditoria(db,r.codigo,usuario,'CIERRE_MANUAL_EXTERNO',{'solicitud':solicitud,'motivo':motivo,'grupos':p['grupos'],
        'confirmaciones':confirmaciones,'entregasCanceladas':[e.id for e in pendientes],'origen':'RECEPCIONES','acuseGoogle':False})
    db.commit()
    return {'recepcion':resultado,'mensaje':'Recepción cerrada por declaración de envío externo. No se envió correo desde ITSANET.'}
