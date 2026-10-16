"""Extraer piezas de QR y sugerir correcciones sin cambiar dígitos en silencio."""
import json
import re
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
from sqlalchemy import select

from app.models import AppSku, Producto
from app.services.codigos import buscar
from app.services.normalize import normalizar_sku

CLAVES = {'sku', 'partnumber', 'partno', 'pn', 'numerodepieza', 'numeropieza', 'codigo', 'codigoproducto'}


def extraer(raw):
    texto = str(raw or '').strip()
    if not texto or len(texto) > 8192:
        raise HTTPException(422, 'Lectura vacía o demasiado larga')
    texto = re.sub(r'^\][A-Za-z][0-9]', '', texto)
    piezas = []
    try:
        d = json.loads(texto)
        if isinstance(d, dict):
            piezas += [str(v) for k, v in d.items() if re.sub('[^a-z]', '', k.lower()) in CLAVES and isinstance(v, (str, int))]
    except (ValueError, TypeError):
        pass
    uri = urlparse(texto)
    if uri.scheme in ('http', 'https'):
        piezas += [v for k, vs in parse_qs(uri.query).items()
            if re.sub('[^a-z]', '', k.lower()) in CLAVES for v in vs]
    piezas += re.findall(r'(?:SKU|PART\s*(?:NUMBER|NO\.?|#)|P\s*/\s*N|N[ÚU]MERO\s+DE\s+PIEZA)\s*[:=]\s*([A-Z0-9][A-Z0-9_.-]{0,79})', texto, re.I)
    piezas += re.findall(r'\(240\)([A-Z0-9_.-]+)', texto, re.I)
    piezas += re.findall(r'(?:^|\x1d)240([A-Z0-9_.-]{1,30})(?=\x1d|$)', texto, re.I)
    piezas += re.findall(r'\(01\)(\d{14})', texto)
    if not piezas and re.fullmatch(r'[\w\s.\-/]+', texto) and len(texto) <= 100:
        piezas = [texto]
    # QR sin claves: solo candidatos completos que existan. Nunca tomar cantidad/fecha como SKU.
    if not piezas:
        piezas = [p for p in re.split(r'[\s;|,\x1d]+', texto) if re.fullmatch(r'[A-Za-z0-9_.-]{4,80}', p)
                  and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', p)]
    return list(dict.fromkeys(normalizar_sku(p) for p in piezas if normalizar_sku(p)))[:50]


def resolver(db, raw, recepcion=None):
    piezas = extraer(raw)
    encontrados = {}
    for p in piezas:
        producto = buscar(db, p)
        sku = producto.sku if producto else p
        en_lista = db.scalar(select(AppSku.sku).where(AppSku.recepcion == recepcion, AppSku.sku == sku)) if recepcion else None
        if producto or en_lista:
            encontrados[sku] = p
    if len(encontrados) == 1:
        sku = next(iter(encontrados))
        return {'sku': sku, 'resuelto': True, 'confirmar': False, 'candidatos': [],
            'transformado': str(raw).strip().upper() != sku,
            'motivo': 'Extracción de número de pieza / normalización de separadores o equivalencia registrada'}
    if len(encontrados) > 1:
        return {'resuelto': False, 'confirmar': True, 'candidatos': sorted(encontrados),
            'motivo': 'La lectura contiene varios códigos existentes; selecciona el producto'}
    candidatos = set()
    for p in piezas:
        variantes = {p.lstrip('0')} if p.startswith('0') else set()
        variantes.update(p[1:] for prefijo in ('P', '1') if p.startswith(prefijo))
        for v in variantes:
            if not v: continue
            prod = buscar(db, v)
            if prod: candidatos.add(prod.sku)
            if recepcion and db.scalar(select(AppSku.id).where(AppSku.recepcion == recepcion, AppSku.sku == v)):
                candidatos.add(v)
    # Dígitos diferentes no se depuran. Se presentan como sugerencia, jamás equivalencia automática.
    if recepcion and not candidatos and len(piezas) == 1:
        for sku in db.scalars(select(AppSku.sku).where(AppSku.recepcion == recepcion)):
            p = piezas[0]
            if len(sku) == len(p) and sum(a != b for a, b in zip(sku, p)) == 1:
                candidatos.add(sku)
                if len(candidatos) >= 8: break
    return {'sku': piezas[0] if len(piezas) == 1 else None, 'resuelto': False,
        'confirmar': bool(candidatos), 'candidatos': sorted(candidatos),
        'motivo': 'Posible prefijo, ceros de relleno o diferencia de caracteres. Requiere confirmación.'
                  if candidatos else 'No se identificó un SKU existente; revisa la lectura antes de crear un adicional'}
