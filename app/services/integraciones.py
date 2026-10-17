"""Credenciales por cliente: cifradas en MySQL, clave fuera de la base."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select

from app import config
from app.models import AppConfig, utcnow


def _cifrador(crear=False):
    carpeta = config.DATA_DIR / 'secretos'
    archivo = carpeta / 'integraciones.key'
    if crear:
        carpeta.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            with archivo.open('xb') as f:
                os.chmod(archivo, 0o600)
                f.write(Fernet.generate_key())
                f.flush(); os.fsync(f.fileno())
        except FileExistsError:
            pass
    try:
        return Fernet(archivo.read_bytes())
    except (OSError, ValueError):
        raise HTTPException(503, 'No se puede leer la clave privada de integraciones. Revisa el respaldo del servidor.') from None


def _descifrar(valor):
    if not valor:
        return {}
    try:
        return json.loads(_cifrador().decrypt(valor.encode()).decode())
    except (InvalidToken, ValueError):
        raise HTTPException(503, 'No se pudieron abrir las credenciales. Revisa la clave privada del servidor.') from None


def _url(valor, google=False):
    valor = str(valor or '').strip().rstrip('/')
    u = urlparse(valor)
    try:
        puerto = u.port
    except ValueError:
        raise HTTPException(422, 'Puerto invalido en la URL') from None
    if any(c.isspace() for c in valor):
        raise HTTPException(422, 'La URL no debe contener espacios')
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise HTTPException(422, 'URL invalida: usa http(s) sin usuario, contrasena ni parametros')
    if google and not re.fullmatch(r'https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec', valor):
        raise HTTPException(422, 'Usa la URL HTTPS /exec del Apps Script')
    return valor


def clientes(db):
    return list(db.scalars(select(AppConfig).where(AppConfig.clave.like('depot:%')).order_by(AppConfig.clave)))


def credenciales(db, ident=None):
    filas = clientes(db)
    if ident:
        filas = [f for f in filas if f.clave == 'depot:' + ident.upper()]
    return [{**f.datos, **_descifrar(f.datos.get('credencial')), 'id': f.clave[6:]} for f in filas if f.datos.get('activo', True)]


def lista_publica(db):
    return [{k: v for k, v in f.datos.items() if k != 'credencial'} | {
        'id': f.clave[6:], 'tieneCredenciales': bool(f.datos.get('credencial'))} for f in clientes(db)]


def guardar_cliente(db, ident, datos, usuario):
    ident = str(ident).upper()
    if not re.fullmatch(r'[A-Z0-9_-]{1,32}', ident):
        raise HTTPException(422, 'Identificador: hasta 32 letras, numeros, guion o guion bajo')
    f = db.get(AppConfig, 'depot:' + ident)
    anteriores = f.datos if f else {}
    secretos = _descifrar(anteriores.get('credencial'))
    for k in ('usuario', 'clave'):
        if datos.get(k): secretos[k] = str(datos[k])
    if any(any(ord(c) < 32 or ord(c) == 127 for c in str(v)) for v in secretos.values()):
        raise HTTPException(422, 'Las credenciales no deben contener saltos de linea ni caracteres de control')
    if not secretos.get('usuario') or not secretos.get('clave'):
        raise HTTPException(422, 'Completa el usuario y la clave de Depot')
    url = _url(datos.get('baseUrl', anteriores.get('baseUrl', config.DEPOT_BASE_URL)))
    publicos = {'nombre': str(datos.get('nombre') or anteriores.get('nombre') or ident)[:120],
        'baseUrl': url, 'cliente': str(datos.get('cliente', anteriores.get('cliente', ident)))[:80],
        'activo': datos.get('activo', anteriores.get('activo', True)) is True,
        'rutaToken': str(datos.get('rutaToken') or anteriores.get('rutaToken') or '/gettoken'),
        'rutaStock': str(datos.get('rutaStock') or anteriores.get('rutaStock') or '/getstock'),
        'cabeceraToken': str(datos.get('cabeceraToken') or anteriores.get('cabeceraToken') or 'token')}
    for k in ('rutaToken', 'rutaStock'):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]{1,100}', publicos[k]) or '..' in publicos[k]:
            raise HTTPException(422, 'La ruta debe empezar con / y permanecer dentro de la API')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', publicos['cabeceraToken']):
        raise HTTPException(422, 'Cabecera de token invalida')
    f = f or AppConfig(clave='depot:' + ident)
    f.datos = {**publicos, 'credencial': _cifrador(crear=True).encrypt(json.dumps(secretos).encode()).decode()}
    f.usuario, f.modificado_en = usuario, utcnow()
    db.add(f); db.commit()
    return next(c for c in lista_publica(db) if c['id'] == ident)


def _clave_google(supervisor):
    return 'g:' + hashlib.sha256(supervisor.encode()).hexdigest()[:32]


def puentes_publicos(db):
    return [{'supervisor': f.datos['supervisor'], 'url': f.datos['url'],
             'secretoConfigurado': bool(f.datos.get('credencial'))}
            for f in db.scalars(select(AppConfig).where(AppConfig.clave.like('g:%')))]


def google(db, supervisor=None):
    email = str(supervisor or '').strip().lower()
    f = db.get(AppConfig, _clave_google(email)) if email else None
    f = f or db.get(AppConfig, 'google')
    if f:
        return {'url': f.datos.get('url', ''), 'secreto': _descifrar(f.datos.get('credencial')).get('secreto', ''),
                'supervisor': f.datos.get('supervisor', '')}
    return {'url': config.VAL_GOOGLE_PROXY_URL, 'secreto': config.VAL_GOOGLE_PROXY_SECRET}


def guardar_google(db, datos, usuario):
    supervisor = str(datos.get('supervisor') or '').strip().lower()
    if supervisor and not re.fullmatch(r'[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+', supervisor):
        raise HTTPException(422, 'Correo del supervisor invalido')
    anterior = google(db, supervisor)
    url = _url(datos.get('url') or anterior['url'], google=True)
    secreto = str(datos.get('secreto') or anterior['secreto'])
    if len(secreto) < 32:
        raise HTTPException(422, 'La clave compartida debe tener al menos 32 caracteres')
    clave = _clave_google(supervisor) if supervisor else 'google'
    f = db.get(AppConfig, clave) or AppConfig(clave=clave)
    # Un puente nuevo de otro supervisor requiere su propia clave, no hereda otra.
    if supervisor and f.datos is None and not datos.get('secreto'):
        raise HTTPException(422, 'Ingresa la clave compartida del puente de este supervisor')
    f.datos = {'url': url, 'supervisor': supervisor, 'credencial': _cifrador(crear=True).encrypt(json.dumps({'secreto': secreto}).encode()).decode()}
    f.usuario, f.modificado_en = usuario, utcnow()
    db.add(f); db.commit()
    return {'url': url, 'supervisor': supervisor, 'secretoConfigurado': True}


def oauth(db):
    f = db.get(AppConfig, 'oauth_google')
    if not f:
        return {}
    return {**f.datos, **_descifrar(f.datos.get('credencial'))}


def guardar_oauth(db, datos, usuario):
    anterior = oauth(db)
    redirect = _url(datos.get('redirectUri') or anterior.get('redirectUri'))
    uri = urlparse(redirect)
    if uri.path != '/api/auth/google/callback' or (uri.scheme != 'https' and uri.hostname not in ('localhost', '127.0.0.1')):
        raise HTTPException(422, 'Callback: HTTPS, o localhost para pruebas, y ruta /api/auth/google/callback')
    client_id = str(datos.get('clientId') or anterior.get('clientId') or '').strip()
    secreto = str(datos.get('clientSecret') or anterior.get('clientSecret') or '')
    if not client_id.endswith('.apps.googleusercontent.com') or not secreto:
        raise HTTPException(422, 'Completa el ID y secreto del cliente OAuth web de Google')
    f = db.get(AppConfig, 'oauth_google') or AppConfig(clave='oauth_google')
    f.datos = {'clientId': client_id, 'redirectUri': redirect,
        'activo': datos.get('activo', True) is True,
        'credencial': _cifrador(crear=True).encrypt(json.dumps({'clientSecret': secreto}).encode()).decode()}
    f.usuario, f.modificado_en = usuario, utcnow()
    db.add(f); db.commit()
    return {'clientId': client_id, 'redirectUri': redirect, 'activo': f.datos['activo'], 'secretoConfigurado': True}
