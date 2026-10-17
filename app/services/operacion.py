"""Preferencias administrables, ingreso físico y evidencia; sin binarios en SQL."""
from copy import deepcopy
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import (AppConfig, AppEvidencia, AppEvento, AppIngreso,
    AppUnidadLogistica, Operador, Rol, utcnow)
from app.services import app_modelo as m
from app.services.normalize import normalizar_sku

DEFECTO = {'evidencias': {'exterioresMin': 3, 'exterioresObjetivo': 6,
    'packingMin': 1, 'abiertosMin': 2, 'panoramicasMin': 6, 'bloquear': False},
    'catalogo': {'activo': True, 'horas': [8, 10, 15], 'zona': 'America/Guayaquil'},
    'repositorios': [], 'impresoras': [], 'maxCopias': 500,
    'correo': {'responsable': '', 'permitirPersonal': True}}
TIPOS = {'EXTERIOR_BULTO', 'PACKING_INICIAL', 'ABIERTO_CON_PACKING',
    'CAJA_CERRADA', 'ETIQUETA_CAJA', 'CAJA_ABIERTA', 'ITEM_NOVEDAD', 'PANORAMICA', 'ADICIONAL', 'DANO_EMBALAJE', 'ESTADO_FINAL'}
CATEGORIAS = {'RECEPCION', 'VALIDACION', 'FALTANTE', 'SOBRANTE', 'PNC', 'GENERAL'}


def configuracion(db, publica=False):
    f = db.get(AppConfig, 'operacion')
    d = deepcopy(DEFECTO)
    if f:
        d.update(deepcopy(f.datos))
        for k in ('evidencias', 'catalogo', 'correo'):
            d[k] = {**DEFECTO[k], **d[k]}
    for p in d['impresoras']:
        p['tokenConfigurado'] = bool(p.pop('tokenHash', None))
    if publica:
        return {'evidencias': d['evidencias'], 'maxCopias': d['maxCopias'],
            'impresoras': [{'id': p['id'], 'nombre': p['nombre']} for p in d['impresoras'] if p.get('activo', True)]}
    return d


def guardar_config(db, datos, usuario):
    actual = configuracion(db)
    f = db.get(AppConfig, 'operacion')
    hashes = {p['id']: p.get('tokenHash') for p in (f.datos.get('impresoras', []) if f else [])}
    d = {**actual, **{k: datos[k] for k in DEFECTO if k in datos}}
    try:
        d['correo'] = {**DEFECTO['correo'], **d['correo']}
        responsable = str(d['correo']['responsable'] or '').strip().lower()
        if responsable and not re.fullmatch(r'[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+', responsable):
            raise ValueError('Correo responsable inválido')
        if type(d['correo']['permitirPersonal']) is not bool:
            raise ValueError('Permiso para correo personal inválido')
        d['correo'] = {'responsable': responsable, 'permitirPersonal': d['correo']['permitirPersonal']}
        d['evidencias'] = {**DEFECTO['evidencias'], **d['evidencias']}
        for k in ('exterioresMin', 'exterioresObjetivo', 'packingMin', 'abiertosMin', 'panoramicasMin'):
            v = d['evidencias'][k]
            if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 100:
                raise ValueError('Recomendaciones de fotos: enteros entre 0 y 100')
        if not isinstance(d['evidencias']['bloquear'], bool):
            raise ValueError('Política de evidencia inválida')
        horas = d['catalogo']['horas']
        if not isinstance(horas, list) or not 1 <= len(horas) <= 12 or any(type(h) is not int or not 0 <= h <= 23 for h in horas):
            raise ValueError('Horas del catálogo: de 0 a 23, hasta 12 ejecuciones diarias')
        d['catalogo']['horas'] = sorted(set(horas))
        ZoneInfo(d['catalogo']['zona'])
        if not isinstance(d['catalogo']['activo'], bool):
            raise ValueError('Estado del catálogo inválido')
        if type(d['maxCopias']) is not int or not 1 <= d['maxCopias'] <= 5000:
            raise ValueError('Máximo de copias: de 1 a 5000')
        for seccion in ('repositorios', 'impresoras'):
            if not isinstance(d[seccion], list) or len(d[seccion]) > 100:
                raise ValueError('Hasta 100 repositorios o estaciones')
            vistos = set()
            for p in d[seccion]:
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', str(p.get('id', ''))) or p['id'] in vistos:
                    raise ValueError('Identificador inválido o repetido')
                vistos.add(p['id'])
                p['nombre'] = str(p.get('nombre') or p['id'])[:120]
                p['activo'] = p.get('activo', True) is True
                if seccion == 'repositorios':
                    carpeta = str(p.get('carpetaId') or '').strip()
                    match = re.search(r'/folders/([\w-]+)', carpeta)
                    p['carpetaId'] = match.group(1) if match else carpeta
                    if not re.fullmatch(r'[\w-]{10,128}', p['carpetaId']):
                        raise ValueError('Repositorio: ID o enlace de carpeta Drive inválido')
                    for k in ('cliente', 'marca'):
                        p[k] = str(p.get(k) or '').strip().upper()[:60]
                else:
                    p['host'] = str(p.get('host') or '').strip()
                    if not re.fullmatch(r'[A-Za-z0-9.:-]{1,253}', p['host']):
                        raise ValueError('Impresora: indicar IP o dominio, sin URL ni ruta')
                    if type(p.get('puerto', 9100)) is not int or not 1 <= p.get('puerto', 9100) <= 65535:
                        raise ValueError('Puerto de impresora inválido')
                    p['puerto'] = p.get('puerto', 9100)
                    p['equipo'] = str(p.get('equipo') or '').strip()[:120]
                    p.pop('tokenConfigurado', None)
                    p['tokenHash'] = hashes.get(p['id'])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:
        raise HTTPException(422, 'Zona horaria o configuración inválida') from None
    f = f or AppConfig(clave='operacion')
    f.datos, f.usuario, f.modificado_en = d, usuario, utcnow()
    db.add(f); db.commit()
    return configuracion(db)


