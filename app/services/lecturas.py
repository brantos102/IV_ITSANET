"""Extraer piezas de QR y sugerir correcciones sin cambiar dígitos en silencio."""
import json
import re
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.models import AppSku, Producto
from app.services.codigos import buscar
from app.services.normalize import normalizar_sku


def distancia(a,b):
    """Edición con transposición adyacente; solo ordena sugerencias revisables."""
    filas=[list(range(len(b)+1))]
    for i,x in enumerate(a,1):
        fila=[i]
        for j,y in enumerate(b,1):
            n=min(filas[-1][j]+1,fila[-1]+1,filas[-1][j-1]+(x!=y))
            if i>1 and j>1 and x==b[j-2] and a[i-2]==y:n=min(n,filas[-2][j-2]+1)
            fila.append(n)
        filas.append(fila)
    return filas[-1][-1]

CLAVES = {'sku', 'partnumber', 'partno', 'pn', 'numerodepieza', 'numeropieza', 'codigo', 'codigoproducto'}


COMILLAS = "'’‘`´\"“”"


def _pieza(texto):
    # Algunos lectores entregan apóstrofos en lugar de guiones. Solo se aplica
    # a candidatos de lectura, nunca cambia la identidad guardada del producto.
    texto = re.sub('[‐‑‒–—−]', '-', str(texto))
    return normalizar_sku(texto.translate(str.maketrans('', '', COMILLAS)))


def _extraer(raw):
    texto = str(raw or '').strip()
    if not texto or len(texto) > 8192:
        raise HTTPException(422, 'Lectura vacía o demasiado larga')
    texto = re.sub(r'^\][A-Za-z][0-9]', '', texto)
    piezas = []
    d = None
    try:
        d = json.loads(texto)
        if isinstance(d, dict):
            piezas += [str(v) for k, v in d.items() if re.sub('[^a-z]', '', k.lower()) in CLAVES and isinstance(v, (str, int))]
    except (ValueError, TypeError):
        pass
    try:
        uri = urlparse(texto)
    except ValueError:
        return [], True
    if uri.scheme in ('http', 'https'):
        piezas += [v for k, vs in parse_qs(uri.query).items()
            if re.sub('[^a-z]', '', k.lower()) in CLAVES for v in vs]
    piezas += re.findall(r'(?:SKU|PART\s*(?:NUMBER|NO\.?|#)|P\s*/\s*N|N[ÚU]MERO\s+DE\s+PIEZA)\s*[:=]\s*([A-Z0-9][A-Z0-9_.\-\'’‘`´"]{0,79})', texto, re.I)
    piezas += re.findall(r'\(240\)([A-Z0-9_.-]+)', texto, re.I)
    piezas += re.findall(r'(?:^|\x1d)240([A-Z0-9_.-]{1,30})(?=\x1d|$)', texto, re.I)
    piezas += re.findall(r'\(01\)(\d{14})', texto)
    estructurada = bool(piezas) or isinstance(d, (dict, list)) or uri.scheme in ('http', 'https')
    compuesta = False
    if not estructurada:
        # Conservar también el código completo: sus ceros pueden ser reales.
        # Los campos numéricos posteriores son lote/relleno, no otro SKU.
        campos = re.split(r'[\s;|,\x1d]+', texto)
        compuesta = len(campos) > 1
        permitidos = r'[A-Za-z0-9_.\-/\s\'’‘`´"“”‐‑‒–—−]{1,100}'
        if re.fullmatch(permitidos, texto):
            piezas.append(texto)
        for i, campo in enumerate(campos):
            limpio = _pieza(campo)
            if (re.fullmatch(r'[A-Za-z0-9_.\-/\'’‘`´"“”‐‑‒–—−]{4,80}', campo)
                    and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', campo)
                    and (i == 0 or (re.search('[A-Za-z]', limpio) and re.search('[0-9]', limpio)))):
                piezas.append(campo)
        # El teclado del lector puede separar también las partes del SKU.
        # Probar el prefijo anterior al relleno conserva todos sus dígitos;
        # solo se aceptará si el código completo existe realmente.
        if len(campos) > 2 and re.fullmatch(permitidos, texto):
            for i in range(2, min(len(campos), 12)):
                if re.fullmatch(r'\d{5,}', _pieza(''.join(campos[i:]))):
                    piezas.append(''.join(campos[:i]))
    candidatos = (_pieza(p) for p in piezas)
    return list(dict.fromkeys(p for p in candidatos if 0 < len(p) <= 100))[:50], compuesta


def extraer(raw):
    return _extraer(raw)[0]


