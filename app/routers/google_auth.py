"""Google OAuth con PKCE y cookie de estado. Sesion y aprobacion locales."""
import base64
import hashlib
import hmac
import json
import re
import secrets
from urllib.parse import urlencode, urlparse
from uuid import uuid4

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.config import SESSION_HOURS
from app.db import get_db
from app.models import Operador, Rol
from app.security import COOKIE, crear_sesion, hash_pin
from app.services import integraciones as svc

router = APIRouter(prefix='/api/auth', tags=['auth-google'])
FLUJO = 'iv_google_flujo'


def disponible(request, c):
    if not c.get('activo') or not c.get('clientSecret'):
        return False
    uri = urlparse(c['redirectUri'])
    return str(request.base_url).rstrip('/') == f'{uri.scheme}://{uri.netloc}'


@router.get('/metodos')
def metodos(request: Request, db: Session = Depends(get_db)):
    c = svc.oauth(db)
    return {'clave': True, 'googleConfigurado': bool(c.get('activo')), 'googleDisponible': disponible(request, c)}


@router.get('/google/iniciar')
def iniciar(request: Request, db: Session = Depends(get_db)):
    c = svc.oauth(db)
    if not disponible(request, c):
        raise HTTPException(409, 'Google necesita configuracion OAuth y acceso por la URL autorizada. Puedes usar correo y contrasena.')
    estado, verificador = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).decode().rstrip('=')
    args = {'client_id': c['clientId'], 'redirect_uri': c['redirectUri'], 'response_type': 'code',
        'scope': 'openid email profile', 'state': estado, 'code_challenge': reto,
        'code_challenge_method': 'S256', 'prompt': 'select_account'}
    r = RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(args))
    contenido = svc._cifrador().encrypt(json.dumps({'state': estado, 'verifier': verificador}).encode()).decode()
    r.set_cookie(FLUJO, contenido, httponly=True, secure=c['redirectUri'].startswith('https:'), samesite='lax', max_age=600, path='/api/auth/google')
    return r


def identidad(c, codigo, verificador):
    # UserInfo de Google sobre TLS verifica al propietario del access_token,
    # obtenido por este cliente OAuth mediante codigo de un solo uso y PKCE.
    with httpx.Client(timeout=15) as http:
        token = http.post('https://oauth2.googleapis.com/token', data={
            'code': codigo, 'client_id': c['clientId'], 'client_secret': c['clientSecret'],
            'redirect_uri': c['redirectUri'], 'grant_type': 'authorization_code', 'code_verifier': verificador})
        token.raise_for_status()
        access = token.json().get('access_token')
        if not access:
            raise ValueError('sin token')
        info = http.get('https://openidconnect.googleapis.com/v1/userinfo', headers={'Authorization': 'Bearer ' + access})
        info.raise_for_status()
        u = info.json()
    if u.get('email_verified') is not True or not u.get('sub') or not u.get('email'):
        raise ValueError('correo no verificado')
    return u


@router.get('/google/callback')
def callback(request: Request, db: Session = Depends(get_db)):
    from app.routers import google_operacion
    if request.cookies.get(google_operacion.COOKIE) and request.query_params.get('state','').startswith('op_'):
        return google_operacion.callback(request,db)
    r = RedirectResponse('/app/?google=error', status_code=303)
    r.delete_cookie(FLUJO, path='/api/auth/google')
    if not request.cookies.get(FLUJO):
        return r
    try:
        flujo = json.loads(svc._cifrador().decrypt(request.cookies.get(FLUJO, '').encode(), ttl=600))
        if not hmac.compare_digest(flujo['state'], request.query_params.get('state', '')):
            return r
        c = svc.oauth(db)
        if not disponible(request, c) or not request.query_params.get('code'):
            return r
        u = identidad(c, request.query_params['code'], flujo['verifier'])
        if u.get('email_verified') is not True:
            return r
        email = str(u['email']).strip().lower()
        candidatos = db.scalars(select(Operador).where(func.lower(Operador.email) == email).limit(2)).all()
        if len(candidatos) > 1:
            return r
        op = candidatos[0] if candidatos else None
        if op is None:
            alias = re.sub(r'[^a-z0-9._-]', '', email.split('@')[0])[:38] or 'google'
            alias = alias if len(alias) >= 3 else 'google-' + alias
            if db.scalar(select(Operador.id).where(Operador.usuario == alias)):
                alias += '-' + uuid4().hex[:8]
            op = Operador(usuario=alias, nombre=str(u.get('name') or alias)[:120], email=email,
                rol=Rol.OPERADOR, activo=False, pin_hash=hash_pin(secrets.token_urlsafe(32)))
            db.add(op); db.commit()
        if not op.activo:
            r.headers['location'] = '/app/?google=pendiente'
            return r
        token = crear_sesion(db, op)
        r.headers['location'] = '/app/'
        r.set_cookie(COOKIE, token, httponly=True, secure=c['redirectUri'].startswith('https:'), samesite='lax', max_age=SESSION_HOURS * 3600)
        return r
    except (InvalidToken, ValueError, KeyError, httpx.HTTPError):
        return r
    except IntegrityError:
        db.rollback()
        return r
