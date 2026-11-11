"""Un móvil y una laptop aprobados; credencial aleatoria HttpOnly por navegador.

No usa IP, nombre declarado ni User-Agent como prueba de identidad del equipo.
El control permanece desactivado hasta el enrolamiento presencial del ADMIN.
"""
import hashlib
import hmac
import os
import secrets
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppConfig, AppPresencia, DispositivoUsuario, Operador, Sesion, SesionDispositivo, utcnow
from app.services import ajustes

CLAVE='seguridad_dispositivos'
TIPOS={'MOVIL','LAPTOP'}


def politica(db):
    f=db.get(AppConfig,CLAVE)
    return {'activo':bool(f and f.datos.get('activo')),'maximoMoviles':1,'maximoLaptops':1,'sesionesActivasPorUsuario':1}


def cookie(opid,pendiente=False):
    return ('iv_equipo_pendiente_' if pendiente else 'iv_equipo_')+str(opid)


def huella(token):return hashlib.sha256(token.encode()).hexdigest()


def ficha(d):
    return {'id':d.id,'operadorId':d.operador_id,'tipo':d.tipo,'nombre':d.nombre,'estado':d.estado,
        'solicitadoEn':d.creado_en.isoformat(),'aprobadoEn':d.aprobado_en.isoformat() if d.aprobado_en else None,
        'aprobadoPor':d.aprobado_por}


def encontrar(db,opid,request,autorizado=True):
    if request is None:return None
    revocado=None
    for pendiente in (False,True):
        token=request.cookies.get(cookie(opid,pendiente),'')
        if not token or len(token)>200:continue
        d=db.scalar(select(DispositivoUsuario).where(DispositivoUsuario.operador_id==opid,
            DispositivoUsuario.token_hash==huella(token)))
        if d and d.estado=='REVOCADO':revocado=d;continue
        if d and (not autorizado or d.estado=='AUTORIZADO'):return d
    return revocado if not autorizado else None


def poner_cookie(response,request,opid,token,pendiente=False):
    response.set_cookie(cookie(opid,pendiente),token,httponly=True,
        secure=request.url.scheme=='https' or os.getenv('VAL_COOKIE_SECURE')=='1',
        samesite='lax',max_age=365*24*3600,path='/')


def promover_cookie(db,op,response,request):
    d=encontrar(db,op.id,request)
    if not d:return
    valor=request.cookies.get(cookie(op.id,True),'')
    if valor and hmac.compare_digest(huella(valor),d.token_hash):
        poner_cookie(response,request,op.id,valor)
        response.delete_cookie(cookie(op.id,True),path='/')


def solicitar(db,op,tipo,nombre,request,response):
    if tipo not in TIPOS or not isinstance(nombre,str) or not 3<=len(nombre.strip())<=100:
        raise HTTPException(422,'Elige Móvil o Laptop y escribe un nombre de equipo de 3 a 100 caracteres.')
    # Todas las aprobaciones y solicitudes del usuario usan el mismo bloqueo.
    db.scalar(select(Operador).where(Operador.id==op.id).with_for_update())
    previo=encontrar(db,op.id,request,autorizado=False)
    if previo and previo.estado=='AUTORIZADO':
        if previo.tipo!=tipo:raise HTTPException(409,'Este navegador ya está registrado con otro tipo de equipo. ADMIN debe revisar el cambio.')
        return {'equipo':ficha(previo),'mensaje':'Este equipo ya está autorizado.'}
    if previo and previo.estado=='PENDIENTE':
        return {'equipo':ficha(previo),'mensaje':'La solicitud ya existe. Espera la aprobación presencial de ADMIN.'}
    pendientes=list(db.scalars(select(DispositivoUsuario).where(DispositivoUsuario.operador_id==op.id,DispositivoUsuario.estado=='PENDIENTE')))
    if len(pendientes)>=4:raise HTTPException(409,'Hay solicitudes pendientes. Pide a ADMIN que las revise antes de registrar otro equipo.')
    token=secrets.token_urlsafe(32)
    d=DispositivoUsuario(id=uuid4().hex,operador_id=op.id,tipo=tipo,nombre=nombre.strip(),token_hash=huella(token))
    db.add(d);db.flush()
    ajustes.auditar(db,op.usuario,'EQUIPO_SOLICITADO',op.id,{'equipoId':d.id,'tipo':tipo,'nombre':d.nombre})
    db.commit();poner_cookie(response,request,op.id,token,pendiente=True)
    return {'equipo':ficha(d),'mensaje':'Solicitud '+d.id[:8].upper()+'. Muestra este equipo a ADMIN para su aprobación presencial.'}


