"""Distribución opcional por contenedor; no altera cantidades ni packing lists."""
import hashlib
import json
import re

from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppConfig, AppEntrega, utcnow
from app.services import app_modelo as m, ajustes


def clave(codigo):
    return 'contenedores:' + hashlib.sha256(codigo.encode()).hexdigest()[:27]


def vista(db, codigo, *, actual=False):
    r = m.obtener(db, codigo)
    consulta = select(AppConfig).where(AppConfig.clave == clave(r.codigo))
    if actual: consulta = consulta.with_for_update().execution_options(populate_existing=True)
    f = db.scalar(consulta)
    guardado = f.datos if f else {}
    lineas = m.leer_coleccion(db, r.codigo, 'lineas', actual=actual)
    from app.services.agrupacion_correo import configuracion, embarque
    plan=configuracion(db,r.codigo,actual=actual)
    detectados = {}
    for l in lineas:
        numero = str(l.get('contenedor') or '').strip().upper()
        if not numero: continue
        d = detectados.setdefault(numero, {'numero': numero, 'embarques': set(), 'lineas': 0})
        if embarque(l,plan): d['embarques'].add(embarque(l,plan))
        d['lineas'] += 1
    candidatos = [{**d, 'embarques': sorted(d['embarques'])} for d in detectados.values()]
    embarques = sorted({embarque(l,plan) for l in lineas if embarque(l,plan)})
    version = hashlib.sha256(json.dumps([guardado, candidatos, embarques], sort_keys=True).encode()).hexdigest()
    return {'filas': guardado.get('filas', []), 'detectados': candidatos, 'embarques': embarques,
            'version': version, 'modificadoPor': guardado.get('usuario'), 'modificadoEn': guardado.get('fecha')}


def para_embarques(db, codigo, embarques=None):
    filas = vista(db, codigo)['filas']
    if embarques is not None and not embarques and len(m.obtener(db,codigo).origenes or [])<=1:
        return [f for f in filas if not f['embarques']]
    return [f for f in filas if embarques is None or set(f['embarques']) & set(embarques)]


def guardar(db, codigo, datos, usuario):
    r = m.obtener(db, codigo, bloquear=True)
    if db.scalar(select(AppEntrega.id).where(AppEntrega.recepcion == r.codigo, AppEntrega.estado == 'PROCESANDO').limit(1)):
        raise HTTPException(409, 'Hay un correo en proceso. Espera su confirmación antes de modificar la distribución.')
    anterior = vista(db, r.codigo, actual=True)
    if datos.get('version') != anterior['version']:
        raise HTTPException(409, 'Otro supervisor cambió la distribución o el packing list. Actualiza antes de guardar.')
    filas = datos.get('filas')
    if not isinstance(filas, list) or len(filas) > 50:
        raise HTTPException(422, 'Registra hasta 50 contenedores por recepción.')
    if filas and not anterior['embarques'] and len(r.origenes or [])>1:
        raise HTTPException(422, 'Identifica los embarques de los packing lists antes de distribuir contenedores entre varios documentos.')
    resultado, usados, rangos = [], set(), []
    for i, entrada in enumerate(filas):
        if not isinstance(entrada, dict): raise HTTPException(422, 'Contenedor inválido.')
        campos = {'numero': 20, 'desde': 20, 'hasta': 20, 'posicion': 120}
        if set(entrada) - set(campos) - {'embarques'}: raise HTTPException(422, 'Campos del contenedor inválidos.')
        if any(not isinstance(entrada.get(k, ''), str) or len(entrada.get(k, '')) > n for k, n in campos.items()):
            raise HTTPException(422, 'Revisa el número, rango y posición del contenedor.')
        f = {k: entrada.get(k, '').strip().upper() for k in campos}
        if not re.fullmatch(r'[A-Z]{4}[0-9]{7}', f['numero']):
            raise HTTPException(422, 'Número de contenedor: cuatro letras y siete dígitos, por ejemplo HLBU1291707.')
        if f['numero'] in usados: raise HTTPException(422, 'El mismo contenedor está repetido.')
        usados.add(f['numero'])
        bs = entrada.get('embarques', [])
        if not isinstance(bs, list) or any(not isinstance(b, str) for b in bs) or len(bs) != len(set(bs)) or not set(bs) <= set(anterior['embarques']):
            raise HTTPException(422, 'Asigna únicamente embarques de esta recepción.')
        conocido = next((d for d in anterior['detectados'] if d['numero'] == f['numero']), None)
        if conocido and set(bs) != set(conocido['embarques']):
            raise HTTPException(422, 'Los embarques del contenedor deben coincidir con sus líneas del packing list.')
        if anterior['embarques'] and not bs: raise HTTPException(422, 'Selecciona el embarque del contenedor para evitar mezclar informes.')
        total = None
        if f['desde'] or f['hasta']:
            a = re.fullmatch(r'([A-Z]*)([0-9]+)', f['desde']); b = re.fullmatch(r'([A-Z]*)([0-9]+)', f['hasta'])
            if not a or not b or a[1] != b[1] or not 0 <= int(a[2]) <= int(b[2]) <= 1000000:
                raise HTTPException(422, 'Completa ambos extremos con el mismo prefijo y en orden, por ejemplo E01 hasta E60.')
            inicio, fin = int(a[2]), int(b[2])
            if any(p == a[1] and inicio <= h and fin >= d for p, d, h in rangos):
                raise HTTPException(422, 'Los rangos de bultos se superponen entre contenedores. Corrígelos antes de guardar.')
            rangos.append((a[1], inicio, fin)); total = fin - inicio + 1
        resultado.append({**f, 'id': 'C' + str(i + 1), 'embarques': sorted(bs), 'total': total})
    if resultado == anterior['filas']: return anterior
    f = db.scalar(select(AppConfig).where(AppConfig.clave == clave(r.codigo)).with_for_update().execution_options(populate_existing=True))
    f = f or AppConfig(clave=clave(r.codigo))
    f.datos = {'filas': resultado, 'usuario': usuario, 'fecha': utcnow().isoformat()}; f.usuario = usuario; db.add(f)
    ajustes.auditar(db, usuario, 'DISTRIBUCION_CONTENEDORES', r.codigo, {'contenedores': len(resultado), 'cantidadesModificadas': False})
    db.commit()
    return vista(db, r.codigo)
