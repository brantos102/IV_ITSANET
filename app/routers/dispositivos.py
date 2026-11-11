"""Enrolamiento y revocación de equipos. Activación controlada por ADMIN."""
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import AppConfig, AppPresencia, DispositivoUsuario, Operador, Rol, Sesion, SesionDispositivo
from app.security import COOKIE, usuario_actual, verify_pin
from app.services import ajustes, dispositivos as svc

router=APIRouter(prefix='/api/auth/dispositivos',tags=['dispositivos'])


def admin(op=Depends(usuario_actual)):
    if op.rol!=Rol.ADMIN:raise HTTPException(403,'Solo ADMIN administra equipos autorizados.')
    return op


@router.post('/solicitar')
def solicitar(request:Request,response:Response,datos:dict=Body(...),db:Session=Depends(get_db)):
    entrada=str(datos.get('usuario') or '').strip().lower()
    campo=func.lower(Operador.email) if '@' in entrada else func.lower(Operador.usuario)
    candidatos=list(db.scalars(select(Operador).where(campo==entrada).limit(2)))
    op=candidatos[0] if len(candidatos)==1 else None
    pin=datos.get('pin')
    if not op or not isinstance(pin,str) or not 1<=len(pin)<=128 or not verify_pin(pin,op.pin_hash):raise HTTPException(401,'Usuario o contraseña incorrectos.')
    if not op.activo:raise HTTPException(403,'La cuenta está inactiva o pendiente de aprobación.')
    return svc.solicitar(db,op,datos.get('tipo'),datos.get('nombre'),request,response)


@router.get('/mios')
def mios(db:Session=Depends(get_db),op=Depends(usuario_actual)):
    return {'politica':svc.politica(db),'equipos':[svc.ficha(d) for d in db.scalars(
        select(DispositivoUsuario).where(DispositivoUsuario.operador_id==op.id))]}


@router.get('/admin')
def listar(db:Session=Depends(get_db),op=Depends(admin)):
    usuarios={x.id:x for x in db.scalars(select(Operador))}
    equipos=[{**svc.ficha(d),'usuario':usuarios[d.operador_id].usuario,'nombreUsuario':usuarios[d.operador_id].nombre}
        for d in db.scalars(select(DispositivoUsuario).order_by(DispositivoUsuario.creado_en.desc()))]
    return {'politica':svc.politica(db),'equipos':equipos,'usuarioActualId':op.id}


@router.post('/admin/{ident}/aprobar')
def aprobar(ident:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(admin)):
    return svc.aprobar(db,ident,op,datos)


@router.post('/admin/{ident}/revocar')
def revocar(ident:str,request:Request,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(admin)):
    motivo=str(datos.get('motivo') or '').strip()
    if not 5<=len(motivo)<=300:raise HTTPException(422,'Registra el motivo de la revocación, de 5 a 300 caracteres.')
    d=db.get(DispositivoUsuario,ident)
    if not d:raise HTTPException(404,'Equipo no encontrado.')
    db.scalar(select(Operador).where(Operador.id==d.operador_id).with_for_update());db.refresh(d)
    actual=svc.encontrar(db,op.id,request)
    if svc.politica(db)['activo'] and actual and actual.id==d.id:
        raise HTTPException(409,'Entra desde otro equipo autorizado o pide a otro ADMIN que revoque el equipo actual.')
    if d.estado=='REVOCADO':return {'ok':True,'sesionesCerradas':0}
    d.estado='REVOCADO';n=svc.cerrar_sesiones_equipo(db,d.id)
    ajustes.auditar(db,op.usuario,'EQUIPO_REVOCADO',d.operador_id,{'equipoId':d.id,'motivo':motivo,'sesionesCerradas':n})
    db.commit();return {'ok':True,'sesionesCerradas':n}


@router.put('/admin/politica')
def configurar(request:Request,response:Response,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(admin)):
    activo=datos.get('activo')
    if type(activo) is not bool:raise HTTPException(422,'Indica activo como verdadero o falso.')
    anterior=svc.politica(db)['activo']
    token=request.cookies.get(COOKIE) or request.headers.get('Authorization','').removeprefix('Bearer ')
    if activo:
        equipo=svc.encontrar(db,op.id,request)
        if not equipo:raise HTTPException(409,'Registra y aprueba presencialmente el equipo de este ADMIN antes de activar el control.')
        if not db.get(SesionDispositivo,token):db.add(SesionDispositivo(sesion_token=token,dispositivo_id=equipo.id))
        svc.promover_cookie(db,op,response,request)
    elif anterior:
        if len(str(datos.get('motivo') or '').strip())<5:raise HTTPException(422,'Registra el motivo para desactivar el control.')
        # No reactivar sesiones antiguas que estaban bloqueadas por el control.
        db.query(Sesion).filter(Sesion.token!=token).delete(synchronize_session=False)
        db.query(AppPresencia).delete(synchronize_session=False)
    f=db.get(AppConfig,svc.CLAVE) or AppConfig(clave=svc.CLAVE)
    f.datos={'activo':activo};f.usuario=op.usuario;db.add(f)
    ajustes.auditar(db,op.usuario,'POLITICA_EQUIPOS',op.id,{'activo':activo,'anterior':anterior,'motivo':str(datos.get('motivo') or '')[:300]})
    db.commit();return svc.politica(db)
