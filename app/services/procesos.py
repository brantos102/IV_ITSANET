"""Registro operativo persistente, sin cuerpos de correo ni credenciales."""
import logging
from sqlalchemy import select, func
from app.models import AppAuditoriaGeneral, AppCopiaDrive, AppEntrega, AppArchivo, utcnow
from app.services.ajustes import auditar


def registrar(db, proceso, estado, referencia, usuario='', **datos):
    # Solo aceptar información operativa explícita. Nunca serializar excepciones HTTP.
    permitidos={'archivoId','recepcion','intento','codigo','duracionMs','cantidad','etapa','tipo'}
    d={k:v for k,v in datos.items() if k in permitidos}
    d.update(proceso=proceso,estado=estado)
    auditar(db,usuario or 'sistema','PROCESO_'+proceso,str(referencia)[:120],d)
    logging.getLogger('iv_itsanet.procesos').log(logging.WARNING if estado=='ERROR' else logging.INFO,
        'proceso=%s estado=%s ref=%s codigo=%s',proceso,estado,referencia,d.get('codigo',''))


def consultar(db, recepcion='', estado='', limite=100):
    from app.services.app_modelo import _iso
    q=select(AppAuditoriaGeneral.id).where(AppAuditoriaGeneral.accion.like('PROCESO_%'))
    if recepcion:q=q.where(AppAuditoriaGeneral.datos['recepcion'].as_string()==recepcion)
    if estado:q=q.where(AppAuditoriaGeneral.datos['estado'].as_string()==estado)
    ids=list(db.scalars(q.order_by(AppAuditoriaGeneral.creado_en.desc(),AppAuditoriaGeneral.id.desc()).limit(limite)))
    filas={f.id:f for f in db.scalars(select(AppAuditoriaGeneral).where(AppAuditoriaGeneral.id.in_(ids)))} if ids else {}
    def contar(modelo, columna):
        q=select(columna,func.count()).group_by(columna)
        if recepcion:q=q.where(modelo.recepcion==recepcion)
        return dict(db.execute(q).all())
    fotos=select(AppCopiaDrive.archivo_id,AppCopiaDrive.recepcion,AppCopiaDrive.estado,AppCopiaDrive.error,
        AppCopiaDrive.intentos,AppCopiaDrive.proximo_en,AppArchivo.nombre).join(AppArchivo,AppArchivo.id==AppCopiaDrive.archivo_id).where(AppCopiaDrive.estado.in_(['PENDIENTE','PROCESANDO','REVISION']))
    correos=select(AppEntrega.id,AppEntrega.recepcion,AppEntrega.estado,AppEntrega.error,AppEntrega.intentos,
        AppEntrega.proximo_en).where(AppEntrega.estado.in_(['PENDIENTE','PROCESANDO','REVISION']))
    if recepcion:fotos=fotos.where(AppCopiaDrive.recepcion==recepcion);correos=correos.where(AppEntrega.recepcion==recepcion)
    incidencias=[{'proceso':'FOTO','referencia':i,'recepcion':r,'estado':e,'mensaje':err or '',
        'intento':n,'proximoEn':_iso(p),'nombre':nombre} for i,r,e,err,n,p,nombre in db.execute(fotos.limit(100))]
    incidencias += [{'proceso':'CORREO','referencia':i,'recepcion':r,'estado':e,'mensaje':err or '',
        'intento':n,'proximoEn':_iso(p)} for i,r,e,err,n,p in db.execute(correos.limit(100))]
    return {'consultadoEn':utcnow().isoformat(),'fotos':contar(AppCopiaDrive,AppCopiaDrive.estado),
        'correos':contar(AppEntrega,AppEntrega.estado),
        'incidencias':incidencias,
        'eventos':[{'id':i,'fecha':_iso(filas[i].creado_en),'usuario':filas[i].usuario,
            'referencia':filas[i].referencia,**filas[i].datos} for i in ids]}
