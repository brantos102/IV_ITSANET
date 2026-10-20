"""Consulta explícita de la cuenta propia; no replica el buzón en MySQL."""
import re
from uuid import uuid4
from fastapi import HTTPException
from app.services import mi_correo, integraciones, entregas


def consultar(db, op, operacion, datos):
    email = mi_correo.cuenta(db, op)
    conexion = integraciones.google(db, email)
    if not conexion['url'] or not conexion['secreto']:
        raise HTTPException(409, 'Autoriza tu cuenta en Mi cuenta y correo antes de consultar Gmail.')
    db.rollback()
    try:
        estado = entregas.llamar_conexion('estado', uuid4().hex, {'usuario': email}, conexion)
        if str(estado.get('remitente', '')).lower() != email:
            raise HTTPException(409, 'El puente Google no pertenece a tu cuenta.')
        if 'gmailHilos' not in estado.get('capacidades', []):
            raise HTTPException(409, 'Para responder hilos, añade Gmail.gs y los permisos Gmail de lectura y envío, ejecuta verificarGmailServidor y publica una Nueva versión de tu /exec. El envío de correos nuevos sigue disponible.')
        r = entregas.llamar_conexion(operacion, uuid4().hex, {'usuario': email, **datos}, conexion)
    except HTTPException: raise
    except Exception:
        raise HTTPException(502, 'Gmail no confirmó la consulta. Revisa los permisos y la publicación de tu cuenta; no se envió ningún correo.') from None
    return {**r, 'cuenta': email}


def seleccionar(db, op, mensaje_id):
    if not isinstance(mensaje_id, str) or not re.fullmatch(r'[a-f0-9]{8,64}', mensaje_id):
        raise HTTPException(422, 'Selecciona un mensaje válido de Gmail.')
    r = consultar(db, op, 'gmailMensaje', {'mensajeId': mensaje_id})
    m = r.get('mensaje') or {}
    if m.get('id') != mensaje_id or not re.fullmatch(r'[a-f0-9]{8,64}', str(m.get('threadId', ''))):
        raise HTTPException(502, 'Gmail no confirmó el hilo seleccionado.')
    return {k: str(m.get(k) or '')[:3000] for k in ('id', 'threadId', 'asunto', 'de', 'para', 'cc', 'replyTo', 'fecha')} | {'cuenta': r['cuenta']}
