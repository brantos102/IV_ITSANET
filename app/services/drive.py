"""Cola durable de imágenes: copia durante la recepción, sin detener el conteo."""
import base64
import hashlib
import logging
import time
from datetime import timedelta
import re
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update, func

from app.db import SessionLocal
from app.models import AppArchivo, AppArchivoIdentidad, AppCopiaDrive, AppEvidencia, AppUnidadLogistica, utcnow
from app.services import archivos, entregas, operacion
from app.services.fotos_identidad import pallet_evidencia
from app.services import app_modelo as m

_verificados = {}


def ubicacion_evidencia(db, e, j, *, fuente=None):
    """Compara el destino vigente con la última ruta confirmada por el puente.

    No consulta ni mueve archivos remotos. Una copia histórica no acredita por
    sí sola que esté organizada en el embarque que corresponde hoy.
    """
    from app.services.fotos_embarques import informacion, asignado, ruta
    fuente = fuente or informacion(db, e.recepcion)
    emb = asignado(db, e, fuente=fuente)
    esperada = ruta(db, e, con_bulto=bool(db.get(AppArchivoIdentidad,e.archivo_id)), fuente=fuente)
    datos = j.datos if j else {}
    vs = datos.get('rutasVinculadas', [])
    propias = [v for v in vs if v.get('evidenciaId') == e.id]
    # Puentes anteriores no incluían evidenciaId. Solo aceptar una coincidencia
    # de ruta y clasificación, nunca la carpeta de otro embarque del mismo SKU.
    if not propias:
        propias = [v for v in vs if v.get('sku','') == (e.sku or '') and v.get('categoria') == e.categoria]
    actuales = [v.get('ruta',[]) for v in propias] or ([datos['ruta']] if datos.get('ruta') else [])
    if fuente[3] and emb is None:
        estado = 'ASIGNAR_EMBARQUE'
    elif not j or j.estado != 'COPIADA':
        estado = 'PENDIENTE_COPIA'
    elif esperada not in actuales:
        estado = 'ACTUALIZAR_CARPETAS'
    else:
        estado = 'SINCRONIZADA'
    return {'estado':estado, 'embarque':emb, 'rutaEsperada':esperada, 'rutasRegistradas':actuales}


def carpeta_sku(j,e,*,db=None,fuente=None):
    if not j or j.estado!='COPIADA' or not e.sku:return None
    if db is not None and ubicacion_evidencia(db,e,j,fuente=fuente)['estado']!='SINCRONIZADA':return None
    propio=j.datos.get('vinculosPorEvidencia',{}).get(e.id,{})
    if propio.get('carpetaSkuUrl'):return propio['carpetaSkuUrl']
    # El puente anterior usa categoría|SKU; solo es inequívoco para un vínculo.
    claves=[v for v in j.datos.get('rutasVinculadas',[]) if v.get('categoria')==e.categoria and v.get('sku')==e.sku]
    if len({tuple(v.get('ruta',[])) for v in claves})>1:return None
    vinculo=j.datos.get('vinculosDrive',{}).get(e.categoria+'|'+e.sku,{})
    if vinculo.get('carpetaSkuUrl'):return vinculo['carpetaSkuUrl']
    if j.datos.get('sku')==e.sku and (j.datos.get('categoria') or (j.datos.get('ruta') or [None])[0])==e.categoria:
        return j.datos.get('carpetaSkuUrl')
    return None


