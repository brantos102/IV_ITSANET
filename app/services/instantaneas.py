"""Comprimir las copias inmutables de cierre; nunca fotos ni claves."""
import base64
import gzip
import hashlib
import io
import json
import zlib

CAMPOS = {'skus', 'lineas', 'eventos', 'recepcion', 'resumen'}
LIMITE = 32 * 1024 * 1024


def expandir(datos):
    ref = datos.get('instantaneaGzip')
    if not ref:
        return dict(datos)  # Compatible con las entregas anteriores.
    try:
        if ref.get('version') != 1:
            raise ValueError('version')
        with gzip.GzipFile(fileobj=io.BytesIO(base64.b64decode(ref['contenido'], validate=True))) as f:
            bruto = f.read(LIMITE + 1)
        if len(bruto) > LIMITE or hashlib.sha256(bruto).hexdigest() != ref['sha256']:
            raise ValueError('integridad')
        original = json.loads(bruto)
        if not isinstance(original, dict) or set(original) - CAMPOS:
            raise ValueError('estructura')
        return {**original, **{k: v for k, v in datos.items() if k != 'instantaneaGzip'}}
    except (ValueError, KeyError, TypeError, OSError, EOFError, zlib.error, AttributeError):
        raise RuntimeError('La instantánea del informe está dañada. Revisa el respaldo antes de enviar; los conteos originales se conservan.') from None


def compactar(datos):
    if not CAMPOS.intersection(datos):
        return dict(datos)
    datos = expandir(datos)
    original = {k: datos[k] for k in CAMPOS if k in datos}
    bruto = json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if len(bruto) > LIMITE:
        raise RuntimeError('El informe supera el tamaño permitido de instantánea; revisa las listas antes de enviar.')
    return {**{k: v for k, v in datos.items() if k not in CAMPOS},
        'instantaneaGzip': {'version': 1, 'sha256': hashlib.sha256(bruto).hexdigest(),
            'bytes': len(bruto), 'contenido': base64.b64encode(gzip.compress(bruto, mtime=0)).decode()}}
