"""Revisar metadatos de archivos ya importados sin reimportar ni sumar cantidades."""
import hashlib
import json
import unicodedata
from collections import Counter
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppLinea, AppEntrega
from app.services import app_modelo as m, ajustes


def _columna(encabezados, nombres):
    for nombre in nombres:
        for i, texto in enumerate(encabezados):
            normal = ''.join(c for c in unicodedata.normalize('NFD', str(texto)).upper() if c.isalnum())
            if normal == nombre: return i
    return None


def analizar(db, codigo, *, actual=False):
    r = m.obtener(db, codigo)
    consulta = select(AppLinea).where(AppLinea.recepcion == r.codigo).order_by(AppLinea.orden, AppLinea.id)
    if actual: consulta = consulta.with_for_update().execution_options(populate_existing=True)
    lineas = list(db.scalars(consulta))
    cambios, por_lista, errores = [], {}, []
    for l in lineas:
        encabezados = (r.formatos or {}).get(m.clave_mapa(l.origen), {}).get('encabezados', [])
        idx = {k: _columna(encabezados, ns) for k, ns in {
            'sku': ['NUMERODEPIEZA', 'NUMERODEPARTE', 'SKU', 'CODPRODUCTO', 'ITEM'],
            'cantidad': ['CANTIDAD', 'QTY', 'QUANTITY'], 'embarque': ['EMBARQUE', 'SHIPMENT'],
            'contenedor': ['NOMBRECONTENEDOR', 'CONTENEDOR', 'NUMEROCONTENEDOR', 'CONTAINER'],
            'factura': ['FACTURA', 'INVOICE']}.items()}
        cruda = (l.extra or {}).get('cruda', [])
        def celda(k):
            return str(cruda[idx[k]]).strip() if idx[k] is not None and idx[k] < len(cruda) else ''
        # La reparación es solo de identificación logística; nunca reconstruye
        # filas ni cantidades desde un resumen o una fuente incompleta.
        if idx['embarque'] is None: continue
        if idx['sku'] is None or idx['cantidad'] is None or not cruda or m.normalizar_codigo(celda('sku')) != l.sku or m.a_numero(celda('cantidad'), -1) != float(l.cantidad):
            errores.append({'origen': l.origen, 'linea': l.linea}); continue
        nueva = {k: celda(k).upper() if k != 'factura' else celda(k) for k in ('embarque', 'contenedor', 'factura') if idx[k] is not None}
        if any(len(v) > (20 if k == 'contenedor' else 80) for k, v in nueva.items()):
            errores.append({'origen': l.origen, 'linea': l.linea}); continue
        nodo = por_lista.setdefault(l.origen, {'actual': Counter(), 'propuesto': Counter()})
        nodo['actual'][str((l.extra or {}).get('embarque') or 'SIN EMBARQUE')] += 1
        nodo['propuesto'][nueva.get('embarque') or 'SIN EMBARQUE'] += 1
        if any(str((l.extra or {}).get(k) or '') != v for k, v in nueva.items()): cambios.append((l, nueva))
    huella = hashlib.sha256(json.dumps([r.formatos, [(l.id, l.sku, str(l.cantidad), l.extra) for l in lineas]], sort_keys=True).encode()).hexdigest()
    return {'version': huella, 'lineasPorCorregir': len(cambios), 'listas': por_lista,
        'errores': errores[:20], 'puedeAplicar': bool(cambios) and not errores}, cambios, lineas


def vista(db, codigo): return analizar(db, codigo)[0]


def aplicar(db, codigo, datos, usuario):
    r = m.obtener(db, codigo, bloquear=True)
    previo, cambios, lineas = analizar(db, r.codigo, actual=True)
    if datos.get('version') != previo['version']: raise HTTPException(409, 'Cambió el packing list. Revisa de nuevo la comparación.')
    if datos.get('confirmar') is not True: raise HTTPException(422, 'Confirma la corrección de metadatos después de revisar la comparación.')
    if not previo['puedeAplicar']: raise HTTPException(409, 'No hay una corrección verificable. No se modificaron las líneas.')
    if db.scalar(select(AppEntrega.id).where(AppEntrega.recepcion == r.codigo, AppEntrega.estado.in_(['PENDIENTE', 'PROCESANDO', 'REVISION'])).limit(1)):
        raise HTTPException(409, 'Resuelve o cancela las entregas pendientes antes de corregir los embarques. Los correos archivados no se reescriben.')
    anteriores = list(r.embarques or [])
    for l, nueva in cambios: l.extra = {**(l.extra or {}), **nueva}
    formatos=dict(r.formatos or {})
    for origen in {l.origen for l,_ in cambios}:
        llave=m.clave_mapa(origen)
        firma=hashlib.sha256(json.dumps([(l.id,n) for l,n in cambios if l.origen==origen],sort_keys=True).encode()).hexdigest()
        formatos[llave]={**formatos.get(llave,{}),'revisionLogistica':firma}
    r.formatos=formatos
    r.embarques = sorted({str((l.extra or {}).get('embarque') or '').strip().upper() for l in lineas} - {''})
    ajustes.auditar(db, usuario, 'LECTURA_PACKING_CORREGIDA', r.codigo, {'lineas': len(cambios),
        'embarquesAnteriores': anteriores, 'embarques': r.embarques, 'versionOrigen': previo['version'], 'cantidadesModificadas': False})
    db.commit()
    return {'corregidas': len(cambios), 'embarques': r.embarques,
        'mensaje': 'Identificación corregida sin sumar ni borrar cantidades. Revisa el reparto de correos y las fotos por embarque antes de generar nuevos informes. Los archivos y envíos históricos se conservan.'}
