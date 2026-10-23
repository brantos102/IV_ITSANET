"""OAuth central: cada persona autoriza su cuenta; Drive puede usar una cuenta operativa.

Los tokens se cifran con la clave de integraciones existente. El navegador nunca
recibe tokens ni secretos; los puentes anteriores se conservan para compatibilidad.
"""
import hashlib
import json
import time
import httpx
from sqlalchemy import select
from app.models import AppConfig, utcnow
from app.services import integraciones as cred, procesos

DRIVE='https://www.googleapis.com/auth/drive'
LECTURA='https://www.googleapis.com/auth/gmail.readonly'
ENVIO='https://www.googleapis.com/auth/gmail.send'
SCOPES={'CORREO':['openid','email',LECTURA,ENVIO], 'DRIVE':['openid','email',DRIVE]}


def clave(email):return 'go:'+hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]


def configuracion(db):
    f=db.get(AppConfig,'google_api')
    return dict(f.datos) if f else {'activo':True,'driveCuenta':''}


def estado(db,email):
    f=db.get(AppConfig,clave(email));d=f.datos if f else {};scopes=set(d.get('scopes',[]))
    return {'correo':email,'conectada':bool(d.get('credencial') and d.get('estado')=='AUTORIZADA'),
        'drive':DRIVE in scopes,'gmail':{LECTURA,ENVIO}<=scopes,
        'estado':d.get('estado','SIN_AUTORIZAR'),'autorizadaEn':d.get('autorizadaEn'),
        'oauthConfigurado':bool(cred.oauth(db).get('activo'))}


def conexion(db,email):
    c=configuracion(db)
    if not c.get('activo'):return None
    email=str(email or '').lower();propia=estado(db,email) if email else {}
    if propia.get('conectada') or c.get('driveCuenta'):
        return {'tipo':'GOOGLE_API','supervisor':email,'driveCuenta':c.get('driveCuenta',''),'carpetaRaiz':c.get('carpetaRaiz',''),
            'url':'','secreto':''}
    return None


def responsable_drive(db,codigo,usuario):
    c=configuracion(db)
    if c.get('activo') and c.get('driveCuenta'):return c['driveCuenta']
    from app.services.remitentes import elegir
    return elegir(db,codigo,{'modoRemitente':'RESPONSABLE'},usuario)[0]


def guardar_tokens(db,email,token,usuario):
    if not token.get('access_token'):raise ValueError('sin token')
    f=db.get(AppConfig,clave(email)) or AppConfig(clave=clave(email));previo=f.datos or {}
    anterior=cred._descifrar(previo.get('credencial'))
    secreto={'access_token':token['access_token'],'refresh_token':token.get('refresh_token') or anterior.get('refresh_token'),
        'vence':time.time()+int(token.get('expires_in',3600))}
    if not secreto['refresh_token']:raise ValueError('sin autorización offline')
    f.datos={'correo':email,'estado':'AUTORIZADA','scopes':str(token.get('scope','')).split(),
        'autorizadaEn':utcnow().isoformat(),'clientId':cred.oauth(db)['clientId'],
        'credencial':cred._cifrador(crear=True).encrypt(json.dumps(secreto).encode()).decode()}
    f.usuario=usuario;db.add(f)
    procesos.registrar(db,'GOOGLE','AUTORIZADA',email,usuario,codigo='OAUTH_OK')
    db.commit()


def acceso(email, scopes):
    from app.db import SessionLocal
    with SessionLocal() as db:
        f=db.scalar(select(AppConfig).where(AppConfig.clave==clave(email)).with_for_update())
        c=cred.oauth(db)
        if not f or f.datos.get('estado')!='AUTORIZADA':raise RuntimeError('GOOGLE_AUTORIZACION: Conecta esta cuenta con Google desde Mi cuenta y correo.')
        if f.datos.get('clientId')!=c.get('clientId'):raise RuntimeError('GOOGLE_AUTORIZACION: La configuración OAuth cambió. Vuelve a conectar tu cuenta.')
        if not set(scopes)<=set(f.datos.get('scopes',[])):raise RuntimeError('GOOGLE_PERMISOS: Autoriza los permisos de esta operación desde Mi cuenta y correo.')
        secreto=cred._descifrar(f.datos['credencial'])
        if secreto.get('vence',0)>time.time()+60:return secreto['access_token']
        try:
            with httpx.Client(timeout=20) as http:
                r=http.post('https://oauth2.googleapis.com/token',data={'grant_type':'refresh_token',
                    'client_id':c['clientId'],'client_secret':c['clientSecret'],'refresh_token':secreto['refresh_token']})
            if r.status_code in (400,401):
                f.datos={**f.datos,'estado':'REAUTORIZAR'}
                procesos.registrar(db,'GOOGLE','ERROR',email,email,codigo='OAUTH_REAUTORIZAR');db.commit()
                raise RuntimeError('GOOGLE_AUTORIZACION: Google retiró o venció el permiso. Pulsa Conectar con Google otra vez.')
            if r.status_code!=200:raise RuntimeError('GOOGLE_TOKEN: Google no pudo renovar el acceso. Se reintentará.')
            t=r.json()
            if not t.get('access_token'):raise RuntimeError('GOOGLE_TOKEN: Respuesta de autorización incompleta.')
            secreto.update(access_token=t['access_token'],vence=time.time()+int(t.get('expires_in',3600)))
            f.datos={**f.datos,'credencial':cred._cifrador().encrypt(json.dumps(secreto).encode()).decode()};db.commit()
            return secreto['access_token']
        except httpx.HTTPError:raise RuntimeError('GOOGLE_RED: No se pudo renovar el acceso. Se conserva el trabajo pendiente.') from None


def peticion(email,servicio,metodo,ruta,**opciones):
    scope=DRIVE if servicio in ('drive','upload') else ENVIO if metodo=='POST' and ruta=='messages/send' else LECTURA
    token=acceso(email,[scope])
    base='https://www.googleapis.com/drive/v3/' if servicio=='drive' else 'https://gmail.googleapis.com/gmail/v1/users/me/'
    if servicio=='upload':base='https://www.googleapis.com/upload/drive/v3/'
    # La URL la construye el servidor; no acepta URLs arbitrarias del usuario.
    try:
        with httpx.Client(timeout=httpx.Timeout(90,connect=10)) as http:
            extra=opciones.pop('headers_extra',{})
            r=http.request(metodo,base+ruta,headers={'Authorization':'Bearer '+token,**extra},**opciones)
    except httpx.HTTPError:raise RuntimeError('GOOGLE_RED: No se recibió confirmación de Google. El proceso conserva su registro.') from None
    if r.status_code>=400:
        codigo='GOOGLE_RED'
        if r.status_code==401:codigo='GOOGLE_AUTORIZACION'
        elif r.status_code==403:
            error=r.text.lower()
            codigo='GOOGLE_API_DESACTIVADA' if any(s in error for s in ('service_disabled','accessnotconfigured','is disabled','has not been used')) else 'GOOGLE_PERMISOS'
        elif r.status_code==404:codigo='GOOGLE_NO_ENCONTRADO'
        elif r.status_code in (429,503):codigo='GOOGLE_CUOTA'
        raise RuntimeError(codigo+': Google no confirmó la operación (HTTP '+str(r.status_code)+'). Revisa el registro de procesos y los permisos de la cuenta.')
    return r


def cuenta_drive(destino):
    return destino.get('driveCuenta') or destino.get('supervisor') or ''
