"""Auditoría puntual: no importa la app, migra, reinicia ni modifica MySQL."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location('estado_produccion', Path(__file__).with_name('estado_produccion.py'))
estado = importlib.util.module_from_spec(spec)
spec.loader.exec_module(estado)


def proxy_publico(valor):
    """Nunca mostrar credenciales, query o fragmento de un upstream."""
    try:
        u = urlsplit(valor)
        if u.scheme not in ('http', 'https') or not u.hostname: return '[destino no identificado]'
        host = '[' + u.hostname + ']' if ':' in u.hostname else u.hostname
        return urlunsplit((u.scheme, host + (':' + str(u.port) if u.port else ''), u.path, '', ''))
    except ValueError:
        return '[destino no identificado]'


def apache(carpeta=Path('/etc/apache2/sites-enabled')):
    resultado = []
    for nombre in ('itsanet-app-8443.conf', 'itsanet-data-sync-ssl.conf', 'itsanet-data-sync.conf'):
        fila = {'archivo': nombre, 'directivas': []}
        try:
            for linea in (carpeta / nombre).read_text().splitlines():
                s = linea.strip()
                if re.match(r'^(<VirtualHost\s|ServerName\s|SSLCertificate(?:Key)?File\s)', s, re.I):
                    fila['directivas'].append(s)
                elif re.match(r'^ProxyPass(?:Reverse)?\s', s, re.I):
                    partes = s.split()
                    if len(partes) >= 3:
                        fila['directivas'].append(partes[0] + ' ' + partes[1] + ' ' + proxy_publico(partes[2].strip('\"\'')))
                elif re.fullmatch(r'ProxyPreserveHost\s+(On|Off)', s, re.I):
                    fila['directivas'].append(s)
                elif re.fullmatch(r'RequestHeader\s+set\s+X-Forwarded-Proto\s+"?https"?', s, re.I):
                    fila['directivas'].append('RequestHeader set X-Forwarded-Proto https')
            fila['estado'] = 'Leído; solo directivas permitidas. No se lee la clave TLS.'
        except OSError as exc:
            fila['estado'] = 'No disponible (' + type(exc).__name__ + ')'
        resultado.append(fila)
    return resultado


def tls():
    r = {'destino': 'apps.flexnetuio.com:8443', 'verificacion': 'Sin confirmar'}
    try:
        contexto = ssl.create_default_context()
        with socket.create_connection(('apps.flexnetuio.com', 8443), timeout=5) as conexion:
            with contexto.wrap_socket(conexion, server_hostname='apps.flexnetuio.com') as canal:
                cert = canal.getpeercert()
                r.update(verificacion='Nombre y cadena validados con la CA de este servidor', protocolo=canal.version(),
                    emisor=cert.get('issuer'), nombres=cert.get('subjectAltName'),
                    vence=cert.get('notAfter'), diasHastaVencimiento=int((ssl.cert_time_to_seconds(cert['notAfter'])-time.time())/86400))
    except Exception as exc:
        r['verificacion'] = 'No confirmado desde este servidor (' + type(exc).__name__ + ')'
    r['limite'] = 'La confianza de Windows o de cada móvil debe comprobarse en ese dispositivo.'
    return r


def capturar(repo):
    ahora = datetime.now(timezone.utc)
    datos = Path(os.environ.get('VAL_DATA_DIR') or repo / 'data')
    r = {'fechaEcuador': ahora.astimezone(ZoneInfo('America/Guayaquil')).isoformat(),
        'fechaUTC': ahora.isoformat(), 'alcance': 'Solo lectura; crea únicamente informes privados fuera del código y MySQL.',
        'commitInstalado': estado.comando(['git', 'rev-parse', 'HEAD'], repo),
        'cambiosLocalesPorRuta': estado.comando(['git', 'status', '--porcelain', '--untracked-files=no'], repo),
        'servicio': estado.comando(['systemctl', 'show', 'iv-itsanet', '-p', 'ActiveState', '-p', 'SubState',
            '-p', 'Result', '-p', 'NRestarts', '-p', 'MemoryCurrent', '-p', 'TasksCurrent',
            '-p', 'WorkingDirectory', '-p', 'ActiveEnterTimestamp', '-p', 'UnitFileState']),
        'puertos': estado.comando(['ss', '-ltn', '( sport = :80 or sport = :443 or sport = :8443 or sport = :3002 or sport = :3306 )']),
        'memoria': {}, 'mysql': None, 'archivos': {}, 'apache': apache(), 'tls': tls(), 'avisos': []}
    try:
        fuente = (repo / 'scripts/versionar_frontend.mjs').read_text()
        m = re.search(r"VERSION_FRONTEND='([^']+)'", fuente)
        r['frontendEnDisco'] = m.group(1) if m else 'No identificado'
    except OSError: r['frontendEnDisco'] = 'No identificado'
    try:
        with urllib.request.urlopen('http://127.0.0.1:3002/health', timeout=5) as res:
            cuerpo = json.loads(res.read(4096))
            r['saludLocal'] = 'ok' if res.status == 200 and cuerpo.get('ok') is True else 'Respuesta inesperada'
    except Exception as exc: r['saludLocal'] = 'No confirmada (' + type(exc).__name__ + ')'
    try:
        uso = shutil.disk_usage(datos)
        r['discoFilesystem'] = {'totalBytes': uso.total, 'libresBytes': uso.free, 'usadosBytes': uso.used,
            'porcentajeUsado': round(uso.used / uso.total * 100, 1)}
    except OSError: r['discoFilesystem'] = None
    try:
        for linea in Path('/proc/meminfo').read_text().splitlines():
            k, v = linea.split(':', 1)
            if k in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'): r['memoria'][k + 'KiB'] = int(v.split()[0])
        r['cargaCPU'] = {'promedios1_5_15min': os.getloadavg(), 'cpusVisibles': os.cpu_count()}
    except (OSError, ValueError, AttributeError): pass
    for sub in ('app_archivos', 'app_miniaturas', 'uploads', 'exports', 'fotos'):
        # Reutiliza el contador acotado, sin leer contenidos ni seguir enlaces.
        r['archivos'][sub] = estado.disco(datos) if sub == 'app_archivos' else contar(datos / sub)
    r['configuracionSinValores'] = {
        'databaseUrlPresente': bool(os.environ.get('VAL_DATABASE_URL')),
        'secretKeyPersonalizadaEnEntorno': bool(os.environ.get('VAL_SECRET_KEY')) and os.environ['VAL_SECRET_KEY'] != 'cambiar-esta-clave-en-produccion',
        'cookieSecureForzada': os.environ.get('VAL_COOKIE_SECURE') == '1',
        'marcadoPruebasPublicas': os.environ.get('ITSANET_PRUEBAS_PUBLICAS') == '1',
        'claveCifradoExiste': (datos / 'secretos/integraciones.key').is_file(),
        'sesionesHorasEnEntorno': os.environ.get('VAL_SESSION_HOURS', '12 (predeterminado)') if re.fullmatch(r'\d+', os.environ.get('VAL_SESSION_HOURS', '12')) else '[valor no numérico]'}
    try: r['mysql'] = estado.base_mysql(os.environ.get('VAL_DATABASE_URL', ''))
    except Exception as exc: r['avisos'].append('MySQL no confirmado (' + type(exc).__name__ + '); no se muestran credenciales.')
    r['temporizadoresITSANET'] = estado.comando(['systemctl', 'list-timers', '--all', '--no-pager', 'iv-itsanet*'])
    r['avisos'].extend(['/health y un commit en disco no demuestran carga real, backup restaurable ni proceso sin cambios posteriores al arranque.',
        'MySQL informa asignación estimada de datos/índices; no es el disco total ni una medición de crecimiento diario.',
        'Archivar historial no reduce por sí mismo filas ni espacio. No se ejecutan limpiezas, OPTIMIZE, migraciones o envíos.'])
    return r


def contar(carpeta):
    # estado.disco acepta solo app_archivos. Mantener el mismo límite para otras carpetas.
    try:
        total = cantidad = 0
        with os.scandir(carpeta) as entradas:
            for e in entradas:
                if cantidad >= 100000: return {'estado': 'limite', 'archivos': cantidad, 'bytes': total}
                if e.is_file(follow_symlinks=False):
                    try: total += e.stat(follow_symlinks=False).st_size; cantidad += 1
                    except FileNotFoundError: pass
        return {'estado': 'ok', 'archivos': cantidad, 'bytes': total}
    except OSError as exc: return {'estado': type(exc).__name__, 'archivos': None, 'bytes': None}


def markdown(r):
    lineas = ['# Captura técnica de IV_ITSANET', '', 'Hora Ecuador: ' + r['fechaEcuador'], '',
              'Solo lectura. No se incluyen contraseñas, tokens, claves ni contenido de fotos.', '']
    for k, v in r.items():
        lineas.extend(['## ' + k, '', '```json', json.dumps(v, ensure_ascii=False, indent=2), '```', ''])
    return '\n'.join(lineas)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True); p.add_argument('--salida', type=Path, required=True)
    a = p.parse_args(); repo = a.repo.resolve(); salida = a.salida.resolve()
    if salida == repo or repo in salida.parents: p.error('Guardar informes fuera del repositorio operativo.')
    os.umask(0o077)
    r = capturar(repo)
    salida.mkdir(parents=True, exist_ok=True, mode=0o700)
    nombre = 'auditoria-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for extension, contenido in (('json', json.dumps(r, ensure_ascii=False, indent=2)), ('md', markdown(r))):
        destino = salida / (nombre + '.' + extension)
        with destino.open('x') as f: f.write(contenido)
        print(destino)
    return 0 if r['mysql'] else 2


if __name__ == '__main__': raise SystemExit(main())