def resumen_fotos(db, codigo, *, ids=None):
    """Estado de todas las fotos guardadas, también panorámicas y finales."""
    resumen = {'guardadas': 0, 'copiadas': 0, 'pendientes': 0, 'procesando': 0, 'requierenAyuda': 0}
    if ids is not None and not ids:return resumen
    consulta = select(AppArchivo, AppCopiaDrive).outerjoin(AppCopiaDrive,
        AppCopiaDrive.archivo_id == AppArchivo.id).where(AppArchivo.recepcion == codigo,
        AppArchivo.tipo == 'foto')
    if ids is not None:consulta=consulta.where(AppArchivo.id.in_(ids))
    filas=db.execute(consulta)
    from app.services.fotos_embarques import informacion
    fuente=informacion(db,codigo)
    evidencias={}
    for e in db.scalars(select(AppEvidencia).where(AppEvidencia.recepcion==codigo,AppEvidencia.eliminado_en.is_(None))):
        evidencias.setdefault(e.archivo_id,[]).append(e)
    for a, j in filas:
        if j and (j.estado == 'ELIMINADA' or j.datos.get('accion') == 'papelera'):
            continue
        resumen['guardadas'] += 1
        organizadas=all(ubicacion_evidencia(db,e,j,fuente=fuente)['estado']=='SINCRONIZADA' for e in evidencias.get(a.id,[]))
        if a.drive_id and j and j.estado == 'COPIADA' and organizadas:
            resumen['copiadas'] += 1
        else:
            resumen['pendientes'] += 1
            resumen['procesando'] += bool(j and j.estado == 'PROCESANDO')
            resumen['requierenAyuda'] += bool(j and j.error)
    return resumen


def pendientes_cierre(db, codigo, offset=0, limite=30):
    """Solo información operativa: no expone remitentes, claves ni errores del puente."""
    from app.services.informes import metadatos, requiere_enlaces
    codigo = m.obtener(db, codigo).codigo
    meta = metadatos(db, codigo)
    from app.services.fotos_embarques import informacion
    fuente=informacion(db,codigo)
    filas = db.execute(select(AppArchivo, AppEvidencia, AppCopiaDrive, AppUnidadLogistica)
        .join(AppEvidencia, AppEvidencia.archivo_id == AppArchivo.id)
        .outerjoin(AppCopiaDrive, AppCopiaDrive.archivo_id == AppArchivo.id)
        .outerjoin(AppUnidadLogistica, AppUnidadLogistica.id == AppEvidencia.unidad_id)
        .where(AppEvidencia.recepcion == codigo, AppEvidencia.eliminado_en.is_(None),
            AppEvidencia.sku.is_not(None), AppEvidencia.sku != '')
        .order_by(AppArchivo.creado_en, AppArchivo.id, AppEvidencia.id))
    pendientes = {}
    for a, e, j, u in filas:
        if carpeta_sku(j,e,db=db,fuente=fuente):
            continue
        f = pendientes.setdefault(a.id, {'archivoId': a.id, 'nombre': a.nombre,
            'estado': j.estado if j else 'SIN_COLA', 'intentos': j.intentos if j else 0,
            'proximoEn': m._iso(j.proximo_en) if j else None,
            'requiereAyuda': bool(j and j.error), 'vinculos': []})
        f['vinculos'].append({'sku': e.sku, 'tipo': e.tipo, 'categoria': e.categoria,
            **ubicacion_evidencia(db,e,j,fuente=fuente),
            'origen': e.origen or '', 'unidad': f'{u.tipo} {u.numero} · {u.codigo or "Sin código"}' if u else ''})
    fotos = list(pendientes.values())
    return {'total': len(fotos), 'bloqueaCierre': requiere_enlaces(meta) and bool(fotos),
        'procesando': sum(f['estado'] == 'PROCESANDO' for f in fotos),
        'requierenAyuda': sum(f['requiereAyuda'] for f in fotos),
        'sincronizacion': resumen_fotos(db, codigo),
        'archivos': fotos[offset:offset + limite], 'offset': offset,
        'hayMas': offset + limite < len(fotos)}


