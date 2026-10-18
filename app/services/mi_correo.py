"""El supervisor autoriza solo su cuenta, sin administrar otras conexiones."""
import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from app.models import AppConfig, Operador, Rol, utcnow
from app.services import ajustes, entregas, integraciones as svc, operacion


def cuenta(db,op):
    if op.rol not in (Rol.SUPERVISOR,Rol.ADMIN):
        raise HTTPException(403,'Solo supervisores y ADMIN pueden autorizar su correo de informes.')
    email=(op.email or '').strip().lower()
    if not email:
        raise HTTPException(409,'Tu ficha no tiene correo. ADMIN debe completar tu dirección antes de autorizar Google.')
    perfiles=list(db.scalars(select(Operador.id).where(func.lower(Operador.email)==email,Operador.activo.is_(True))))
    if perfiles!=[op.id]:
        raise HTTPException(409,'Ese correo figura en varias cuentas activas. ADMIN debe corregir las fichas antes de autorizarlo.')
    return email


def _propia(db,email):
    return db.get(AppConfig,svc._clave_google(email))


def _firma(f):
    return hashlib.sha256(json.dumps(f.datos,sort_keys=True).encode()).hexdigest() if f else None


def estado(db,op):
    email=cuenta(db,op);f=_propia(db,email);d=f.datos if f else {}
    return {'correo':email,'url':d.get('url',''),'secretoConfigurado':bool(d.get('credencial')),
        'verificadoEn':d.get('verificadoEn'),'envioHabilitado':operacion.configuracion(db)['correo']['permitirPersonal']}


def guardar(db,op,datos,autor=None):
    email=cuenta(db,op);ident=op.id
    if set(datos)-{'url','secreto'}:
        raise HTTPException(422,'Solo puedes autorizar tu propia conexión. Tu correo se toma de la sesión.')
    f=_propia(db,email);anterior=dict(f.datos) if f else {};firma=_firma(f)
    url=svc._url(datos.get('url') or anterior.get('url',''),google=True)
    secreto=str(datos.get('secreto') or svc._descifrar(anterior.get('credencial')).get('secreto',''))
    if len(secreto)<32:raise HTTPException(422,'Configura una sola vez la misma clave SERVIDOR_HMAC de tu proyecto Apps Script (mínimo 32 caracteres).')
    if any(p['url']==url and p['supervisor']!=email for p in svc.puentes_publicos(db)):
        raise HTTPException(409,'Este /exec ya está asociado a otra cuenta. Crea o publica un despliegue desde tu cuenta '+email+'. Cambiar el texto del remitente no cambia la cuenta Google ejecutora. Si la asociación anterior es errónea, ADMIN debe revisarla.')
    db.rollback()  # No retener bloqueos durante la verificación externa.
    try:
        r=entregas.llamar_conexion('estado',uuid4().hex,{'usuario':email},{'url':url,'secreto':secreto,'supervisor':email})
        if str(r.get('remitente') or '').strip().lower()!=email:
            raise RuntimeError('El despliegue se ejecuta con otra cuenta Google.')
        if 'correoVerificado' not in r.get('capacidades',[]):
            raise HTTPException(409,'Publica juntos Proxy.gs y Servidor.gs actuales con una Nueva versión del mismo despliegue /exec antes de guardar. No se cambió tu conexión.')
    except RuntimeError as exc:
        texto=str(exc).lower()
        if any(p in texto for p in ('ejecut','otra cuenta','no pertenece')):
            mensaje=f'El /exec no confirmó a {email} como cuenta ejecutora. Abre Apps Script con {email}, autoriza los permisos y publica tu aplicación web como «Ejecutar como: Yo». Copia la URL de ese despliegue. Editar el remitente en ITSANET no cambia quién ejecuta Google.'
        else:
            mensaje=str(exc)
        raise HTTPException(502,mensaje+' No se guardó la conexión ni se envió correo.') from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502,'No fue posible contactar el puente Google. Revisa el /exec publicado y su acceso. No se guardó la conexión ni se envió correo.') from None
    db.rollback()
    actual=db.scalar(select(Operador).where(Operador.id==ident).with_for_update().execution_options(populate_existing=True))
    if not actual or not actual.activo or cuenta(db,actual)!=email:
        raise HTTPException(409,'Tu ficha cambió durante la verificación. Actualiza antes de guardar.')
    f=db.scalar(select(AppConfig).where(AppConfig.clave==svc._clave_google(email)).with_for_update().execution_options(populate_existing=True))
    if _firma(f)!=firma:raise HTTPException(409,'La conexión cambió mientras se comprobaba. Actualiza antes de guardar.')
    actor=autor or email
    svc.guardar_google(db,{'supervisor':email,'url':url,'secreto':secreto},actor,confirmar=False)
    f=_propia(db,email);f.datos={**f.datos,'verificadoEn':utcnow().isoformat()}
    ajustes.auditar(db,actor,'CORREO_PROPIO_AUTORIZADO',email,{'remitente':email,'configuradoPorAdmin':bool(autor)});db.commit()
    return {**estado(db,actual),'carpeta':r.get('carpeta',''),
        'mensaje':f'Conexión verificada y guardada para {email}. No se envió correo. La clave queda guardada para los siguientes envíos.'}
