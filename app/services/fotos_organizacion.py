"""Revisión y programación de nombres y carpetas, sin reenviar informes."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppArchivo,AppArchivoIdentidad,AppCopiaDrive,AppEvidencia,utcnow
from app.services import app_modelo as m,drive,fotos_identidad as identidad,operacion


def fotos(db,codigo,bloquear=False):
    retiradas=select(AppCopiaDrive.archivo_id).where(AppCopiaDrive.recepcion==codigo,
        (AppCopiaDrive.estado=='ELIMINADA')|(AppCopiaDrive.datos['accion'].as_string()=='papelera'))
    q=select(AppArchivo).where(AppArchivo.recepcion==codigo,AppArchivo.tipo=='foto',
        AppArchivo.id.not_in(retiradas)).order_by(AppArchivo.creado_en,AppArchivo.id)
    if bloquear:q=q.with_for_update().execution_options(populate_existing=True)
    return list(db.scalars(q))


def plan(db,codigo,bloquear=False):
    try:r=m.obtener(db,codigo)
    except m.ErrorApp as exc:raise HTTPException(404,str(exc)) from None
    q=select(AppArchivoIdentidad).where(AppArchivoIdentidad.recepcion==r.codigo)
    if bloquear:q=q.with_for_update().execution_options(populate_existing=True)
    ids={i.archivo_id:i for i in db.scalars(q)}
    siguiente=max((i.secuencia for i in ids.values()),default=0)
    propuestas={}
    # Incluye retiradas en la asignación para que el número no vuelva a usarse.
    q=select(AppArchivo).where(AppArchivo.recepcion==r.codigo,AppArchivo.tipo=='foto').order_by(AppArchivo.creado_en,AppArchivo.id)
    if bloquear:q=q.with_for_update().execution_options(populate_existing=True)
    for a in db.scalars(q):
        meta=ids.get(a.id)
        if not meta:
            siguiente+=1;meta=AppArchivoIdentidad(archivo_id=a.id,recepcion=r.codigo,secuencia=siguiente,nombre_original=a.nombre,datos={})
        propuestas[a.id]=identidad.nombre(db,a,meta)
    from app.services.fotos_embarques import informacion
    fuente_embarques=informacion(db,codigo,actual=bloquear)
    copias={j.archivo_id:j for j in db.scalars(select(AppCopiaDrive).where(AppCopiaDrive.recepcion==r.codigo))}
    filas=[]
    for a in fotos(db,r.codigo,bloquear):
        q=select(AppEvidencia).where(AppEvidencia.archivo_id==a.id,AppEvidencia.eliminado_en.is_(None)).order_by(AppEvidencia.creado_en,AppEvidencia.id)
        if bloquear:q=q.with_for_update().execution_options(populate_existing=True)
        es=list(db.scalars(q))
        from app.services.fotos_embarques import ruta,asignado,contexto
        rutas=[ruta(db,e,fuente=fuente_embarques) for e in es]
        j=copias.get(a.id)
        estados=[drive.ubicacion_evidencia(db,e,j,fuente=fuente_embarques) for e in es]
        filas.append({'archivoId':a.id,'actual':a.nombre,'nuevo':propuestas[a.id],
            'url':'/api/app/archivos/'+a.id,'driveUrl':a.drive_url or '',
            'rutas':rutas,'clasificaciones':list(dict.fromkeys(e.categoria for e in es)),
            'ubicaciones':estados,
            'requiereActualizar':any(x['estado']!='SINCRONIZADA' for x in estados),
            'vinculos':[{'id':e.id,'origen':e.origen,'unidadId':e.unidad_id,'tipo':e.tipo,'protocolo':e.protocolo,'sku':e.sku or '', 'categoria':e.categoria,'embarque':asignado(db,e,fuente=fuente_embarques),
                **contexto(db,codigo,e.sku or '',e.origen or '',e.unidad_id or '',fuente=fuente_embarques)} for e in es]})
    huella=hashlib.sha256(json.dumps(filas,ensure_ascii=True,sort_keys=True).encode()).hexdigest()
    return {'estadoRecepcion':r.estado,'total':len(filas),'huella':huella,'archivos':filas}


def programar(db,codigo,usuario,datos):
    try:r=m.obtener(db,codigo,bloquear=True)
    except m.ErrorApp as exc:raise HTTPException(404,str(exc)) from None
    if r.estado not in {*m.ABIERTAS,'CERRADA'}:raise HTTPException(409,'Esta recepción no permite organizar sus fotografías.')
    if datos.get('confirmar') is not True:raise HTTPException(422,'Revisa los nombres y confirma la organización.')
    actual=plan(db,r.codigo,bloquear=True)
    if datos.get('huella')!=actual['huella']:raise HTTPException(409,'Las fotografías cambiaron. Actualiza la vista previa antes de organizar.')
    fs=fotos(db,r.codigo,bloquear=True)
    tareas=list(db.scalars(select(AppCopiaDrive).where(AppCopiaDrive.archivo_id.in_([a.id for a in fs])).with_for_update().execution_options(populate_existing=True)))
    if any(j.estado=='PROCESANDO' for j in tareas):raise HTTPException(409,'Hay fotografías copiándose a Drive. Espera su confirmación y vuelve a revisar.')
    asignaciones=datos.get('asignaciones',{})
    permitidos={v['id'] for f in actual['archivos'] for v in f['vinculos']}
    if not isinstance(asignaciones,dict) or not set(asignaciones)<=permitidos:raise HTTPException(422,'Asigna únicamente fotos activas de esta recepción.')
    from app.services.fotos_embarques import resolver,registrar,asignado
    cambios=[]
    for ident,emb in asignaciones.items():
        e=db.get(AppEvidencia,ident)
        nuevo=resolver(db,r.codigo,{'sku':e.sku,'origen':e.origen,'unidadId':e.unidad_id,'embarqueFoto':emb})
        antes=asignado(db,e)
        if antes!=nuevo:cambios.append({'evidenciaId':e.id,'archivoId':e.archivo_id,'antes':antes,'despues':nuevo})
    if cambios:
        from app.services.entregas import activas
        if activas(db,r.codigo):raise HTTPException(409,'Hay un envío automático pendiente o en revisión. Resuélvelo en Entregas antes de cambiar el embarque de sus fotografías; se conserva el correo ya revisado.')
    identidad.asegurar_recepcion(db,r.codigo)
    for x in cambios:registrar(db,x['archivoId'],x['evidenciaId'],x['despues'])
    n=0
    for a in fs:
        j=drive.encolar(db,a)
        if j.estado in ('PENDIENTE','REVISION'):
            j.estado='PENDIENTE';j.proximo_en=utcnow();j.error=None;n+=1
    operacion.auditoria(db,r.codigo,usuario,'FOTOS_ORGANIZADAS',{'cantidad':len(fs),'programadas':n,
        'huella':actual['huella'],'embarques':cambios,'nombres':[{k:f[k] for k in ('archivoId','actual','nuevo')} for f in actual['archivos']]})
    db.commit()
    return {'programadas':n,'mensaje':f'{n} foto(s) programadas para organizar. Se conservan el archivo, la clasificación y los conteos; no se envía correo.'}


def actualizar_por_embarques(db,codigo):
    """Invocar bajo bloqueo de recepción tras guardar un packing o sus embarques."""
    if not db.scalar(select(AppArchivoIdentidad.archivo_id).where(AppArchivoIdentidad.recepcion==codigo).limit(1)):return
    identidad.asegurar_recepcion(db,codigo)
    for a in fotos(db,codigo):drive.encolar(db,a)