def reintentar_pendientes(db, codigo, usuario):
    """Adelanta copias pendientes; mantiene las reservas activas y sus claves."""
    r = m.obtener(db, codigo, bloquear=True)
    codigo = r.codigo
    if r.estado not in {*m.ABIERTAS, 'CERRADA'}:
        raise HTTPException(409, 'La recepción no permite reintentar sus fotos en este estado')
    # Incluye fotos generales para que la recepción completa pueda sincronizarse.
    fotos = list(db.scalars(select(AppArchivo).outerjoin(AppEvidencia,
        AppEvidencia.archivo_id == AppArchivo.id).where(AppArchivo.recepcion == codigo,
        AppArchivo.tipo == 'foto', AppEvidencia.eliminado_en.is_(None)).distinct()))
    ahora = utcnow()
    cantidad = 0
    for a in fotos:
        j = db.scalar(select(AppCopiaDrive).where(AppCopiaDrive.archivo_id == a.id)
            .with_for_update().execution_options(populate_existing=True))
        if not j:
            if a.drive_id: continue
            j = encolar(db, a)
            db.flush()
        # Nunca adelantar una reserva activa ni una eliminación de evidencia.
        if j.datos.get('accion') == 'papelera': continue
        if j.estado == 'COPIADA' and a.drive_id:
            nueva = descripcion(db, a)
            if nueva['ruta'] != j.datos.get('ruta') or nueva.get('rutasVinculadas') != j.datos.get('rutasVinculadas'):
                j.datos = {**nueva, 'accion': 'ubicar'}
                j.usuario, j.estado = nueva['usuario'], 'PENDIENTE'
        if j.estado=='REVISION':j.estado='PENDIENTE'
        if j.estado == 'PENDIENTE':
            j.proximo_en = ahora
            cantidad += 1
    operacion.auditoria(db, codigo, usuario, 'COPIAS_DRIVE_REINTENTADAS', {'cantidad': cantidad})
    db.commit()
    return {'programadas': cantidad,
        'mensaje': f'{cantidad} foto(s) programadas para reintento. Se conserva cada archivo y su identificador; el correo todavía no se ha enviado.'}


def verificar_puente(db, clave, datos):
    from app.services.integraciones import google
    g = google(db, datos['usuario'])
    k = (g['url'], hashlib.sha256(g['secreto'].encode()).hexdigest(), datos['usuario'], datos.get('carpetaRaiz'),bool(datos.get('rutaSku')),datos.get('versionFotos'))
    if _verificados.get(k, 0) > time.monotonic(): return
    r = entregas.llamar('estado', clave, {'usuario': datos['usuario'], 'carpetaRaiz': datos.get('carpetaRaiz', '')})
    if datos.get('carpetaRecepcionId') and 'carpetasRecepcion62' not in r.get('capacidades',[]):raise RuntimeError('Actualiza Servidor.gs: la recepción conserva una carpeta fija de la versión 62. Las fotos locales se conservan.')
    if datos.get('rutaSku') and 'fotosSkuSimples' not in r.get('capacidades',[]):
        raise RuntimeError('Actualiza Servidor.gs y publica una Nueva versión del mismo /exec para fotos por SKU con nombres simples. Se conservan las imágenes locales.')
    if datos.get('versionFotos')==2 and 'fotosAuditables' not in r.get('capacidades',[]):
        raise RuntimeError('Actualiza Servidor.gs: faltan nombres auditables y clasificación histórica. Las fotos siguen guardadas en el servidor.')
    if r.get('versionPuente', 0) < 2:
        raise RuntimeError('Actualiza Servidor.gs y publica su versión con rutas de evidencias')
    if str(r.get('remitente') or '').lower() != datos['usuario'].lower():
        raise RuntimeError('El puente no confirma al supervisor responsable')
    if datos.get('carpetaRaiz') and r.get('carpetaId') != datos['carpetaRaiz']:
        raise RuntimeError('El puente no confirmó el repositorio configurado')
    if len(_verificados) > 128: _verificados.clear()
    _verificados[k] = time.monotonic() + 300


def ruta_evidencia(e):
    if e and e.sku:
        return ([e.categoria] if e.categoria in ('PNC','SOBRANTE','FALTANTE') else [])+[e.sku]
    return [e.categoria if e else 'GENERAL']+([e.tipo] if e else [])


def nombre_evidencia(db,archivo,e):
    if db.get(AppArchivoIdentidad,archivo.id):
        from app.services.fotos_identidad import nombre
        return nombre(db,archivo)
    if not e or not e.sku:return archivo.nombre
    ids=[f[0] for f in db.execute(select(AppArchivo.id,func.min(AppEvidencia.creado_en)).join(AppEvidencia,
        AppEvidencia.archivo_id==AppArchivo.id).where(AppEvidencia.recepcion==archivo.recepcion,
        AppEvidencia.sku==e.sku)
        .group_by(AppArchivo.id).order_by(func.min(AppEvidencia.creado_en),AppArchivo.id))]
    extension='.png' if archivo.mime=='image/png' else '.webp' if archivo.mime=='image/webp' else '.jpg'
    return f'{e.sku}_{ids.index(archivo.id)+1:03d}'+extension


