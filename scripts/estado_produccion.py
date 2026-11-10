#!/usr/bin/env python3
"""Captura administrativa de solo lectura. No importa ni inicia la aplicación."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
from zoneinfo import ZoneInfo


def comando(args, cwd=None):
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=6)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def base_mysql(url):
    # Sin app.config, init_db(), migraciones, consultas a secretos ni contenido de fotos.
    import pymysql
    from sqlalchemy.engine import make_url
    u = make_url(url)
    if not u.drivername.startswith(('mysql', 'mariadb')) or not u.database:
        raise ValueError('Se requiere una base MySQL identificada')
    permitidas = {'ssl_ca', 'ssl_cert', 'ssl_key', 'ssl_verify_cert', 'ssl_verify_identity', 'unix_socket'}
    opciones = {k: v for k, v in u.query.items() if k in permitidas}
    for k in ('ssl_verify_cert', 'ssl_verify_identity'):
        if k in opciones:
            opciones[k] = str(opciones[k]).lower() in ('true', '1', 'yes')
    con = pymysql.connect(host=u.host or 'localhost', port=u.port or 3306,
        user=u.username, password=u.password, database=u.database,
        charset=u.query.get('charset', 'utf8mb4'), connect_timeout=5,
        read_timeout=8, write_timeout=5, autocommit=True, **opciones)
    resultado = {'identidad': hashlib.sha256(
        f'{u.host}:{u.port or 3306}/{u.database}/{opciones.get("unix_socket", "")}'.encode()).hexdigest(),
        'tablas': [], 'avisos': []}
    try:
        with con.cursor(pymysql.cursors.DictCursor) as c:
            c.execute('SELECT VERSION() AS version')
            version = c.fetchone()['version']
            resultado['version'] = version
            c.execute('SET SESSION max_statement_time=5' if 'mariadb' in version.lower()
                      else 'SET SESSION MAX_EXECUTION_TIME=5000')
            c.execute('START TRANSACTION READ ONLY')
            c.execute('''SELECT TABLE_NAME AS nombre, TABLE_ROWS AS filas_estimadas,
                DATA_LENGTH AS datos_bytes, INDEX_LENGTH AS indices_bytes
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'
                ORDER BY TABLE_NAME''')
            resultado['tablas'] = [{k: int(v) if k != 'nombre' and v is not None else v
                                    for k, v in r.items()} for r in c.fetchall()]
            presentes = {r['nombre'] for r in resultado['tablas']}
            c.execute('''SELECT TABLE_NAME AS tabla, COLUMN_NAME AS columna, DATA_TYPE AS tipo
                FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
                AND DATA_TYPE IN ('blob','tinyblob','mediumblob','longblob','binary','varbinary')''')
            resultado['columnas_binarias'] = list(c.fetchall())
            consultas = {
                'archivos': ('app_archivos', '''SELECT tipo,
                    CASE WHEN drive_id IS NOT NULL AND drive_id<>'' THEN 'DRIVE' ELSE 'PENDIENTE' END AS destino,
                    COUNT(*) AS cantidad, COALESCE(SUM(bytes),0) AS contenido_bytes
                    FROM app_archivos GROUP BY tipo, destino'''),
                'entregas': ('app_entregas', '''SELECT estado, COUNT(*) AS cantidad
                    FROM app_entregas GROUP BY estado'''),
                'recepciones': ('app_recepciones', '''SELECT estado, COUNT(*) AS cantidad
                    FROM app_recepciones GROUP BY estado'''),
            }
            for nombre, (tabla, sql) in consultas.items():
                if tabla not in presentes:
                    resultado[nombre] = None
                    resultado['avisos'].append(f'{nombre}: tabla ausente')
                    continue
                try:
                    c.execute(sql)
                    resultado[nombre] = [{k: int(v) if k in ('cantidad', 'contenido_bytes') else v
                                           for k, v in r.items()} for r in c.fetchall()]
                except pymysql.MySQLError as exc:
                    resultado[nombre] = None
                    resultado['avisos'].append(f'{nombre}: consulta incompleta ({type(exc).__name__})')
    finally:
        try:
            con.rollback()
        finally:
            con.close()
    return resultado


def disco(data_dir):
    carpeta = data_dir / 'app_archivos'
    total = archivos = 0
    try:
        with os.scandir(carpeta) as entradas:
            for e in entradas:
                if archivos >= 100000:
                    return {'estado': 'limite', 'archivos': archivos, 'bytes': total}
                if e.is_file(follow_symlinks=False):
                    try:
                        total += e.stat(follow_symlinks=False).st_size
                        archivos += 1
                    except FileNotFoundError:  # El trabajador pudo completar una subida.
                        continue
        return {'estado': 'ok', 'archivos': archivos, 'bytes': total}
    except FileNotFoundError:
        return {'estado': 'carpeta_ausente', 'archivos': None, 'bytes': None}
    except OSError:
        return {'estado': 'sin_acceso', 'archivos': None, 'bytes': None}


def diferencia(actual, anterior):
    if actual.get('formato') != 1 or anterior.get('formato') != 1:
        raise ValueError('Formato de reporte incompatible')
    a, b = actual.get('mysql'), anterior.get('mysql')
    if not a or not b or not a.get('identidad') or a['identidad'] != b.get('identidad'):
        raise ValueError('No se pueden comparar bases distintas o sin diagnóstico MySQL')
    inicio = datetime.fromisoformat(anterior['capturado_utc'])
    fin = datetime.fromisoformat(actual['capturado_utc'])
    if fin <= inicio:
        raise ValueError('La captura final debe ser posterior a la inicial')
    previas = {t['nombre']: t for t in b['tablas']}
    tablas = []
    for t in a['tablas']:
        p = previas.get(t['nombre'])
        delta = {'nombre': t['nombre']}
        for campo in ('datos_bytes', 'indices_bytes', 'filas_estimadas'):
            delta[campo] = (t[campo] - p[campo]
                            if p and t.get(campo) is not None and p.get(campo) is not None else None)
        tablas.append(delta)
    total_a = [t.get(k) for t in a['tablas'] for k in ('datos_bytes', 'indices_bytes')]
    total_b = [t.get(k) for t in b['tablas'] for k in ('datos_bytes', 'indices_bytes')]
    total = (sum(total_a) - sum(total_b)
             if None not in total_a and None not in total_b else None)
    grupos = {}
    for seccion, claves in [('archivos', ('tipo', 'destino')),
                            ('entregas', ('estado',)), ('recepciones', ('estado',))]:
        if a.get(seccion) is None or b.get(seccion) is None:
            grupos[seccion] = None
            continue
        actuales = {tuple(f[k] for k in claves): f for f in a[seccion]}
        anteriores = {tuple(f[k] for k in claves): f for f in b[seccion]}
        grupos[seccion] = []
        for clave in sorted(actuales.keys() | anteriores.keys()):
            fila = dict(zip(claves, clave))
            for campo in ('cantidad', 'contenido_bytes') if seccion == 'archivos' else ('cantidad',):
                fila[campo] = actuales.get(clave, {}).get(campo, 0) - anteriores.get(clave, {}).get(campo, 0)
            grupos[seccion].append(fila)
    return {'desde': anterior['capturado_ecuador'], 'hasta': actual['capturado_ecuador'],
            'segundos': (fin - inicio).total_seconds(), 'asignacion_mysql_bytes': total,
            'tablas': tablas, 'cambio_por_estado': grupos,
            'tablas_ausentes_al_final': sorted(set(previas) - {t['nombre'] for t in a['tablas']})}


def markdown(r):
    lineas = ['# Estado de IV_ITSANET', '', r['capturado_ecuador'] + ' (Ecuador)', '',
        f"Servicio: {r['servicio'] or 'no disponible'}",
        f"Salud HTTP: {r['salud']}", f"Commit: {r['commit'] or 'no disponible'}", '',
        'Las cifras de MySQL son asignación estimada de datos/índices; las filas de InnoDB',
        'son estimaciones, no conteos exactos. No representan el disco total del servidor.', '']
    db = r.get('mysql')
    if db:
        lineas += ['| Tabla | Filas estimadas | Datos (bytes) | Índices (bytes) |',
                   '|---|---:|---:|---:|']
        for t in db['tablas']:
            lineas.append('| ' + ' | '.join(str(t[k]) for k in
                          ('nombre', 'filas_estimadas', 'datos_bytes', 'indices_bytes')) + ' |')
        for clave in ('archivos', 'entregas', 'recepciones'):
            lineas += ['', f'## {clave.capitalize()}', '',
                       '```json', json.dumps(db.get(clave), ensure_ascii=False, indent=2), '```']
        lineas += ['', 'Columnas binarias detectadas (no se leen contenidos):',
                   '```json', json.dumps(db['columnas_binarias'], ensure_ascii=False), '```']
    else:
        lineas += ['MySQL no disponible. Esta captura no permite medir crecimiento.']
    lineas += ['', '## Archivos locales temporales e informes', '',
               '```json', json.dumps(r['disco'], ensure_ascii=False), '```', '',
               'Los bytes de archivos son contenido multimedia/informes, no bytes dentro de MySQL.',
               'DRIVE indica ID confirmado en MySQL; no verifica hoy la disponibilidad del archivo remoto.',
               'Las fotos pendientes se copian al cerrar la recepción. No se prueba ni envía correo.',
               'Las secciones se capturan consecutivamente mientras continúa la operación.']
    if 'comparacion' in r:
        d = r['comparacion']
        lineas += ['', '## Cambio desde la captura inicial', '',
            f"Desde: {d['desde']} — Hasta: {d['hasta']}",
            f"Cambio de asignación MySQL (bytes): {d['asignacion_mysql_bytes']}", '',
            '```json', json.dumps(d['tablas'], ensure_ascii=False, indent=2), '```',
            'Cambios de cantidades por estado (pueden bajar al pasar de pendiente a Drive):',
            '```json', json.dumps(d['cambio_por_estado'], ensure_ascii=False, indent=2), '```',
            'Tablas ausentes al final: ' + ', '.join(d['tablas_ausentes_al_final']),
            'Un cambio de 0 bytes no significa ausencia de registros: InnoDB reutiliza páginas.',
            'El JSON conserva ambas clases de métricas para comparar fotos, recepciones y entregas.']
    lineas += ['', '## Avisos', ''] + ['- ' + aviso for aviso in r['avisos'] + (db or {}).get('avisos', [])]
    return '\n'.join(lineas) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--salida', type=Path, required=True)
    p.add_argument('--comparar', type=Path)
    p.add_argument('--health', default='http://127.0.0.1:3002/health')
    args = p.parse_args()
    if not re.fullmatch(r'https?://(127\.0\.0\.1|localhost):[0-9]+/health', args.health):
        p.error('--health debe ser el /health local, sin credenciales')
    os.umask(0o077)
    ahora = datetime.now(timezone.utc)
    r = {'formato': 1, 'capturado_utc': ahora.isoformat(),
         'capturado_ecuador': ahora.astimezone(ZoneInfo('America/Guayaquil')).isoformat(),
         'avisos': [], 'mysql': None,
         'commit': comando(['git', 'rev-parse', 'HEAD'], args.repo),
         'servicio': comando(['systemctl', 'show', 'iv-itsanet', '-p', 'ActiveState',
                              '-p', 'SubState', '-p', 'Result', '-p', 'NRestarts'])}
    try:
        with urllib.request.urlopen(args.health, timeout=5) as res:
            datos = json.loads(res.read(4096))
            r['salud'] = 'ok' if res.status == 200 and datos.get('ok') is True else 'respuesta inesperada'
    except Exception as exc:
        r['salud'] = 'sin confirmar (' + type(exc).__name__ + ')'
    try:
        r['mysql'] = base_mysql(os.environ.get('VAL_DATABASE_URL', ''))
    except Exception as exc:
        r['avisos'].append('MySQL no consultado: ' + type(exc).__name__ + ' (sin exponer credenciales)')
    r['disco'] = disco(Path(os.environ.get('VAL_DATA_DIR') or args.repo / 'data'))
    if args.comparar:
        try:
            r['comparacion'] = diferencia(r, json.loads(args.comparar.read_text()))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            r['avisos'].append('Comparación rechazada: ' + type(exc).__name__)
    args.salida.mkdir(parents=True, exist_ok=True, mode=0o700)
    nombre = ahora.strftime('estado-%Y%m%dT%H%M%S%fZ')
    for extension, contenido in [('json', json.dumps(r, ensure_ascii=False, indent=2)), ('md', markdown(r))]:
        destino = args.salida / (nombre + '.' + extension)
        with destino.open('x') as archivo:
            archivo.write(contenido)
        print(destino)
    return 0 if r['mysql'] and (not args.comparar or 'comparacion' in r) else 2


if __name__ == '__main__':
    raise SystemExit(main())