def auditoria(db, codigo, usuario, accion, datos):
    db.add(AppEvento(id=uuid4().hex, recepcion=codigo, tipo='AUDITORIA', cantidad=0,
        usuario=usuario, motivo=accion[:300], datos={'accion': accion, **datos}))


def obtener_ingreso(db, codigo):
    m.obtener(db, codigo)
    f = db.get(AppIngreso, codigo)
    unidades = list(db.scalars(select(AppUnidadLogistica).where(AppUnidadLogistica.recepcion == codigo)
        .order_by(AppUnidadLogistica.tipo, AppUnidadLogistica.numero)))
    evidencias = list(db.scalars(select(AppEvidencia).where(AppEvidencia.recepcion == codigo,
        AppEvidencia.eliminado_en.is_(None))))
    d = f.datos if f else {}
    avisos = []
    p = configuracion(db, publica=True)['evidencias']
    fotos = lambda tipo, unidad=None: len({e.archivo_id for e in evidencias
        if e.tipo == tipo and (unidad is None or e.unidad_id == unidad)})
    if d.get('protocolo') == 'REGLAMENTARIO':
        if fotos('PACKING_INICIAL') < p['packingMin']:
            avisos.append(f"Packing list inicial: recomendado {p['packingMin']} foto(s)")
        for u in unidades:
            if u.tipo != 'BULTO': continue
            if fotos('EXTERIOR_BULTO', u.id) < p['exterioresMin']:
                avisos.append(f'Bulto {u.numero}: faltan fotos exteriores recomendadas')
            if fotos('ABIERTO_CON_PACKING', u.id) < p['abiertosMin']:
                avisos.append(f'Bulto {u.numero}: faltan fotos abierto con packing list')
    elif d.get('protocolo') == 'GENERAL' and fotos('PANORAMICA') < p['panoramicasMin']:
        avisos.append(f"Recomendadas {p['panoramicasMin']} imágenes panorámicas")
    return {'recepcion': codigo, **d, 'version': d.get('version', 0), 'avisos': avisos, 'recomendaciones': p, 'unidades': [
        {'id': u.id, 'tipo': u.tipo, 'numero': u.numero, 'codigo': u.codigo,
         'padreId': u.padre_id, **(u.datos or {}), 'version': (u.datos or {}).get('version', 0)} for u in unidades],
        'evidencias': [{'id': e.id, 'archivoId': e.archivo_id, 'unidadId': e.unidad_id,
            'sku': e.sku, 'origen': e.origen, 'categoria': e.categoria, 'tipo': e.tipo,
            'protocolo': e.protocolo, 'creadoEn': m._iso(e.creado_en)} for e in evidencias]}