def descripcion(db, archivo, evidencia=None):
    es = list(db.scalars(select(AppEvidencia).where(AppEvidencia.archivo_id == archivo.id,
        AppEvidencia.eliminado_en.is_(None)).order_by(AppEvidencia.creado_en, AppEvidencia.id)))
    e = evidencia or (es[0] if es else None)
    d = operacion.destino_drive(db, archivo.recepcion)
    d['usuario'] = d.pop('supervisor')
    from app.services.remitentes import responsable
    d['usuario'] = responsable(db, archivo.recepcion, d['usuario']) or d['usuario']
    anterior=db.get(AppCopiaDrive,archivo.id)
    if anterior and anterior.datos.get('usuarioDriveFijado'):
        d['usuarioDriveFijado']=anterior.datos['usuarioDriveFijado'];d['usuario']=d['usuarioDriveFijado']
    identidad=db.get(AppArchivoIdentidad,archivo.id)
    if identidad and not db.is_modified(identidad,include_collections=True):
        # Otro operario puede haber añadido un vínculo mientras Google copiaba
        # el archivo. Releer el mapa antes de confirmar sus rutas.
        db.refresh(identidad)
    from app.services.fotos_embarques import informacion
    fuente_embarques=informacion(db,archivo.recepcion)
    def ruta(v,solo_sku=False):
        from app.services.fotos_embarques import ruta as ruta_embarque
        return ruta_embarque(db,v,con_bulto=bool(identidad) and not solo_sku,fuente=fuente_embarques)
    from app.services.fotos_embarques import asignado as leer_asignado
    def asignado(db,e):return leer_asignado(db,e,fuente=fuente_embarques)
    d['ruta'] = ruta(e)
    d['sku'] = e.sku if e else ''
    d['origen'] = e.origen if e else ''
    d['embarque'] = asignado(db,e)
    d['categoria'] = e.categoria if e else 'GENERAL'
    d['rutaSku'] = ruta(e,solo_sku=True) if e and e.sku else []
    d['rutasVinculadas'] = list({(v.categoria,v.sku or '',v.tipo,v.unidad_id,v.origen,asignado(db,v),pallet_evidencia(db,v)):
        {'evidenciaId':v.id,'categoria':v.categoria,'sku':v.sku or '', 'origen':v.origen or '', 'embarque':asignado(db,v),**({'pallet':pallet_evidencia(db,v)} if pallet_evidencia(db,v) else {}),'ruta':ruta(v),
         'rutaSku':ruta(v,solo_sku=True) if v.sku else [],'nombre':nombre_evidencia(db,archivo,v)}
        for v in es}.values())
    d.update(tipoArchivo=archivo.tipo, nombre=archivo.nombre, tipo=archivo.mime,
        recepcion=archivo.recepcion, evidencia=e.id if e else None)
    d['nombre']=nombre_evidencia(db,archivo,e)
    d['tipoEvidencia']=e.tipo if e else ''
    if identidad:
        d.update(versionFotos=2,conservarAccesosPrevios=False,secuencia=identidad.secuencia,
            nombreOriginal=identidad.nombre_original,embarques=identidad.datos.get('embarques',[]))
        if anterior:
            # Solo rutas de esta recepción conocidas por el servidor; no buscar
            # ni eliminar archivos ajenos. El puente trata únicamente atajos.
            previas=[anterior.datos.get('ruta',[])]+[v.get('ruta',[]) for v in anterior.datos.get('rutasVinculadas',[])]+anterior.datos.get('rutasIntentadas',[])
            d['rutasAnteriores']=[list(r) for r in sorted(set(tuple(r) for r in previas if r))]
            if anterior.datos.get('ruta') and anterior.datos['ruta']!=d['ruta']:
                # Mantener accesos a carpetas que ya fueron incluidas en informes.
                d['conservarAccesosPrevios']=True
        d['rutasIntentadas']=[list(r) for r in sorted(set(tuple(r) for r in [d['ruta']]+d.get('rutasAnteriores',[]) if r))]
    return d


