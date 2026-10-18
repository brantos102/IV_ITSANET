"""Resolución manual y limpieza visible del historial, con auditoría durable."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppEntrega,AppInforme,AppConfig,utcnow
from app.services import app_modelo as m,entregas,ajustes
from app.services.instantaneas import expandir


def bloquear(db,ident,datos):
    e=db.get(AppEntrega,ident)
    if not e:raise HTTPException(404,'Entrega no encontrada')
    r=m.obtener(db,e.recepcion,bloquear=True)
    grupo=list(db.scalars(select(AppEntrega).where(AppEntrega.recepcion==r.codigo)
        .order_by(AppEntrega.id).with_for_update().execution_options(populate_existing=True)))
    e=next(e for e in grupo if e.id==ident)
    if datos.get('versionGestion')!=entregas.documento(e)['versionGestion']:
        raise HTTPException(409,'Otro usuario o el proceso de envío actualizó esta entrega. Actualiza antes de continuar.')
    motivo=str(datos.get('motivo') or '').strip()
    if not 10<=len(motivo)<=300:raise HTTPException(422,'Indica el motivo, entre 10 y 300 caracteres.')
    return r,e,grupo,motivo


def declarar(db,ident,datos,usuario):
    r,e,grupo,motivo=bloquear(db,ident,datos)
    if datos.get('confirmarEnviado') is not True:
        raise HTTPException(422,'Confirma que verificaste el mensaje y los documentos en Enviados.')
    if (e.datos.get('correoManual') or {}).get('estado')=='DECLARADO_ENVIADO':return entregas.documento(e)
    from app.services.recuperar_entrega import _validar
    _validar(db,e,grupo,manual_confirmado=True)
    from app.services.correo_redactado import vista,clave_config
    v=vista(db,r.codigo,usuario,ident)
    if datos.get('correoVersion')!=v['version']:
        raise HTTPException(409,'El correo revisado cambió o corresponde a otro usuario. Actualiza antes de declarar el envío manual.')
    registro={'estado':'DECLARADO_ENVIADO','usuario':usuario,'fecha':utcnow().isoformat(),
        'motivo':motivo,'version':v['version'],'entregaId':ident,
        'destinatarios':e.datos.get('destinatarios',''),'asunto':v['asunto']}
    for g in grupo:
        if g.estado in ('PENDIENTE','REVISION'):
            g.estado='CANCELADA';g.datos={**g.datos,'anulacion':{'usuario':usuario,'fecha':registro['fecha'],
                'motivo':'Correo ya enviado manualmente; automático detenido. '+motivo}}
    final=expandir(e.datos).get('correoFinal') or {k:v[k] for k in ('asunto','html','texto','remitente','campos','imagenesDrive')}
    e.datos={**e.datos,'correoManual':registro,'correoFinal':final}
    if e.datos.get('informeId'):
        f=db.get(AppInforme,e.datos['informeId'])
        if f:f.estado='MANUAL_DECLARADO'
    f=db.get(AppConfig,clave_config(r.codigo,manual=True)) or AppConfig(clave=clave_config(r.codigo,manual=True))
    f.datos=registro;f.usuario=usuario;db.add(f)
    ajustes.auditar(db,usuario,'ENVIO_MANUAL_HISTORICO_DECLARADO',r.codigo,registro)
    db.commit();return entregas.documento(e)


def archivar(db,ident,datos,usuario):
    r,e,grupo,motivo=bloquear(db,ident,datos)
    ocultar=datos.get('archivar')
    if type(ocultar) is not bool:raise HTTPException(422,'Indica si deseas archivar o restaurar.')
    if ocultar and (e.estado in entregas.ACTIVAS or (e.datos.get('correoManual') or {}).get('estado')=='PREPARADO'):
        raise HTTPException(409,'Resuelve el envío antes de retirarlo del historial. Puedes declarar el envío manual ya realizado.')
    indice=db.get(AppConfig,'he:'+e.id)
    if ocultar:
        indice=indice or AppConfig(clave='he:'+e.id)
        indice.datos={'entregaId':e.id};indice.usuario=usuario;db.add(indice)
    elif indice:db.delete(indice)
    e.datos={**e.datos,'historialOculto':ocultar,'archivoHistorial':{'usuario':usuario,'fecha':utcnow().isoformat(),'motivo':motivo}}
    ajustes.auditar(db,usuario,'HISTORIAL_ENTREGA_ARCHIVADO' if ocultar else 'HISTORIAL_ENTREGA_RESTAURADO',r.codigo,{'entregaId':ident,'motivo':motivo})
    db.commit();return entregas.documento(e)
