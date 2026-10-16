"""La API que habla el idioma de la aplicación de los operarios.

Las rutas de `recepciones.py` son del prototipo: identificadores numéricos,
campos en snake_case, un modelo que no sabe de qué packing list viene cada
línea. La aplicación que está en los handhelds lleva meses escribiendo otros
documentos, y son los que entienden `informe.js`, `conteo.js` y `kpi.js`.

Así que estas rutas devuelven exactamente esos documentos, con esos nombres de
campo. La capa de datos del navegador cambia de destino —de Firestore a este
servidor— sin que el resto de la aplicación se entere, que es lo único que
permite migrar sin reescribir las pantallas y sin perder nada por el camino.

Las dos conviven mientras dure la transición: `/api/recepciones` sigue sirviendo
al prototipo y a sus KPIs.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppArchivo, AppArchivoSku, AppConfig, AppEntrega, AppRecepcion, AppEvento, AppSku, Operador, Producto, ProductoCodigo, Rol, utcnow
from app.security import requiere_supervisor, usuario_actual
from app.services import app_modelo as m
from app.services import depot as depot_svc
from app.services import entregas

router = APIRouter(prefix="/api/app", tags=["app-operarios"])

# El código de la recepción ES su identificador, como en Firestore. Las rutas
# lo llevan tal cual: /api/app/recepciones/REC0260002.
COLECCIONES = ("lineas", "skus", "adicionales", "eventos", "auditoria")


@router.get('/estado')
def estado_local(db: Session = Depends(get_db), op: Operador = Depends(requiere_supervisor)):
    estado = {'destino': 'servidor',
            'recepciones': db.scalar(select(func.count()).select_from(AppRecepcion)),
            'productos': db.scalar(select(func.count()).select_from(Producto)),
            'archivos': db.scalar(select(func.count()).select_from(AppArchivo)),
            'firebase_requerido': False}
    if op.rol == Rol.ADMIN:
        estado.update(motor=db.get_bind().dialect.name, correo_configurado=entregas.configurado(db))
    return estado


@router.get('/entregas')
def listar_entregas(db: Session = Depends(get_db), op: Operador = Depends(requiere_supervisor)):
    return [entregas.documento(e, tecnico=op.rol == Rol.ADMIN) for e in db.scalars(
        select(AppEntrega).order_by(AppEntrega.creado_en.desc()).limit(100))]


@router.get('/recepciones/{codigo}/entregas')
def entregas_recepcion(codigo: str, db: Session = Depends(get_db), _: Operador = Depends(requiere_supervisor)):
    # Esta vista operativa no contiene errores de configuracion, tampoco para ADMIN.
    try:
        r = m.obtener(db, codigo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc
    return [entregas.documento(e) for e in db.scalars(select(AppEntrega)
        .where(AppEntrega.recepcion == r.codigo).order_by(AppEntrega.creado_en.desc()).limit(10))]


@router.get('/recepciones/{codigo}/destinatarios-recientes')
def destinatarios_recientes(codigo: str, db: Session = Depends(get_db), _: Operador = Depends(requiere_supervisor)):
    try:
        r = m.obtener(db, codigo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc
    historial = db.scalars(select(AppEntrega).join(AppRecepcion, AppEntrega.recepcion == AppRecepcion.codigo)
        .where(AppRecepcion.cliente == r.cliente)
        .order_by(AppEntrega.creado_en.desc(), AppEntrega.id.desc()).limit(100))
    grupos, vistos = [], set()
    for e in historial:
        destinatarios = str(e.datos.get('destinatarios') or '').strip()
        clave = ','.join(sorted(c.strip().lower() for c in destinatarios.split(',') if c.strip()))
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        grupos.append({'destinatarios': destinatarios, 'recepcion': e.recepcion, 'fecha': m._iso(e.creado_en)})
        if len(grupos) == 8:
            break
    return grupos


@router.post('/entregas/{ident}/reintentar')
def reintentar_entrega(ident: str, db: Session = Depends(get_db), op: Operador = Depends(requiere_supervisor)):
    e = db.get(AppEntrega, ident)
    if not e:
        raise HTTPException(404, 'Entrega no encontrada')
    if e.estado != 'PENDIENTE':
        raise HTTPException(409, 'Solo se reintentan entregas pendientes. Si requiere revisión, contacta al administrador.')
    e.proximo_en = utcnow()
    db.commit()
    return entregas.documento(e, tecnico=op.rol == Rol.ADMIN)


@router.post('/recepciones/{codigo}/entrega', status_code=201)
def cerrar_con_entrega(codigo: str, datos: dict = Body(...), db: Session = Depends(get_db),
                      op: Operador = Depends(requiere_supervisor)):
    try:
        return entregas.preparar(db, codigo, datos, _quien(op))
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


@router.get('/config/csv')
def leer_csv(db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    config = db.get(AppConfig, 'csv')
    return config.datos if config else {'formatos': []}


@router.put('/config/csv')
def guardar_csv(datos: dict = Body(...), db: Session = Depends(get_db),
                op: Operador = Depends(requiere_supervisor)):
    if op.rol != Rol.ADMIN:
        raise HTTPException(403, 'Solo un administrador configura los formatos')
    import json
    if not isinstance(datos.get('formatos'), list) or len(json.dumps(datos)) > 100_000:
        raise HTTPException(422, 'Formatos CSV invalidos o demasiado grandes')
    config = db.get(AppConfig, 'csv') or AppConfig(clave='csv')
    config.datos = {'formatos': datos['formatos']}
    config.usuario, config.modificado_en = _quien(op), utcnow()
    db.add(config)
    db.commit()
    return config.datos


@router.post('/recepciones/{codigo}/archivos/{tipo}', status_code=201)
def subir_archivo(codigo: str, tipo: str, datos: dict = Body(...), db: Session = Depends(get_db),
                   op: Operador = Depends(usuario_actual)):
    from app.services import archivos
    from app.services import operacion, drive
    if tipo == 'informe' and op.rol not in (Rol.ADMIN, Rol.SUPERVISOR):
        raise HTTPException(403, 'Solo un supervisor archiva informes')
    if tipo == 'foto':
        try:
            r = m.obtener(db, codigo, bloquear=True)
        except m.ErrorApp as exc:
            raise _traducir(exc) from None
        if r.estado not in m.ABIERTAS:
            raise HTTPException(409, 'Reabre la recepción antes de adjuntar nuevas fotos; el informe cerrado se conserva.')
        operacion.validar_evidencia(db, codigo, datos)
    a = None
    try:
        a = archivos.guardar(db, codigo, tipo, datos, _quien(op), confirmar=False)
        if tipo == 'foto':
            operacion.vincular_evidencia(db, a, datos, _quien(op), confirmar=False)
            drive.encolar(db, a)
        db.commit()
    except Exception:
        db.rollback()
        if a is not None and db.get(AppArchivo, a.id) is None:
            archivos.ruta(a).unlink(missing_ok=True)
        raise
    url = f'/api/app/archivos/{a.id}'
    return {'id': a.id, 'nombre': a.nombre, 'url': url, 'enlace': url,
            'bytes': a.bytes, 'sha256': a.sha256, 'destino': 'SERVIDOR'}


@router.get('/recepciones/{codigo}/imagenes')
def imagenes(codigo: str, sku: str = '', contexto: bool = False, offset: int = Query(0, ge=0),
             limite: int = Query(40, ge=1, le=100), db: Session = Depends(get_db), op: Operador = Depends(usuario_actual)):
    from app.services import archivos
    from app.services.normalize import normalizar_sku
    try:
        r = m.obtener(db, codigo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from None
    consulta = select(AppArchivo).where(AppArchivo.recepcion == r.codigo, AppArchivo.tipo == 'foto')
    from app.models import AppCopiaDrive
    retiradas = select(AppCopiaDrive.archivo_id).where(AppCopiaDrive.recepcion == r.codigo,
        (AppCopiaDrive.estado == 'ELIMINADA') | (AppCopiaDrive.datos['accion'].as_string() == 'papelera'))
    consulta = consulta.where(AppArchivo.id.not_in(retiradas))
    if sku:
        normal = normalizar_sku(sku)
        ids = set(db.scalars(select(AppArchivoSku.archivo_id).join(AppArchivo, AppArchivo.id == AppArchivoSku.archivo_id)
            .where(AppArchivoSku.sku == normal, AppArchivo.recepcion == r.codigo)))
        # Evidencias anteriores a esta actualización siguen ligadas por la bitácora.
        for ev in db.scalars(select(AppEvento).where(AppEvento.recepcion == r.codigo, AppEvento.sku == normal)):
            ids.update(str(url).split('/api/app/archivos/')[-1].split('?')[0] for url in (ev.datos or {}).get('fotos', []))
        if contexto:
            from app.models import AppEvidencia, AppUnidadLogistica
            todas = list(db.scalars(select(AppEvidencia).where(AppEvidencia.recepcion == r.codigo,
                AppEvidencia.eliminado_en.is_(None))))
            propias = [e for e in todas if e.sku == normal]
            unidades = {e.unidad_id for e in propias if e.unidad_id}
            origenes = {e.origen for e in propias if e.origen}
            for uid in list(unidades):
                u = db.get(AppUnidadLogistica, uid)
                if u and u.padre_id: unidades.add(u.padre_id)
            # Solo evidencia de contexto sin otro SKU: nunca mezclar productos distintos.
            ids.update(e.archivo_id for e in todas if not e.sku and
                (e.tipo == 'PACKING_INICIAL' or e.unidad_id in unidades or
                 (e.origen and e.origen in origenes)))
        consulta = consulta.where(AppArchivo.id.in_(ids))
    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    filas = list(db.scalars(consulta.order_by(AppArchivo.creado_en.desc(), AppArchivo.id).offset(offset).limit(limite)))
    etiquetas = {}
    if filas:
        for aid, cod in db.execute(select(AppArchivoSku.archivo_id, AppArchivoSku.sku).where(AppArchivoSku.archivo_id.in_([a.id for a in filas]))):
            etiquetas.setdefault(aid, []).append(cod)
    resultado = []
    from app.models import AppEvidencia
    metadatos = {}
    if filas:
        for e in db.scalars(select(AppEvidencia).where(AppEvidencia.archivo_id.in_([a.id for a in filas]),
                AppEvidencia.eliminado_en.is_(None))):
            metadatos.setdefault(e.archivo_id, []).append({'sku': e.sku, 'categoria': e.categoria,
                'tipo': e.tipo, 'unidadId': e.unidad_id, 'origen': e.origen})
    for a in filas:
        f = {'id': a.id, 'nombre': a.nombre, 'url': f'/api/app/archivos/{a.id}',
             'skus': etiquetas.get(a.id, []), 'bytes': a.bytes, 'creadoEn': m._iso(a.creado_en),
             'almacen': 'DRIVE' if a.drive_id else 'SERVIDOR', 'driveUrl': a.drive_url or '',
             'evidencias': metadatos.get(a.id, [])}
        if op.rol == Rol.ADMIN:
            f['rutaServidor'] = str(archivos.ruta(a)) if archivos.ruta(a).exists() else None
        resultado.append(f)
    entrega = next((e for e in db.scalars(select(AppEntrega).where(AppEntrega.recepcion == r.codigo)
        .order_by(AppEntrega.creado_en.desc()).limit(30)) if (e.resultado or {}).get('carpeta')), None)
    return {'total': total, 'archivos': resultado,
            'carpetaDrive': (entrega.resultado.get('carpetaFotos') or entrega.resultado.get('carpeta')) if entrega else ''}


@router.get('/archivos/{archivo_id}')
def archivo_local(archivo_id: str, db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    from app.services import archivos
    a = db.get(AppArchivo, archivo_id)
    if a is None:
        raise HTTPException(404, 'Archivo no encontrado')
    from app.models import AppCopiaDrive
    copia = db.get(AppCopiaDrive, archivo_id)
    if copia and (copia.estado == 'ELIMINADA' or copia.datos.get('accion') == 'papelera'):
        raise HTTPException(410, 'Evidencia retirada por supervisión; se conserva su trazabilidad')
    if not archivos.ruta(a).is_file():
        if a.drive_id:
            return RedirectResponse(f'https://drive.google.com/uc?export=view&id={a.drive_id}', headers={'Cache-Control': 'private, no-store'})
        raise HTTPException(404, 'Archivo no encontrado')
    return FileResponse(archivos.ruta(a), media_type=a.mime, filename=a.nombre,
        content_disposition_type='inline' if a.tipo == 'foto' else 'attachment',
        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


def _quien(op: Operador) -> str:
    """Con qué nombre queda firmado un evento."""
    return op.email or op.usuario


def _traducir(exc: m.ErrorApp) -> HTTPException:
    """Un error del modelo, con su código, en el sitio donde el handheld lo lee.

    El código viaja en el cuerpo porque la pantalla decide con él: CONFIRMAR_SOBRANTE
    abre el diálogo de confirmación, RECEPCION_CERRADA manda a elegir otra. Un
    texto suelto no se puede programar.
    """
    estado = {
        "NO_ENCONTRADA": 404, "NO_ENCONTRADO": 404,
        "DUPLICADA": 409, "ORIGEN_DUPLICADO": 409, "YA_CERRADA": 409,
        "NO_CERRADA": 409, "YA_ANULADO": 409, "RECEPCION_CERRADA": 409,
        "CONFIRMAR_SOBRANTE": 409,
    }.get(exc.codigo, 422)
    return HTTPException(estado, {"codigo": exc.codigo, "mensaje": str(exc)})


# --------------------------------------------------------------------------- #
# Recepciones
# --------------------------------------------------------------------------- #
@router.get("/recepciones")
def listar(max: int = Query(50, ge=1, le=500), mias: bool = False,
           db: Session = Depends(get_db), op: Operador = Depends(usuario_actual)):
    return m.listar_recepciones(db, max, usuario=_quien(op) if mias else None)


@router.get('/recepciones/{codigo}/catalogo-exportacion')
def catalogo_exportacion(codigo: str, db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    try:
        r = m.obtener(db, codigo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from None
    productos = db.scalars(select(Producto).join(AppSku, AppSku.sku == Producto.sku)
        .where(AppSku.recepcion == r.codigo))
    return {p.sku: {'unidad': (p.unidad or '') if p.cliente == r.cliente else '',
                    'familia': (p.familia or '') if p.cliente == r.cliente else '', 'existe': True,
                    'cliente': p.cliente, 'ean': p.ean or ''} for p in productos}


@router.get('/recepciones/{codigo}/codigos-barras')
def codigos_de_recepcion(codigo: str, db: Session = Depends(get_db), _: Operador = Depends(requiere_supervisor)):
    try:
        r = m.obtener(db, codigo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from None
    filas = db.scalars(select(ProductoCodigo).join(AppSku, AppSku.sku == ProductoCodigo.sku)
        .where(AppSku.recepcion == r.codigo, ProductoCodigo.exportar.is_(True))
        .order_by(ProductoCodigo.sku, ProductoCodigo.codigo))
    return [{'sku': f.sku, 'codigoBarras': f.valor, 'registradoPor': f.registrado_por,
             'fecha': m._iso(f.creado_en)} for f in filas]


@router.get('/recepciones-abiertas/por-codigo/{codigo}')
def buscar_en_recepciones(codigo: str, db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    from app.services.codigos import buscar
    normal = m.normalizar_codigo(codigo)
    producto = buscar(db, codigo)
    sku = producto.sku if producto else normal
    filas = db.scalars(select(AppRecepcion).join(AppSku, AppSku.recepcion == AppRecepcion.codigo)
        .where(AppRecepcion.estado.in_(m.ABIERTAS), AppSku.sku == sku, AppSku.en_packing_list.is_(True))
        .order_by(AppRecepcion.creado_en.desc())).all()
    return {'sku': sku, 'recepciones': [m.doc_recepcion(r) for r in filas]}


@router.post("/recepciones", status_code=201)
def crear(datos: dict = Body(...), db: Session = Depends(get_db),
          op: Operador = Depends(requiere_supervisor)):
    try:
        return m.crear_recepcion(db, datos, _quien(op))
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


@router.get("/recepciones/{codigo}")
def una(codigo: str, db: Session = Depends(get_db),
        _: Operador = Depends(usuario_actual)):
    try:
        r = m.obtener(db, codigo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc
    return m.doc_recepcion(r, m.operarios_de(db, r.codigo))


@router.delete("/recepciones/{codigo}")
def borrar(codigo: str, db: Session = Depends(get_db),
           op: Operador = Depends(requiere_supervisor)):
    """Irreversible: se lleva la bitácora y la auditoría. Solo un administrador."""
    if op.rol != Rol.ADMIN:
        raise HTTPException(403, "Solo un administrador puede borrar una recepción")
    try:
        return m.borrar_recepcion(db, codigo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


@router.get("/recepciones/{codigo}/{coleccion}")
def subcoleccion(codigo: str, coleccion: str, max: int = Query(0, ge=0, le=5000),
                 db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    """Las subcolecciones que lee la aplicación: líneas, SKU, adicionales, eventos.

    Una sola ruta para las cinco porque el navegador las lee con una sola
    función (`leerColeccion`): cuantas menos formas haya de pedir lo mismo,
    menos sitios donde puedan discrepar.
    """
    if coleccion not in COLECCIONES:
        raise HTTPException(404, f"No existe la colección «{coleccion}»")
    try:
        return m.leer_coleccion(db, codigo, coleccion, max)
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


@router.get('/recepciones/{codigo}/estado-sku/{sku}')
def estado_sku(codigo: str, sku: str, db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    from app.services.normalize import normalizar_sku
    try:
        r = m.obtener(db, codigo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc
    s = db.scalar(select(AppSku).where(AppSku.recepcion == r.codigo, AppSku.sku == normalizar_sku(sku)))
    return m.doc_sku(s) if s else None


# --------------------------------------------------------------------------- #
# Packing list
# --------------------------------------------------------------------------- #
@router.post("/recepciones/{codigo}/packing-list")
def cargar_packing_list(codigo: str, cuerpo: dict = Body(...),
                        db: Session = Depends(get_db),
                        op: Operador = Depends(requiere_supervisor)):
    """Recibe el packing list YA LEÍDO por el navegador.

    El archivo no se sube: lo lee el navegador con la rutina que conoce los
    formatos reales de cada cliente y manda el resultado traducido. Dos lectores
    de Excel, uno en cada lado, serían dos cosas que pueden discrepar sobre
    cuántas unidades declara una fila.
    """
    try:
        from app.services.operacion import configuracion, obtener_ingreso
        from app.models import AppIngreso
        if db.get(AppIngreso, codigo) and configuracion(db)['evidencias']['bloquear'] and obtener_ingreso(db, codigo)['avisos']:
            raise HTTPException(409, 'Completa las evidencias exigidas por ADMIN antes de cargar el packing list')
        return m.guardar_packing_list(
            db, codigo,
            resultado=cuerpo.get("resultado") or {},
            origen=cuerpo.get("origen") or "PRINCIPAL",
            archivo=cuerpo.get("archivo"),
        )
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


@router.post("/packing-lists/parecidos")
def parecidos(cuerpo: dict = Body(...), db: Session = Depends(get_db),
              _: Operador = Depends(usuario_actual)):
    """¿Este packing list ya se cargó antes? Se pregunta por contenido."""
    return m.packing_lists_parecidos(
        db, cuerpo.get("resumen") or {}, excluir=cuerpo.get("excluirRecepcion"))


# --------------------------------------------------------------------------- #
# Conteo
# --------------------------------------------------------------------------- #
@router.post("/recepciones/{codigo}/conteos")
def contar(codigo: str, cuerpo: dict = Body(...), db: Session = Depends(get_db),
           op: Operador = Depends(usuario_actual)):
    try:
        return m.registrar_conteo(db, codigo, _quien(op), cuerpo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


@router.post("/recepciones/{codigo}/no-encontrado")
def no_encontrado(codigo: str, cuerpo: dict = Body(...), db: Session = Depends(get_db),
                  op: Operador = Depends(usuario_actual)):
    try:
        return m.declarar_no_encontrado(db, codigo, _quien(op), cuerpo)
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


@router.post("/recepciones/{codigo}/conteos/{evento_id}/anular")
def anular(codigo: str, evento_id: str, cuerpo: dict = Body(default={}),
           db: Session = Depends(get_db), op: Operador = Depends(usuario_actual)):
    try:
        return m.anular_conteo(db, codigo, _quien(op), evento_id,
                               cuerpo.get("motivo") or "")
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


@router.post("/recepciones/{codigo}/auditoria")
def auditar(codigo: str, cuerpo: dict = Body(...), db: Session = Depends(get_db),
            op: Operador = Depends(usuario_actual)):
    return m.registrar_auditoria(db, codigo, _quien(op),
                                 cuerpo.get("tipo") or "AUDITORIA",
                                 cuerpo.get("detalle") or {})


@router.get("/recepciones/{codigo}/skus/{sku}/recalcular")
def recalcular(codigo: str, sku: str, db: Session = Depends(get_db),
               _: Operador = Depends(requiere_supervisor)):
    """Vuelve a armar el agregado desde el libro mayor. La verdad son los eventos."""
    try:
        return m.recalcular_sku(db, codigo, sku)
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


# --------------------------------------------------------------------------- #
# Cierre
# --------------------------------------------------------------------------- #
@router.post("/recepciones/{codigo}/cerrar")
def cerrar(codigo: str, db: Session = Depends(get_db),
           op: Operador = Depends(requiere_supervisor)):
    try:
        return m.cerrar_recepcion(db, codigo, _quien(op))
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


@router.post("/recepciones/{codigo}/reabrir")
def reabrir(codigo: str, cuerpo: dict = Body(default={}), db: Session = Depends(get_db),
            op: Operador = Depends(requiere_supervisor)):
    try:
        return m.reabrir_recepcion(db, codigo, _quien(op), cuerpo.get("motivo") or "")
    except m.ErrorApp as exc:
        raise _traducir(exc) from exc


# --------------------------------------------------------------------------- #
# Catálogo
# --------------------------------------------------------------------------- #
@router.get("/catalogo/{codigo}")
def catalogo(codigo: str, cliente: str | None = None, db: Session = Depends(get_db),
             _: Operador = Depends(usuario_actual)):
    """Lo que la pantalla necesita saber de un código escaneado."""
    r = depot_svc.resolver_codigo(db, codigo, usar_api=False)
    from app.services.catalogo_programado import posiciones_de
    return {
        "sku": r.sku, "existe": r.existe, "descripcion": r.descripcion,
        "ean": r.ean, "unidad": r.unidad, "inactivo": r.inactivo,
        "fuente": r.fuente, "degradado": r.degradado,
        "candidatos": r.candidatos, "mensaje": r.mensaje, "accion": r.accion,
        **posiciones_de(db, r.sku, cliente),
    }


@router.post("/catalogo/{codigo}/equivalencia")
def equivalencia(codigo: str, cuerpo: dict = Body(...), db: Session = Depends(get_db),
                 op: Operador = Depends(usuario_actual)):
    """Apunta que un código escaneado corresponde a un SKU del maestro.

    Pasa con las etiquetas del proveedor: el código del bulto no es el del
    producto. La primera vez lo resuelve una persona; a partir de ahí lo resuelve
    el escáner. Sin esto, cada operario vuelve a resolverlo desde cero.
    """
    from app.services.codigos import guardar
    c = guardar(db, codigo, cuerpo.get('sku'), _quien(op))
    return {'sku': c.sku, 'codigoAlternativo': c.codigo, 'codigoBarras': c.valor}


@router.post('/catalogo/codigos/importar')
def importar_codigos(datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(requiere_supervisor)):
    from app.services.codigos import guardar
    filas = datos.get('filas')
    if not isinstance(filas, list) or not 1 <= len(filas) <= 5000:
        raise HTTPException(422, 'El archivo debe contener entre 1 y 5000 filas')
    try:
        for i, f in enumerate(filas, 2):
            if not isinstance(f, dict):
                raise HTTPException(422, f'Fila {i}: datos no válidos')
            try:
                guardar(db, f.get('codigoBarras'), f.get('sku'), _quien(op), confirmar=False)
            except HTTPException as exc:
                raise HTTPException(exc.status_code, f'Fila {i}: {exc.detail}') from None
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'procesadas': len(filas), 'mensaje': 'Códigos asociados a productos existentes. No se crearon productos ni conteos.'}
