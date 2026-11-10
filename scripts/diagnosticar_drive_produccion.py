#!/usr/bin/env python3
"""Diagnóstico acotado: SQL de solo lectura y consultas GET a Drive.

No importa la aplicación, ejecuta migraciones, crea carpetas ni procesa la cola.
Si hace falta, renueva el acceso OAuth únicamente en memoria; no guarda tokens.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

DRIVE = 'https://www.googleapis.com/auth/drive'


def mapa(valor):
    return json.loads(valor) if isinstance(valor, (str, bytes)) else valor or {}


def leer_base(url, recepciones):
    import pymysql
    from sqlalchemy.engine import make_url
    u = make_url(url)
    if not u.drivername.startswith(('mysql', 'mariadb')) or not u.database:
        raise ValueError('Se requiere la conexión MySQL de producción.')
    opciones = {k: v for k, v in u.query.items() if k in
                ('ssl_ca', 'ssl_cert', 'ssl_key', 'unix_socket')}
    for k in ('ssl_verify_cert', 'ssl_verify_identity'):
        if k in u.query:
            opciones[k] = str(u.query[k]).lower() in ('true', '1', 'yes')
    con = pymysql.connect(host=u.host or 'localhost', port=u.port or 3306,
        user=u.username, password=u.password, database=u.database, charset='utf8mb4',
        connect_timeout=5, read_timeout=10, write_timeout=5, autocommit=True,
        cursorclass=pymysql.cursors.DictCursor, **opciones)
    try:
        with con.cursor() as c:
            c.execute('SELECT VERSION() AS version')
            maria = 'mariadb' in c.fetchone()['version'].lower()
            c.execute('SET SESSION time_zone = \'+00:00\'')
            c.execute('SET SESSION max_statement_time=5' if maria
                      else 'SET SESSION MAX_EXECUTION_TIME=5000')
            c.execute('START TRANSACTION READ ONLY')
            c.execute('SELECT estado, COUNT(*) AS cantidad FROM app_copias_drive GROUP BY estado')
            estados = {r['estado']: int(r['cantidad']) for r in c.fetchall()}
            filtro = ' AND j.recepcion IN (' + ','.join(['%s'] * len(recepciones)) + ')' if recepciones else ''
            c.execute('''SELECT j.archivo_id, j.recepcion, j.estado, j.intentos, j.usuario,
                j.error, j.datos, a.nombre, a.drive_id, a.sha256, a.bytes
                FROM app_copias_drive j JOIN app_archivos a ON a.id=j.archivo_id
                WHERE j.estado IN ('PENDIENTE','PROCESANDO','REVISION')''' + filtro +
                ' ORDER BY j.recepcion, j.archivo_id LIMIT 101', tuple(recepciones))
            filas = list(c.fetchall())
            if len(filas) > 100:
                raise ValueError('Más de 100 pendientes; indicar --recepcion para acotar.')
            c.execute("SELECT clave, datos FROM app_config WHERE clave IN ('google_api','oauth_google','operacion') OR clave LIKE 'go:%%'")
            configs = {r['clave']: mapa(r['datos']) for r in c.fetchall()}
            # Las reservas solo contienen un ID. No se seleccionan secretos ajenos.
            c.execute("SELECT clave, JSON_UNQUOTE(JSON_EXTRACT(datos,'$.id')) AS id FROM app_config WHERE clave LIKE 'gd:%%' LIMIT 20001")
            reservas = {r['clave']: r['id'] for r in c.fetchall()}
            if len(reservas) > 20000:
                raise ValueError('Demasiadas reservas para este diagnóstico acotado.')
            return estados, filas, configs, reservas
    finally:
        try:
            con.rollback()
        finally:
            con.close()


def original_local(data_dir, fila):
    ident = str(fila['archivo_id'])
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ident):
        return {'estado': 'IDENTIFICADOR_INVALIDO'}
    p = data_dir / 'app_archivos' / ident
    try:
        if not p.is_file():
            return {'estado': 'AUSENTE', 'tieneIdDrive': bool(fila['drive_id'])}
        tamano = p.stat().st_size
        if tamano > 16 * 1024 * 1024:
            return {'estado': 'NO_VERIFICADO_POR_TAMANO', 'bytes': tamano}
        bruto = p.read_bytes()
        coincide = len(bruto) == int(fila['bytes']) and hashlib.sha256(bruto).hexdigest() == fila['sha256']
        return {'estado': 'INTEGRO' if coincide else 'DIFIERE_DEL_REGISTRO', 'bytes': len(bruto)}
    except OSError:
        return {'estado': 'NO_SE_PUDO_LEER'}


def motivo(respuesta):
    try:
        error = respuesta.json().get('error', {})
        razones = [e.get('reason', '') for e in error.get('errors', [])] + [error.get('status', '')]
        return ','.join(r for r in razones if re.fullmatch(r'[A-Za-z_]{1,80}', str(r)))[:160]
    except (ValueError, AttributeError, TypeError):
        return ''


class LecturaGoogle:
    def __init__(self, configs, data_dir):
        self.configs, self.data_dir = configs, data_dir
        self.tokens, self.cache = {}, {}
        self.limite = time.monotonic() + 45

    def token(self, cuenta):
        import httpx
        from cryptography.fernet import Fernet
        k = 'go:' + hashlib.sha256(cuenta.strip().lower().encode()).hexdigest()[:32]
        d = self.configs.get(k, {})
        oauth = self.configs.get('oauth_google', {})
        if d.get('estado') != 'AUTORIZADA' or DRIVE not in d.get('scopes', []):
            raise ValueError('CUENTA_SIN_AUTORIZACION_DRIVE')
        if d.get('clientId') != oauth.get('clientId'):
            raise ValueError('CLIENTE_OAUTH_CAMBIO')
        cifrador = Fernet((self.data_dir / 'secretos' / 'integraciones.key').read_bytes())
        secreto = json.loads(cifrador.decrypt(d['credencial'].encode()))
        if secreto.get('vence', 0) > time.time() + 30:
            return secreto['access_token']
        cliente = json.loads(cifrador.decrypt(oauth['credencial'].encode()))
        # Solo OAuth: ningún POST a Drive, ningún cambio de credenciales en SQL.
        with httpx.Client(timeout=8) as http:
            r = http.post('https://oauth2.googleapis.com/token', data={
                'grant_type': 'refresh_token', 'client_id': oauth['clientId'],
                'client_secret': cliente['clientSecret'], 'refresh_token': secreto['refresh_token']})
        if r.status_code != 200:
            raise ValueError('NO_SE_PUDO_RENOVAR_ACCESO')
        return r.json()['access_token']

    def ficha(self, cuenta, ident):
        import httpx
        k = cuenta, ident
        if k in self.cache:
            return self.cache[k]
        if time.monotonic() >= self.limite or len(self.cache) >= 30:
            return {'estado': 'NO_CONSULTADO_LIMITE'}
        if not cuenta or not re.fullmatch(r'[A-Za-z0-9_-]{5,128}', str(ident or '')):
            return {'estado': 'CUENTA_O_ID_NO_CONFIGURADO'}
        try:
            if cuenta not in self.tokens:
                self.tokens[cuenta] = self.token(cuenta)
            with httpx.Client(timeout=5) as http:
                r = http.get('https://www.googleapis.com/drive/v3/files/' + ident,
                    headers={'Authorization': 'Bearer ' + self.tokens[cuenta]}, params={
                        'supportsAllDrives': 'true',
                        'fields': 'id,name,mimeType,trashed,parents,driveId,capabilities(canAddChildren,canEdit)'})
            if r.status_code == 200:
                resultado = {'estado': 'VISIBLE', **{k: v for k, v in r.json().items() if k in
                    ('id', 'name', 'mimeType', 'trashed', 'parents', 'driveId', 'capabilities')}}
            else:
                resultado = {'estado': 'NO_CONFIRMADO', 'http': r.status_code, 'motivo': motivo(r)}
        except ValueError as exc:
            razon = str(exc)
            resultado = {'estado': razon if re.fullmatch('[A-Z_]{1,80}', razon) else 'RESPUESTA_INVALIDA'}
        except Exception as exc:
            resultado = {'estado': 'NO_SE_PUDO_CONSULTAR', 'tipo': type(exc).__name__}
        self.cache[k] = resultado
        return resultado


def diagnosticar(estados, filas, configs, reservas, data_dir, remoto=None):
    central = configs.get('google_api', {})
    salida = {'consultadoEn': datetime.now(timezone.utc).isoformat(), 'soloLecturaSQL': True,
        'operacionesDrive': ['GET files/id'] if remoto else [], 'estadosFotos': estados,
        'cuentaOperativa': central.get('driveCuenta', ''), 'raizCentral': central.get('carpetaRaiz', ''),
        'limite': '100 pendientes, 30 recursos remotos y 45 segundos; no es una auditoría completa de Drive.',
        'interpretacion404': 'Un ID reservado todavía no creado puede dar 404 normalmente. En una carpeta existente, 404 también puede significar falta de acceso.',
        'destinos': [], 'pendientes': []}
    destinos = {}
    for f in filas:
        p = mapa(f['datos'])
        cuenta = central.get('driveCuenta') or f['usuario']
        raiz = p.get('carpetaRaiz') or central.get('carpetaRaiz', '')
        item = {k: f[k] for k in ('archivo_id', 'recepcion', 'estado', 'intentos', 'nombre', 'drive_id')}
        item.update(cuentaDrive=cuenta, raiz=raiz, carpetaRecepcionId=p.get('carpetaRecepcionId', ''),
                    original=original_local(data_dir, f), proceso=p.get('proceso', {}),
                    codigoError=str(f.get('error') or '').split(':', 1)[0][:80], reservasRuta=[])
        partes = ([] if p.get('carpetaRecepcionId') else
                  [p.get('cliente'), p.get('marca'), p.get('carpetaRecepcion') or f['recepcion']])
        partes += p.get('ruta') or ['imagenes']
        clave_destino = (cuenta, raiz, p.get('carpetaRecepcionId'), tuple(partes))
        if clave_destino in destinos:
            item['destino'] = destinos[clave_destino]
            item.pop('reservasRuta')
            k = 'gd:' + hashlib.sha256((cuenta + '|archivo:' + f['archivo_id'] + ':' + f['archivo_id']).encode()).hexdigest()[:32]
            item['idArchivoReservado'] = reservas.get(k)
            salida['pendientes'].append(item)
            continue
        destino = {k: item[k] for k in ('cuentaDrive', 'raiz', 'carpetaRecepcionId', 'reservasRuta')}
        destino['numero'] = len(salida['destinos']) + 1
        destinos[clave_destino] = item['destino'] = destino['numero']
        if remoto:
            destino['raizRemota'] = remoto.ficha(cuenta, raiz)
        padre = p.get('carpetaRecepcionId') or raiz
        if p.get('carpetaRecepcionId') and remoto:
            destino['recepcionRemota'] = remoto.ficha(cuenta, padre)
        for parte in filter(None, partes):
            n = re.sub(r'[\\/\x00-\x1f]', '_', str(parte)).strip()[:180]
            k = 'gd:' + hashlib.sha256((cuenta + '|carpeta:' + padre + '/' + n).encode()).hexdigest()[:32]
            ident = reservas.get(k)
            ruta = {'nombre': n, 'padre': padre, 'idReservado': ident}
            if ident and remoto:
                ruta['remoto'] = remoto.ficha(cuenta, ident)
            item['reservasRuta'].append(ruta)
            if not ident:
                break
            padre = ident
        item.pop('reservasRuta')
        salida['destinos'].append(destino)
        k = 'gd:' + hashlib.sha256((cuenta + '|archivo:' + f['archivo_id'] + ':' + f['archivo_id']).encode()).hexdigest()[:32]
        item['idArchivoReservado'] = reservas.get(k)
        salida['pendientes'].append(item)
    salida['originalesLocales'] = dict(Counter(x['original']['estado'] for x in salida['pendientes']))
    return salida


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path.cwd())
    p.add_argument('--recepcion', action='append', default=[])
    p.add_argument('--sin-red', action='store_true')
    p.add_argument('--salida', type=Path, required=True)
    a = p.parse_args()
    try:
        estados, filas, configs, reservas = leer_base(os.environ['VAL_DATABASE_URL'], a.recepcion)
        data = Path(os.getenv('VAL_DATA_DIR', a.repo / 'data'))
        if not data.is_absolute():
            data = a.repo / data
        r = diagnosticar(estados, filas, configs, reservas, data,
                         None if a.sin_red else LecturaGoogle(configs, data))
        r['revisionInstalada'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=a.repo, text=True).strip()
        texto = json.dumps(r, ensure_ascii=False, indent=2)
        a.salida.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.fdopen(os.open(a.salida, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
            f.write(texto + '\n')
        print(texto)
        print('Archivo privado:', a.salida)
    except Exception as exc:
        p.exit(1, 'Diagnóstico incompleto (' + type(exc).__name__ +
               '). No se modificó la base ni se escribieron archivos en Drive.\n')


if __name__ == '__main__':
    main()