def guardar_ingreso(db, codigo, datos, usuario):
    r = m.obtener(db, codigo, bloquear=True)
    if r.estado not in m.ABIERTAS:
        raise HTTPException(409, 'Reabre la recepción para modificar su ingreso')
    f = db.scalar(select(AppIngreso).where(AppIngreso.recepcion == codigo).with_for_update().execution_options(populate_existing=True))
    revision = (f.datos or {}).get('version', 0) if f else 0
    if revision and datos.get('version') != revision:
        raise HTTPException(409, 'Otro supervisor actualizó el ingreso. Recarga sus datos antes de guardar tus cambios.')
    f = f or AppIngreso(recepcion=codigo, datos={})
    d = {**(f.datos or {}), **{k: datos[k] for k in
        ('marca', 'embarque', 'protocolo', 'paso') if k in datos}}
    if d.get('protocolo', 'REGLAMENTARIO') not in ('REGLAMENTARIO', 'GENERAL', 'SIN_FOTOS'):
        raise HTTPException(422, 'Protocolo inválido')
    d.setdefault('protocolo', 'REGLAMENTARIO')
    for k in ('marca', 'embarque'):
        d[k] = str(d.get(k) or '').strip()[:120]
    responsable = str(d.get('responsable') or usuario or '').strip().lower()
    op = db.scalar(select(Operador).where(func.lower(Operador.email) == responsable,
        Operador.activo.is_(True), Operador.rol.in_([Rol.ADMIN, Rol.SUPERVISOR])))
    if responsable and '@' in responsable and not op:
        raise HTTPException(422, 'El responsable debe ser un supervisor activo registrado')
    d['responsable'] = responsable
    if d.get('paso', 'EVIDENCIAS') not in ('EVIDENCIAS', 'PACKING', 'VALIDACION'):
        raise HTTPException(422, 'Paso de recepción inválido')
    d.setdefault('paso', 'EVIDENCIAS')
    d['version'] = revision + 1
    f.datos, f.actualizado_en = d, utcnow()
    db.add(f)
    db.flush()
    if d['paso'] in ('PACKING', 'VALIDACION') and configuracion(db)['evidencias']['bloquear'] and obtener_ingreso(db, codigo)['avisos']:
        db.rollback()
        raise HTTPException(409, 'Completa las recomendaciones exigidas por ADMIN antes de continuar')
    auditoria(db, codigo, usuario, 'INGRESO_RECEPCION', {'paso': d['paso'], 'protocolo': d['protocolo']})
    db.commit()
    return obtener_ingreso(db, codigo)


