"""Embarque de cada vínculo fotográfico, independiente del archivo packing list.

La asignación explícita se guarda en la identidad existente del archivo; no hay
otra copia del binario ni una migración de tablas.
"""
from fastapi import HTTPException
import hashlib
from sqlalchemy import select
from app.models import AppArchivoIdentidad
from app.services import app_modelo as m


def informacion(db, codigo, *, actual=False):
    from app.services.agrupacion_correo import configuracion, embarque
    from app.models import AppLinea
    r = m.obtener(db, codigo)
    # La autenticación pudo abrir un snapshot antes de esperar el bloqueo
    # de recepción; usar el plan que el supervisor acaba de confirmar.
    c = configuracion(db, r.codigo,actual=actual)
    # Leer solo la identificación; no cargar las celdas originales del Excel
    # por cada imagen ni bloquear sus filas para mostrar una galería.
    q=select(AppLinea.origen,AppLinea.linea,AppLinea.sku,AppLinea.extra['embarque'].as_string()).where(AppLinea.recepcion==r.codigo)
    if actual:q=q.with_for_update()
    lineas=[{'id':f'{o}-{n}','origen':o,'linea':n,'sku':sku,'embarque':emb} for o,n,sku,emb in db.execute(q)]
    todos = sorted({str(x).strip().upper() for x in (r.embarques or []) if str(x).strip()}
        | {embarque(l, c) for l in lineas if embarque(l, c)})
    return r,c,lineas,todos


def contexto(db, codigo, sku='', origen='', unidad_id='', *, fuente=None, actual=False):
    from app.services.agrupacion_correo import embarque
    from app.models import AppUnidadLogistica
    r,c,lineas,todos = fuente or informacion(db,codigo,actual=actual)
    propias = lineas
    filtrar = bool(origen or sku)
    if origen:
        propias = [l for l in propias if (l.get('origen') or 'PRINCIPAL') == origen]
    if sku:
        propias = [l for l in propias if l['sku'] == m.normalizar_codigo(sku)]
    if unidad_id:
        u = db.get(AppUnidadLogistica, unidad_id)
        if not u or u.recepcion != r.codigo:
            raise HTTPException(422, 'La unidad no pertenece a esta recepción.')
        if u.padre_id:
            padre = db.get(AppUnidadLogistica, u.padre_id)
        else:
            padre = None
        origenes = (u.datos or {}).get('origenes') or ((padre.datos or {}).get('origenes') if padre else [])
        if origenes:
            filtrar = True
            propias = [l for l in propias if (l.get('origen') or 'PRINCIPAL') in origenes]
    candidatos = (sorted({embarque(l, c) for l in propias if embarque(l, c)}) or todos) if filtrar else todos
    return {'embarques': todos, 'candidatos': candidatos,
        'sugerido': candidatos[0] if len(candidatos) == 1 else '',
        'permiteGeneral': True, 'origenes': r.origenes or []}


def resolver(db, codigo, datos):
    p = contexto(db, codigo, datos.get('sku') or '', datos.get('origen') or '', datos.get('unidadId') or '',actual=True)
    if 'embarqueFoto' not in datos:
        return p['sugerido'] or None
    valor = datos['embarqueFoto']
    if not isinstance(valor, str) or len(valor) > 80:
        raise HTTPException(422, 'Selecciona un embarque válido para la foto.')
    valor = valor.strip().upper()
    if not valor and p['permiteGeneral']:
        return ''
    if valor not in p['candidatos']:
        raise HTTPException(422, 'El embarque de la foto no corresponde a este SKU, packing list o bulto. Actualiza y selecciona su destino.')
    return valor


def asignado(db, e, *, fuente=None):
    if not e:
        return None
    identidad = db.get(AppArchivoIdentidad, e.archivo_id)
    mapa = (identidad.datos or {}).get('embarquesPorEvidencia', {}) if identidad else {}
    if e.id in mapa:
        elegido=mapa[e.id]
        if elegido=='':return ''  # General es una decisión explícita.
        return elegido if elegido in contexto(db,e.recepcion,e.sku or '',e.origen or '',e.unidad_id or '',fuente=fuente)['candidatos'] else None
    return contexto(db, e.recepcion, e.sku or '', e.origen or '', e.unidad_id or '',fuente=fuente)['sugerido'] or None


def registrar(db, archivo_id, evidencia_id, embarque):
    if embarque is None:
        return
    identidad = db.get(AppArchivoIdentidad, archivo_id)
    if identidad:
        identidad.datos = {**identidad.datos, 'embarquesPorEvidencia': {
            **identidad.datos.get('embarquesPorEvidencia', {}), evidencia_id: embarque}}


def ruta(db, e, *, con_bulto=True, fuente=None):
    from app.services.drive import ruta_evidencia
    from app.services.fotos_identidad import ruta_bulto, componente
    bulto = ruta_bulto(db, e) if con_bulto else []
    base = bulto + (ruta_evidencia(e) if e and e.sku else []) if bulto else ruta_evidencia(e)
    emb = asignado(db, e,fuente=fuente)
    if emb:
        carpeta = componente(emb, 90)
        if carpeta != emb or emb == 'POR-ASIGNAR':
            carpeta += '-' + hashlib.sha256(emb.encode()).hexdigest()[:10]
        return ['EMBARQUES', carpeta] + base
    if e and contexto(db, e.recepcion,fuente=fuente)['embarques']:
        # Nunca repartir una foto histórica ambigua entre embarques por intuición.
        return (['EMBARQUES', 'POR-ASIGNAR'] if emb is None and (e.sku or e.unidad_id) else ['GENERALES']) + base
    return base