def vinculos_por_evidencia(aid,datos,respuesta):
    """Compatibilidad con el puente instalado: categoría|SKU puede repetirse.

    Si una misma foto tiene dos destinos con esa clave, consultar cada vínculo
    con el mismo fileId confirma sus carpetas sin volver a subir el binario.
    """
    salida={};vs=datos.get('rutasVinculadas',[])
    for v in vs:
        if not v.get('evidenciaId'):continue
        k=v['categoria']+'|'+v['sku'];r=respuesta
        if len({tuple(x['ruta']) for x in vs if x['categoria']+'|'+x['sku']==k})>1:
            p={k:x for k,x in datos.items() if k!='base64'}
            p.update(fileId=respuesta['fileId'],rutasVinculadas=[v],conservarAccesosPrevios=True)
            r=entregas.llamar('archivo',aid+':'+aid,p)
            if r.get('fileId')!=respuesta['fileId']:raise RuntimeError('Drive no confirmó la misma imagen al consultar su embarque.')
        salida[v['evidenciaId']]=r.get('vinculosDrive',{}).get(k,{})
    return salida


def encolar(db, archivo):
    j = db.scalar(select(AppCopiaDrive).where(AppCopiaDrive.archivo_id == archivo.id).with_for_update().execution_options(populate_existing=True))
    if not j:
        d = descripcion(db, archivo)
        j = AppCopiaDrive(archivo_id=archivo.id, recepcion=archivo.recepcion,
            usuario=d['usuario'], estado='PENDIENTE', datos=d)
        db.add(j)
    elif j.estado == 'COPIADA' and archivo.drive_id:
        nueva = descripcion(db, archivo)
        if nueva.get('ruta') != j.datos.get('ruta') or nueva.get('rutasVinculadas') != j.datos.get('rutasVinculadas'):
            j.datos = {**nueva, 'accion': 'ubicar'}
            j.usuario, j.estado, j.proximo_en = nueva['usuario'], 'PENDIENTE', utcnow()
    return j