def guardar_unidad(db, codigo, datos, usuario):
    r = m.obtener(db, codigo, bloquear=True)
    if r.estado not in m.ABIERTAS:
        raise HTTPException(409, 'Recepción cerrada')
    tipo = datos.get('tipo', 'BULTO')
    if tipo not in ('BULTO', 'CAJA_MADRE'):
        raise HTTPException(422, 'Tipo de unidad inválido')
    ident = datos.get('id')
    u = db.scalar(select(AppUnidadLogistica).where(AppUnidadLogistica.id == ident).with_for_update().execution_options(populate_existing=True)) if ident else None
    if ident and (not u or u.recepcion != codigo or u.tipo != tipo):
        raise HTTPException(404, 'Unidad logística no encontrada')
    anterior = dict(u.datos or {}) if u else {}
    revision = anterior.get('version', 0)
    if u and revision and datos.get('version') != revision:
        raise HTTPException(409, 'Otro supervisor modificó este bulto. Revisa sus cambios antes de guardar; tus fotos no se pierden.')
    padre_id = datos.get('padreId', u.padre_id if u else None)
    padre = db.scalar(select(AppUnidadLogistica).where(AppUnidadLogistica.id == padre_id).with_for_update()) if padre_id else None
    if tipo == 'CAJA_MADRE' and (not padre or padre.recepcion != codigo or padre.tipo != 'BULTO'):
        raise HTTPException(422, 'La caja madre necesita un bulto de esta recepción')
    if tipo == 'BULTO' and padre_id:
        raise HTTPException(422, 'Un bulto no puede estar dentro de otro bulto')
    if not u:
        numero = (db.scalar(select(func.max(AppUnidadLogistica.numero)).where(
            AppUnidadLogistica.recepcion == codigo, AppUnidadLogistica.tipo == tipo)) or 0) + 1
        u = AppUnidadLogistica(id=uuid4().hex, recepcion=codigo, tipo=tipo, numero=numero)
    cod = str(datos.get('codigo', u.codigo or '') or '').strip()
    if len(cod) > 80:
        raise HTTPException(422, 'Código de unidad demasiado largo')
    origenes = datos.get('origenes', anterior.get('origenes', [])) or []
    if not isinstance(origenes, list) or any(not isinstance(o, str) or len(o) > 40 for o in origenes):
        raise HTTPException(422, 'Listas vinculadas inválidas')
    if 'concluido' in datos and type(datos['concluido']) is not bool:
        raise HTTPException(422, 'Estado del bulto inválido')
    u.codigo, u.padre_id = cod, padre.id if padre else None
    u.datos = {**anterior, 'origenes': list(dict.fromkeys(origenes)),
        'observacion': str(datos.get('observacion', anterior.get('observacion', '')) or '')[:300],
        'pallet': str(datos.get('pallet', anterior.get('pallet', '')) or '').strip().upper()[:80],
        'lecturaOriginal': str(datos.get('lecturaOriginal', anterior.get('lecturaOriginal', '')) or '')[:2048],
        'concluido': datos.get('concluido', anterior.get('concluido', False)),
        'version': revision + 1, 'actualizadoPor': usuario, 'actualizadoEn': m._iso(utcnow())}
    db.add(u)
    auditoria(db, codigo, usuario, 'UNIDAD_LOGISTICA', {'unidadId': u.id, 'tipo': tipo, 'codigo': u.codigo, **u.datos})
    db.commit()
    return obtener_ingreso(db, codigo)


def validar_evidencia(db, codigo, datos):
    tipo, categoria = datos.get('tipoEvidencia', 'ADICIONAL'), datos.get('categoria', 'GENERAL')
    if tipo not in TIPOS or categoria not in CATEGORIAS:
        raise HTTPException(422, 'Clasificación de evidencia inválida')
    if tipo == 'ESTADO_FINAL' and (categoria != 'RECEPCION' or str(datos.get('sku') or '').strip()):
        raise HTTPException(422, 'El estado final corresponde a la recepción completa, sin SKU')
    protocolo = datos.get('protocolo', 'GENERAL')
    if protocolo not in ('REGLAMENTARIO', 'GENERAL'):
        raise HTTPException(422, 'Protocolo inválido')
    u = db.scalar(select(AppUnidadLogistica).where(AppUnidadLogistica.id == datos.get('unidadId')).with_for_update().execution_options(populate_existing=True)) if datos.get('unidadId') else None
    if datos.get('unidadId') and (not u or u.recepcion != codigo):
        raise HTTPException(422, 'La unidad no pertenece a esta recepción')
    if u and 'unidadVersion' in datos and datos['unidadVersion'] != (u.datos or {}).get('version', 0):
        raise HTTPException(409, 'Otro supervisor cambió este bulto. Revisa su etiqueta antes de adjuntar las fotos.')
    origen = str(datos.get('origen') or '')
    if len(origen) > 40: raise HTTPException(422, 'Identificador de lista demasiado largo')
    return {'tipo': tipo, 'categoria': categoria, 'protocolo': protocolo,
        'unidad_id': u.id if u else None, 'origen': origen or None,
        'sku': normalizar_sku(datos.get('sku'))[:80] or None}


