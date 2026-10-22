"""Consulta explícita de la cuenta propia; no replica el buzón en MySQL."""
import re
import logging
import httpx
from uuid import uuid4
from fastapi import HTTPException
from app.services import mi_correo, integraciones, entregas


def consultar(db, op, operacion, datos):
    email = mi_correo.cuenta(db, op)
    conexion = integraciones.google(db, email)
    if not integraciones.conexion_lista(conexion):
        raise HTTPException(409, 'Autoriza tu cuenta en Mi cuenta y correo antes de consultar Gmail.')
    db.rollback()
    try:
        legado=False;perfil={}
        try:perfil=entregas.llamar_conexion('gmailEstado',uuid4().hex,{'usuario':email},conexion)
        except RuntimeError as exc:
            # Compatibilidad con despliegues anteriores; solo una operación desconocida.
            if 'no reconoce esta operación' not in str(exc):raise
            legado=True
        if perfil.get('cuentaGmail'):
            if str(perfil['cuentaGmail']).lower()!=email:raise HTTPException(409,'El buzón Google no pertenece a tu cuenta.')
        else:legado=True
        if legado:
            estado=entregas.llamar_conexion('estado',uuid4().hex,{'usuario':email},conexion)
            if str(estado.get('remitente','')).lower()!=email:raise HTTPException(409,'El puente Google no pertenece a tu cuenta.')
            if 'gmailHilos' not in estado.get('capacidades',[]):raise HTTPException(409,'Para responder hilos, añade Gmail.gs y los permisos Gmail de lectura y envío, ejecuta verificarGmailServidor y publica una Nueva versión de tu /exec. El envío de correos nuevos sigue disponible.')
            if operacion=='gmailEstado':raise HTTPException(409,'Actualiza Gmail.gs y Servidor.gs versión 62 para comprobar tu buzón sin depender de Drive.')
        r=perfil if operacion=='gmailEstado' else entregas.llamar_conexion(operacion,uuid4().hex,{'usuario':email,**datos},conexion)
    except HTTPException: raise
    except RuntimeError as exc:
        mensaje=str(exc)
        encontrado=re.match(r'^(GMAIL_[A-Z_]+): (.+)$',mensaje)
        if encontrado:
            raise HTTPException(409,{'codigo':encontrado[1],'mensaje':encontrado[2]}) from None
        raise HTTPException(502,mensaje+' Esta consulta no envía correo.') from None
    except httpx.TimeoutException:
        raise HTTPException(504,{'codigo':'GMAIL_TIEMPO','mensaje':'La consulta Gmail agotó el tiempo de espera. Puedes cerrar y volver a buscar; no se envió correo ni se modificó el buzón.'}) from None
    except httpx.RequestError as exc:
        logging.getLogger('iv_itsanet.gmail').warning('Consulta Gmail sin conexión causa=%s',type(exc).__name__)
        raise HTTPException(502,{'codigo':'GMAIL_RED','mensaje':'El servidor no pudo conectar con Google. Revisa salida HTTPS, DNS y la publicación del puente; no cambies la clave HMAC por este aviso. No se envió correo.'}) from None
    except Exception as exc:
        logging.getLogger('iv_itsanet.gmail').warning('Consulta Gmail no confirmada causa=%s',type(exc).__name__)
        raise HTTPException(502, 'Gmail no confirmó la consulta. Revisa los permisos y la publicación de tu cuenta; no se envió ningún correo.') from None
    if r.get('cuentaGmail') and str(r['cuentaGmail']).lower()!=email:raise HTTPException(409,'Google devolvió otro buzón. Revisa el despliegue de tu cuenta; no se seleccionó ningún hilo.')
    return {**r, 'cuenta': email}


def seleccionar(db, op, mensaje_id):
    if not isinstance(mensaje_id, str) or not re.fullmatch(r'[a-f0-9]{8,64}', mensaje_id):
        raise HTTPException(422, 'Selecciona un mensaje válido de Gmail.')
    r = consultar(db, op, 'gmailMensaje', {'mensajeId': mensaje_id})
    m = r.get('mensaje') or {}
    if m.get('id') != mensaje_id or not re.fullmatch(r'[a-f0-9]{8,64}', str(m.get('threadId', ''))):
        raise HTTPException(502, 'Gmail no confirmó el hilo seleccionado.')
    return {k: str(m.get(k) or '')[:3000] for k in ('id', 'threadId', 'asunto', 'de', 'para', 'cc', 'replyTo', 'fecha')} | {'cuenta': r['cuenta']}