def procesar_uno():
    ahora = utcnow()
    with SessionLocal() as db:
        elegible = or_(AppCopiaDrive.estado == 'PENDIENTE', AppCopiaDrive.estado == 'PROCESANDO')
        aid = db.scalar(select(AppCopiaDrive.archivo_id).where(elegible, AppCopiaDrive.proximo_en <= ahora)
                        .order_by(AppCopiaDrive.proximo_en).limit(1))
        if not aid:return False
        cambio = db.execute(update(AppCopiaDrive).where(AppCopiaDrive.archivo_id == aid,
            elegible, AppCopiaDrive.proximo_en <= ahora).values(estado='PROCESANDO',
            proximo_en=ahora + timedelta(minutes=5)).execution_options(synchronize_session=False))
        db.commit()
        if cambio.rowcount != 1: return False
        j, a = db.get(AppCopiaDrive, aid), db.get(AppArchivo, aid)
        try:
            j.intentos += 1
            # Permite corregir responsable/repositorio desde ADMIN sin editar tareas pendientes.
            if not a.drive_id and j.datos.get('accion') != 'papelera':
                j.datos = descripcion(db, a)
                j.usuario = j.datos['usuario']
            db.commit()
            if not entregas.configurado(db, j.usuario):
                raise RuntimeError('Pendiente de conexión Drive del supervisor responsable')
            d = dict(j.datos)
            verificar_puente(db, aid + ':' + aid, {**d, 'usuario': j.usuario})
            if d.get('accion') == 'papelera':
                if a.drive_id:
                    entregas.llamar('papelera', aid + ':' + aid, {**d, 'usuario': j.usuario, 'fileId': a.drive_id})
                j.estado = 'ELIMINADA'
            else:
                if not a.drive_id or d.get('accion') == 'ubicar':
                    if a.drive_id: d['fileId'] = a.drive_id
                    else: d['base64'] = base64.b64encode(archivos.ruta(a).read_bytes()).decode()
                    r = entregas.llamar('archivo', aid + ':' + aid, d)
                    ident = str(r.get('fileId') or '')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{5,128}', ident):
                        raise RuntimeError('Drive no confirmó el archivo')
                    if a.drive_id and ident != a.drive_id:
                        raise RuntimeError('Drive devolvió otro archivo al actualizar su carpeta; revisa antes de continuar.')
                    vinculos=vinculos_por_evidencia(aid,d,r)
                    a.drive_id, a.drive_url = ident, 'https://drive.google.com/file/d/' + ident + '/view'
                    if r.get('nombre'):a.nombre=str(r['nombre'])[:190]
                    j.datos = {**{k:v for k,v in j.datos.items() if k != 'accion'}, 'carpeta': r.get('carpeta', ''), 'carpetaRecepcionUrl': r.get('carpetaRecepcionUrl', ''),
                        'carpetaSkuUrl': r.get('carpetaSkuUrl', ''),'vinculosDrive':r.get('vinculosDrive',{}),'vinculosPorEvidencia':vinculos}
                j.estado = 'COPIADA'
            j.error = None
            db.commit()
            if j.estado == 'COPIADA':
                nueva = descripcion(db,a)
                if nueva.get('rutasVinculadas') != j.datos.get('rutasVinculadas'):
                    j.datos = {**nueva,'accion':'ubicar'};j.estado='PENDIENTE';j.proximo_en=utcnow();db.commit()
            if a.drive_id and j.estado!='ELIMINADA':archivos.conservar_miniatura(a)
            try: archivos.ruta(a).unlink(missing_ok=True)
            except OSError: logging.getLogger(__name__).warning('Copia Drive confirmada; limpieza local pendiente')
        except Exception as exc:
            db.rollback()
            j = db.get(AppCopiaDrive, aid)
            if not j: return True
            j.estado = 'REVISION' if entregas.conexion_rechazada(str(exc)) else 'PENDIENTE'
            j.error = str(exc)[:160] if type(exc) is RuntimeError else 'Copia pendiente; se reintentará sin perder la foto'
            j.proximo_en = utcnow() + timedelta(seconds=min(1800, 15 * 2 ** min(j.intentos, 7)))
            db.commit()
    return True


def eliminar(db, aid, usuario):
    a = db.get(AppArchivo, aid)
    if not a or a.tipo != 'foto': raise HTTPException(404, 'Foto no encontrada')
    r = m.obtener(db, a.recepcion, bloquear=True)
    if r.estado not in m.ABIERTAS: raise HTTPException(409, 'Reabre la recepción para depurar evidencia')
    j = db.scalar(select(AppCopiaDrive).where(AppCopiaDrive.archivo_id == aid).with_for_update())
    if j and j.estado == 'PROCESANDO': raise HTTPException(409, 'La foto se está copiando; vuelve a intentarlo después')
    for e in db.scalars(select(AppEvidencia).where(AppEvidencia.archivo_id == aid, AppEvidencia.eliminado_en.is_(None))):
        e.eliminado_en = utcnow()
    j = j or encolar(db, a)
    j.estado, j.proximo_en = 'PENDIENTE', utcnow()
    j.datos = {**j.datos, 'accion': 'papelera'}
    operacion.auditoria(db, a.recepcion, usuario, 'EVIDENCIA_RETIRADA', {'archivoId': aid, 'driveId': a.drive_id})
    if not a.drive_id:
        j.estado = 'ELIMINADA'
    db.commit()
    if not a.drive_id: archivos.ruta(a).unlink(missing_ok=True)
    return {'eliminada': True, 'papeleraDrivePendiente': j.estado != 'ELIMINADA'}