def vincular_evidencia(db, archivo, datos, usuario, confirmar=True):
    d = validar_evidencia(db, archivo.recepcion, datos)
    q = select(AppEvidencia).where(AppEvidencia.archivo_id == archivo.id,
        AppEvidencia.eliminado_en.is_(None), *[getattr(AppEvidencia, k) == v for k, v in d.items()])
    e = db.scalar(q)
    creada = e is None
    if not e:
        e = AppEvidencia(id=uuid4().hex, archivo_id=archivo.id, recepcion=archivo.recepcion,
            usuario=usuario, **d)
        db.add(e)
        auditoria(db, archivo.recepcion, usuario, 'EVIDENCIA_REGISTRADA',
            {'archivoId': archivo.id, 'unidadId': d['unidad_id'], 'sku': d['sku'], 'categoria': d['categoria']})
        db.commit() if confirmar else db.flush()
    return creada
    return e


def destino_drive(db, codigo):
    r = m.obtener(db, codigo)
    ingreso = db.get(AppIngreso, codigo)
    d = ingreso.datos if ingreso else {}
    marca = str(d.get('marca') or '').strip().upper()
    candidatos = [p for p in configuracion(db)['repositorios'] if p.get('activo', True)
        and (not p.get('cliente') or p['cliente'] == r.cliente.upper())
        and (not p.get('marca') or p['marca'] == marca)]
    candidatos.sort(key=lambda p: (bool(p.get('cliente')) + bool(p.get('marca'))), reverse=True)
    responsable = d.get('responsable') or r.creado_por or ''
    if '@' not in responsable and candidatos:
        responsable = candidatos[0].get('supervisor') or responsable
    return {'cliente': r.cliente, 'marca': marca, 'carpetaRecepcion': r.codigo,
        'carpetaRaiz': candidatos[0]['carpetaId'] if candidatos else '',
        'supervisor': responsable}


def ajustar_bultos(db, codigo, datos, usuario, confirmar=True):
    try: r = m.obtener(db, codigo, bloquear=True)
    except m.ErrorApp as exc: raise HTTPException(404, str(exc)) from None
    if r.estado not in m.ABIERTAS: raise HTTPException(409, 'Recepción cerrada')
    n = datos.get('cantidad')
    if type(n) is not int or not 1 <= n <= 1000: raise HTTPException(422, 'Cantidad de bultos: de 1 a 1000')
    existentes = list(db.scalars(select(AppUnidadLogistica).where(AppUnidadLogistica.recepcion == codigo,
        AppUnidadLogistica.tipo == 'BULTO').order_by(AppUnidadLogistica.numero).with_for_update().execution_options(populate_existing=True)))
    if existentes and n != r.bultos and datos.get('cantidadAnterior') != r.bultos:
        raise HTTPException(409, 'El total de bultos cambió. Recarga antes de corregirlo.')
    if n < len(existentes):
        sobrantes = existentes[n:]
        for u in sobrantes:
            if u.codigo or any((u.datos or {}).get(k) for k in ('observacion','pallet','concluido','origenes','etiquetaEmitida')) or db.scalar(
                select(AppEvidencia.id).where(AppEvidencia.unidad_id == u.id).limit(1)) or db.scalar(
                select(AppUnidadLogistica.id).where(AppUnidadLogistica.padre_id == u.id).limit(1)):
                raise HTTPException(409, 'Solo se pueden quitar bultos finales vacíos, sin etiquetas, fotos ni registros.')
        for u in sobrantes: db.delete(u)
    for numero in range(len(existentes)+1, n+1):
        db.add(AppUnidadLogistica(id=uuid4().hex, recepcion=codigo, tipo='BULTO', numero=numero, codigo='', datos={}))
    r.bultos = n
    auditoria(db, codigo, usuario, 'BULTOS_RECIBIDOS', {'cantidad': n})
    db.flush()
    if confirmar: db.commit()
    return obtener_ingreso(db, codigo)