def _similares(db, piezas, recepcion):
    """Una inserción, omisión o sustitución: consulta acotada al catálogo.

    LIKE usa un comodín de un carácter en cada posición y limita las respuestas.
    No se descarga el maestro. Ningún candidato se convierte en equivalencia.
    """
    patrones, exactos = set(), set()
    for p in piezas[:4]:
        if not re.fullmatch(r'[A-Z0-9]{5,40}', p) or not re.search('[A-Z]', p):
            continue
        for i in range(len(p)):
            patrones.add(p[:i] + '_' + p[i+1:])
            exactos.add(p[:i] + p[i+1:])
        for i in range(len(p)+1):
            patrones.add(p[:i] + '_' + p[i:])
    if not patrones:
        return set()
    def condicion(col):
        return or_(col.in_(sorted(exactos)), *(col.like(p) for p in sorted(patrones)))
    candidatos = set(db.scalars(select(Producto.sku).where(condicion(Producto.sku))
        .order_by(Producto.sku).limit(9)))
    if recepcion:
        # La lista de esta recepción tiene prioridad. Incluye dos movimientos
        # de dígitos, sin descargar el catálogo completo ni aceptar el cambio.
        for sku in db.scalars(select(AppSku.sku).where(AppSku.recepcion==recepcion,AppSku.en_packing_list.is_(True))):
            if any(abs(len(sku)-len(p))<=2 and distancia(p,sku)<=2 for p in piezas[:4]):candidatos.add(sku)
    return candidatos


def _detalles(db, candidatos, recepcion):
    productos = {p.sku:p for p in db.scalars(select(Producto).where(Producto.sku.in_(candidatos)))}
    en_lista = set(db.scalars(select(AppSku.sku).where(AppSku.recepcion == recepcion,
        AppSku.en_packing_list.is_(True),AppSku.sku.in_(candidatos)))) if recepcion else set()
    return [{'sku':s, 'descripcion':productos[s].descripcion or '' if s in productos else '',
        'cliente':productos[s].cliente if s in productos else '',
        'enCatalogo':s in productos, 'existeDepot':bool(productos[s].existe_depot) if s in productos else False,
        'enPackingList':s in en_lista} for s in candidatos]


def resolver(db, raw, recepcion=None):
    piezas, compuesta = _extraer(raw)
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
            'motivo': ('SKU confirmado en packing list o catálogo. Se separaron los campos adicionales de la etiqueta y se normalizaron los separadores.'
                       if compuesta else 'Número de pieza confirmado; separadores normalizados o equivalencia registrada.')}
    if len(encontrados) > 1:
        return {'resuelto': False, 'confirmar': True, 'candidatos': sorted(encontrados),
            'detallesCandidatos': _detalles(db, sorted(encontrados), recepcion),
            'motivo': 'La lectura contiene varios códigos existentes; selecciona el producto'}
    candidatos = set()
    for p in piezas:
        variantes = {p.lstrip('0')} if p.startswith('0') else set()
        variantes.update(p[1:] for prefijo in ('P', '1') if p.startswith(prefijo))
        # Sin límite de campo no sabemos si los ceros pertenecen a la pieza:
        # ofrecer solo códigos existentes y exigir confirmación, nunca recortar.
        variantes.update(p[:i] for i in range(4, len(p) - 2) if set(p[i:]) == {'0'})
        # Lote/cantidad pegados por el lector: proponer el prefijo existente,
        # exigir confirmación y conservar íntegro el código original.
        variantes.update(p[:i] for i in range(5, len(p)-4) if p[i:].isdigit())
        for v in variantes:
            if not v: continue
            prod = buscar(db, v)
            if prod: candidatos.add(prod.sku)
            if recepcion and db.scalar(select(AppSku.id).where(AppSku.recepcion == recepcion, AppSku.sku == v)):
                candidatos.add(v)
    # Dígitos diferentes no se depuran. Se presentan como sugerencia, jamás equivalencia automática.
    if not candidatos:
        candidatos = _similares(db, piezas, recepcion)
    en_lista=set(db.scalars(select(AppSku.sku).where(AppSku.recepcion==recepcion,AppSku.en_packing_list.is_(True),AppSku.sku.in_(candidatos)))) if recepcion else set()
    candidatos = sorted(candidatos,key=lambda s:(s not in en_lista,
        not any(sorted(s)==sorted(p) for p in piezas[:4]),min((distancia(p,s) for p in piezas[:4]),default=100),s))[:8]
    return {'sku': piezas[0] if len(piezas) == 1 and not compuesta else None, 'resuelto': False,
        'confirmar': bool(candidatos), 'candidatos': candidatos,
        'detallesCandidatos': _detalles(db, candidatos, recepcion),
        'motivo': 'Posible prefijo, ceros de relleno o diferencia de caracteres. Requiere confirmación.'
                  if candidatos else 'No se identificó un SKU existente. Escanea solo el número de pieza o escríbelo sin lote, cantidad ni relleno; vuelve a buscar antes de crear un adicional.'}