def cerrar_sesiones_equipo(db,ident):
    tokens=list(db.scalars(select(SesionDispositivo.sesion_token).where(SesionDispositivo.dispositivo_id==ident)))
    if tokens:
        hashes=[huella(t) for t in tokens]
        db.query(AppPresencia).filter(AppPresencia.sesion_hash.in_(hashes)).delete(synchronize_session=False)
        db.query(Sesion).filter(Sesion.token.in_(tokens)).delete(synchronize_session=False)
    return len(tokens)


def aprobar(db,ident,autor,datos):
    d=db.get(DispositivoUsuario,ident)
    if not d:raise HTTPException(404,'Solicitud de equipo no encontrada.')
    op=db.scalar(select(Operador).where(Operador.id==d.operador_id).with_for_update())
    db.refresh(d)
    if d.estado=='AUTORIZADO':return ficha(d)
    if d.estado!='PENDIENTE' or not op.activo:raise HTTPException(409,'La solicitud ya no está pendiente o la cuenta está inactiva.')
    if datos.get('presencial') is not True:raise HTTPException(422,'Comprueba presencialmente la identidad, el equipo y el código de solicitud antes de aprobar.')
    actual=db.scalar(select(DispositivoUsuario).where(DispositivoUsuario.operador_id==op.id,
        DispositivoUsuario.tipo==d.tipo,DispositivoUsuario.estado=='AUTORIZADO'))
    if actual:
        if datos.get('reemplaza')!=actual.id:
            raise HTTPException(409,{'codigo':'EQUIPO_YA_REGISTRADO','mensaje':'Ya hay un equipo autorizado de este tipo. Confirma su reemplazo para continuar.','equipoActual':actual.id})
        actual.estado='REVOCADO';cerrar_sesiones_equipo(db,actual.id)
    d.estado='AUTORIZADO';d.aprobado_en=utcnow();d.aprobado_por=autor.email or autor.usuario
    ajustes.auditar(db,autor.usuario,'EQUIPO_APROBADO',op.id,{'equipoId':d.id,'tipo':d.tipo,'reemplazado':actual.id if actual else None})
    db.commit();return ficha(d)


def antes_de_sesion(db,op,request):
    if not politica(db)['activo']:return None
    d=encontrar(db,op.id,request)
    if not d:raise HTTPException(403,{'codigo':'EQUIPO_NO_AUTORIZADO','mensaje':'Este equipo no está autorizado para tu cuenta. Solicita su registro y aprobación presencial a ADMIN.'})
    # Un relevo en el mismo navegador también cierra la sesión anterior,
    # aunque pertenezca a otra persona; no conserva sus canales abiertos.
    anterior=request.cookies.get('val_session') if request else None
    if anterior:
        db.query(AppPresencia).filter(AppPresencia.sesion_hash==huella(anterior)).delete(synchronize_session=False)
        db.query(Sesion).filter(Sesion.token==anterior).delete(synchronize_session=False)
    anteriores=list(db.scalars(select(Sesion.token).where(Sesion.operador_id==op.id)))
    db.query(Sesion).filter(Sesion.operador_id==op.id).delete(synchronize_session=False)
    db.query(AppPresencia).filter(AppPresencia.operador_id==op.id).delete(synchronize_session=False)
    ajustes.auditar(db,op.usuario,'SESION_EN_EQUIPO_AUTORIZADO',op.id,{'equipoId':d.id,'sesionesCerradas':len(anteriores)})
    return d


def sesion_valida(db,op,token,request):
    if not politica(db)['activo']:return True
    enlace=db.get(SesionDispositivo,token)
    if not enlace:return False
    d=encontrar(db,op.id,request)
    return bool(d and d.id==enlace.dispositivo_id)
