#!/usr/bin/env python3
"""Puente saliente a una Zebra de red. Config JSON local: servidor, estacion, token."""
import argparse
import json
import os
from pathlib import Path
import socket
import time
from urllib.parse import urlparse

import httpx


def persistir(ruta, dato):
    ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = ruta.with_suffix('.tmp')
    with tmp.open('w') as f:
        os.chmod(tmp, 0o600)
        json.dump(dato, f)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, ruta)


def ciclo(config, carpeta, http, equipo=None):
    endpoint = config['servidor'].rstrip('/') + '/api/impresion/agente/' + config['estacion']
    headers = {'Authorization': 'Bearer ' + config['token']}
    for f in carpeta.glob('*.json'):
        d = json.loads(f.read_text())
        if d.get('confirmada'): continue
        if d.get('estado') not in ('ENVIADA', 'REVISION'):
            d['estado'] = 'REVISION'  # Se interrumpió antes de confirmar el envío, no repetir.
        r = http.post(endpoint + '/confirmar', json=d, headers=headers)
        r.raise_for_status()
        d['confirmada'] = True; persistir(f, d)
    r = http.post(endpoint + '/siguiente', json={'equipo': equipo or socket.gethostname()}, headers=headers)
    r.raise_for_status()
    j = r.json().get('trabajo')
    if not j: return False
    ruta = carpeta / (j['id'] + '.json')
    if ruta.exists(): return False
    d = {'id': j['id'], 'reserva': j['reserva'], 'estado': 'ENVIANDO'}
    persistir(ruta, d)  # Antes del socket: un reinicio no puede repetir etiquetas.
    try:
        with socket.create_connection((j['host'], int(j['puerto'])), timeout=10) as s:
            s.sendall(j['zpl'].encode('utf-8'))
        d['estado'] = 'ENVIADA'
    except OSError:
        d['estado'] = 'REVISION'
    persistir(ruta, d)
    r = http.post(endpoint + '/confirmar', json=d, headers=headers)
    r.raise_for_status()
    d['confirmada'] = True; persistir(ruta, d)
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--registro', type=Path, required=True)
    p.add_argument('--una-vez', action='store_true')
    args = p.parse_args()
    c = json.loads(args.config.read_text())
    u = urlparse(c['servidor'])
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise SystemExit('URL del servidor inválida')
    if not c.get('token') or not c.get('estacion'): raise SystemExit('Faltan estación o token')
    args.registro.mkdir(parents=True, exist_ok=True, mode=0o700)
    with httpx.Client(timeout=15) as http:
        while True:
            try: ciclo(c, args.registro, http, c.get('equipo'))
            except (httpx.HTTPError, OSError, ValueError):
                print('Puente pendiente de conexión o configuración; se reintentará.', flush=True)
                if args.una_vez: return 2
            if args.una_vez: return 0
            time.sleep(2)


if __name__ == '__main__':
    raise SystemExit(main())
