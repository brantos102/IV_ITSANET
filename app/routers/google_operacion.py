"""Autorización propia de APIs Google con OAuth central, PKCE y estado de un uso."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import AppConfig, Operador, Rol
from app.security import requiere_supervisor
from app.services import google_cuentas as svc, integraciones, mi_correo, procesos
from app.routers.google_auth import disponible

router=APIRouter(prefix='/api/auth/google/operacion',tags=['google-operacion'])
COOKIE='iv_google_operacion'


@router.get('/estado')
def estado(db:Session=Depends(get_db),op:Operador=Depends(requiere_supervisor)):
    return svc.estado(db,mi_correo.cuenta(db,op))


@router.get('/iniciar')
def iniciar(request:Request,tipo:str='CORREO',db:Session=Depends(get_db),op:Operador=Depends(requiere_supervisor)):
    email=mi_correo.cuenta(db,op);c=integraciones.oauth(db)
    if tipo not in svc.SCOPES:raise HTTPException(422,'Elige correo o almacenamiento Drive.')
    if tipo=='DRIVE' and op.rol!=Rol.ADMIN:raise HTTPException(403,'ADMIN autoriza la cuenta operativa de Drive.')
    if not disponible(request,c):raise HTTPException(409,'ADMIN debe configurar el cliente OAuth web central y acceder desde su URL HTTPS autorizada.')
    estado='op_'+secrets.token_urlsafe(32);verificador=secrets.token_urlsafe(48)
    reto=base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).decode().rstrip('=')
    clave='go:s:'+hashlib.sha256(estado.encode()).hexdigest()[:32]
    # Una reserva de estado enlaza usuario local, navegador, cliente OAuth y permisos.
    f=AppConfig(clave=clave,usuario=email,datos={'opId':op.id,'correo':email,'tipo':tipo,
        'vence':time.time()+600,'clientId':c['clientId'],'redirectUri':c['redirectUri']})
    db.add(f);db.commit()
    r=RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({
        'client_id':c['clientId'],'redirect_uri':c['redirectUri'],'response_type':'code',
        'scope':' '.join(svc.SCOPES[tipo]),'state':estado,'code_challenge':reto,
        'code_challenge_method':'S256','access_type':'offline','prompt':'consent select_account',
        'include_granted_scopes':'true','login_hint':email}))
    r.set_cookie(COOKIE,integraciones._cifrador().encrypt(json.dumps({'estado':estado,'verificador':verificador}).encode()).decode(),
        httponly=True,secure=c['redirectUri'].startswith('https:'),samesite='lax',max_age=600,path='/api/auth/google')
    return r


def callback(request,db):
    r=RedirectResponse('/app/cuenta.html?googleOperacion=error',status_code=303)
    r.delete_cookie(COOKIE,path='/api/auth/google')
    from app.security import _operador_de_request
    try:
        cookie=json.loads(integraciones._cifrador().decrypt(request.cookies.get(COOKIE,'').encode(),ttl=600))
        if not hmac.compare_digest(cookie['estado'],request.query_params.get('state','')):return r
        clave='go:s:'+hashlib.sha256(cookie['estado'].encode()).hexdigest()[:32]
        f=db.scalar(select(AppConfig).where(AppConfig.clave==clave).with_for_update())
        if not f:return r
        flujo=dict(f.datos);db.delete(f);db.commit()  # Consumir antes de contactar Google.
        op=_operador_de_request(request,db);c=integraciones.oauth(db)
        if not op or not op.activo or op.id!=flujo['opId'] or mi_correo.cuenta(db,op)!=flujo['correo']:return r
        if flujo['vence']<time.time() or c.get('clientId')!=flujo['clientId'] or c.get('redirectUri')!=flujo['redirectUri'] or not disponible(request,c):return r
        if flujo['tipo']=='DRIVE' and op.rol!=Rol.ADMIN:return r
        email=flujo['correo'];usuario=op.usuario;db.rollback()
        with httpx.Client(timeout=20) as http:
            t=http.post('https://oauth2.googleapis.com/token',data={'code':request.query_params.get('code',''),
                'client_id':c['clientId'],'client_secret':c['clientSecret'],'redirect_uri':c['redirectUri'],
                'grant_type':'authorization_code','code_verifier':cookie['verificador']})
            t.raise_for_status();token=t.json()
            u=http.get('https://openidconnect.googleapis.com/v1/userinfo',headers={'Authorization':'Bearer '+token['access_token']})
            u.raise_for_status();perfil=u.json()
        if perfil.get('email_verified') is not True or str(perfil.get('email','')).lower()!=email:
            r.headers['location']='/app/cuenta.html?googleOperacion=cuenta';return r
        if not set(svc.SCOPES[flujo['tipo']]) - {'openid','email'} <= set(token.get('scope','').split()):
            r.headers['location']='/app/cuenta.html?googleOperacion=permisos';return r
        db.expire_all();actual=db.get(Operador,flujo['opId'])
        if not actual or not actual.activo or mi_correo.cuenta(db,actual)!=email:return r
        svc.guardar_tokens(db,email,token,usuario)
        r.headers['location']='/app/cuenta.html?googleOperacion=ok'
    except Exception as exc:
        db.rollback()
        procesos.registrar(db,'GOOGLE','ERROR','oauth-callback',codigo=type(exc).__name__);db.commit()
    return r


@router.delete('/cuenta')
def desconectar(db:Session=Depends(get_db),op:Operador=Depends(requiere_supervisor)):
    email=mi_correo.cuenta(db,op);f=db.get(AppConfig,svc.clave(email))
    if f:db.delete(f)
    procesos.registrar(db,'GOOGLE','DESCONECTADA',email,op.usuario,codigo='DESCONECTADA');db.commit()
    return {'mensaje':'Autorización retirada de ITSANET. Puedes volver a conectarla cuando lo necesites.'}


@router.get('/config')
def config(db:Session=Depends(get_db),op:Operador=Depends(requiere_supervisor)):
    if op.rol!=Rol.ADMIN:raise HTTPException(403,'Solo ADMIN.')
    cuentas=[svc.estado(db,f.datos['correo']) for f in db.scalars(select(AppConfig).where(AppConfig.clave.like('go:%'))) if f.datos.get('correo') and f.datos.get('credencial')]
    return {**svc.configuracion(db),'cuentas':cuentas}


@router.put('/config')
def guardar_config(datos:dict=Body(...),db:Session=Depends(get_db),op:Operador=Depends(requiere_supervisor)):
    if op.rol!=Rol.ADMIN:raise HTTPException(403,'Solo ADMIN.')
    email=str(datos.get('driveCuenta','')).strip().lower()
    if email:
        e=svc.estado(db,email)
        if not e['conectada'] or not e['drive']:raise HTTPException(409,'Primero autoriza Drive con esa cuenta operativa.')
    raiz=str(datos.get('carpetaRaiz','')).strip()
    if raiz:
        from app.services import google_drive_api as drive
        import re
        enlace=re.fullmatch(r'https://drive\.google\.com/(?:drive/(?:u/[0-9]+/)?)?folders/([A-Za-z0-9_-]{5,128})(?:\?[^\s]*)?',raiz)
        if enlace:raiz=enlace[1]
        try:
            drive.validar_id(raiz)
            if not email:raise RuntimeError('Selecciona la cuenta operativa.')
            db.rollback();carpeta=drive.ficha(email,raiz)
            if carpeta.get('trashed') or carpeta.get('mimeType')!=drive.CARPETA:raise RuntimeError('Selecciona una carpeta Drive activa.')
        except RuntimeError as exc:raise HTTPException(409,str(exc)) from None
    f=db.get(AppConfig,'google_api') or AppConfig(clave='google_api')
    f.datos={'activo':True,'driveCuenta':email,'carpetaRaiz':raiz};f.usuario=op.usuario;db.add(f)
    programadas=0
    if email:
        from app.models import AppCopiaDrive, utcnow
        from app.services.entregas import conexion_rechazada
        for j in db.scalars(select(AppCopiaDrive).where(AppCopiaDrive.estado.in_(['PENDIENTE','REVISION'])).with_for_update()):
            if j.datos.get('accion')=='papelera':continue
            if j.estado=='PENDIENTE' or conexion_rechazada(j.error):
                j.estado='PENDIENTE';j.error=None;j.proximo_en=utcnow();programadas+=1
    procesos.registrar(db,'GOOGLE','CONFIGURADA','drive-operativo',op.usuario,codigo='DRIVE_CENTRAL');db.commit()
    return {**config(db,op),'fotosProgramadas':programadas}