def manifiesto(db, codigo):
    retiradas = set(db.scalars(select(AppCopiaDrive.archivo_id).where(
        AppCopiaDrive.recepcion == codigo, or_(AppCopiaDrive.estado == 'ELIMINADA',
        AppCopiaDrive.datos['accion'].as_string() == 'papelera'))))
    filas = list(db.scalars(select(AppArchivo).where(AppArchivo.recepcion == codigo,
        AppArchivo.tipo == 'foto').order_by(AppArchivo.creado_en, AppArchivo.id)))
    grupos = {}
    for a in filas:
        if a.id in retiradas: continue
        es = list(db.scalars(select(AppEvidencia).where(AppEvidencia.archivo_id == a.id,
            AppEvidencia.eliminado_en.is_(None)).order_by(AppEvidencia.creado_en, AppEvidencia.id)))
        for e in es or [None]:
            d = descripcion(db, a, e)
            k = tuple(d['ruta'])
            grupo = grupos.setdefault(k, [])
            if not any(previo.id == a.id for previo, _ in grupo): grupo.append((a, d))
    salida = []
    for grupo in grupos.values():
        for i, (a, d) in enumerate(grupo, 1):
            nombre = d['nombre'] if d.get('sku') or d.get('versionFotos')==2 else f'RECEPCION_{i:03d}' + ('.png' if a.mime == 'image/png' else '.webp' if a.mime == 'image/webp' else '.jpg')
            salida.append({**d, 'archivoId': a.id, 'fileId': a.drive_id,
                'nombreFinal': nombre, 'indice': i, 'total': len(grupo)})
    return salida


def reintentar_desde_cuenta(db,codigo,usuario):
    """Recuperación explícita con la cuenta propia, sin tocar conexiones base."""
    from app.services.integraciones import google
    correo=str(usuario or '').lower()
    destino=operacion.destino_drive(db,codigo)
    conexion=google(db,correo)
    db.rollback()
    try:
        estado=entregas.llamar_conexion('estado',uuid4().hex,{'usuario':correo,'carpetaRaiz':destino['carpetaRaiz']},conexion)
        if str(estado.get('remitente') or '').lower()!=correo or 'fotosSkuSimples' not in estado.get('capacidades',[]):raise RuntimeError('Google no confirmó tu cuenta y el puente actualizado para fotos por SKU.')
        if destino['carpetaRaiz'] and estado.get('carpetaId')!=destino['carpetaRaiz']:raise RuntimeError('Tu cuenta Google no confirmó la carpeta matriz de esta recepción.')
    except RuntimeError as exc:raise HTTPException(502,str(exc)+' Las fotos siguen guardadas; no se envió correo.') from None
    db.rollback();m.obtener(db,codigo,bloquear=True)
    if google(db,correo)!=conexion:raise HTTPException(409,'La conexión cambió durante la verificación. Actualiza antes de reintentar.')
    n=0
    for j in db.scalars(select(AppCopiaDrive).where(AppCopiaDrive.recepcion==codigo,AppCopiaDrive.estado.in_(['PENDIENTE','REVISION'])).with_for_update()):
        if j.datos.get('accion')=='papelera':continue
        j.usuario=correo;j.datos={**j.datos,'usuario':correo,'usuarioDriveFijado':correo};j.estado='PENDIENTE';j.error=None;j.proximo_en=utcnow();n+=1
    from app.models import AppEntrega
    for e in db.scalars(select(AppEntrega).where(AppEntrega.recepcion==codigo,AppEntrega.estado.in_(['PENDIENTE','REVISION'])).with_for_update()):
        if e.estado=='REVISION' and e.datos.get('revisionMotivo') not in ('CONEXION_RECHAZADA','ENTREGAS_MULTIPLES','FOTOS_RECUPERADAS'):continue
        e.estado='REVISION';e.datos={**e.datos,'revisionMotivo':'FOTOS_RECUPERADAS','confirmarConCuenta':correo}
        e.error='Fotos en recuperación. Al confirmarse en Drive, el supervisor debe revisar y confirmar el envío desde su correo.'
    operacion.auditoria(db,codigo,usuario,'FOTOS_RECUPERADAS_CUENTA_PROPIA',{'programadas':n,'remitente':correo})
    db.commit();return {'programadas':n,'mensaje':f'{n} foto(s) programadas desde tu conexión verificada. Espera su confirmación en Drive antes de enviar los documentos.'}
