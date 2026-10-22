"""Preparación durable de carpetas, sin bloquear el registro ni tocar fotografías."""
import hashlib
import time
from uuid import uuid4
from sqlalchemy import select
from app.models import AppConfig


def clave(codigo):return 'drive:r:'+hashlib.sha256(codigo.encode()).hexdigest()[:30]


def encolar(db,codigo):
    from app.services.fotos_embarques import informacion
    from app.services.enlaces_correo import base_embarque
    _,_,_,embarques=informacion(db,codigo)
    rutas=[base_embarque(e)[0] for e in embarques]
    f=db.get(AppConfig,clave(codigo))
    if f and f.datos.get('embarques')==rutas:return
    f=f or AppConfig(clave=clave(codigo));f.datos={**(f.datos or {}),'recepcion':codigo,'embarques':rutas,'estado':'PENDIENTE','proximo':0}
    db.add(f)


def procesar_uno(db):
    from app.services import operacion,entregas,remitentes
    # Recuperar una reserva vencida permite reiniciar el servidor sin perder la tarea.
    candidatas=list(db.scalars(select(AppConfig).where(AppConfig.clave.like('drive:r:%'))))
    f=next((f for f in candidatas if f.datos.get('estado')!='LISTA' and f.datos.get('proximo',0)<=time.time()),None)
    if not f:return False
    f=db.scalar(select(AppConfig).where(AppConfig.clave==f.clave).with_for_update().execution_options(populate_existing=True))
    if f.datos.get('estado')=='LISTA' or f.datos.get('proximo',0)>time.time():return True
    original=dict(f.datos)
    from app.models import AppIngreso,AppLinea
    if not db.get(AppIngreso,original['recepcion']) and not db.scalar(select(AppLinea.id).where(AppLinea.recepcion==original['recepcion']).limit(1)):
        f.datos={**original,'proximo':time.time()+10};db.commit();return True
    f.datos={**original,'proximo':time.time()+300};db.commit()
    try:
        d=operacion.destino_drive(db,original['recepcion']);d['usuario']=remitentes.responsable(db,original['recepcion'],d.pop('supervisor'))
        if not entregas.configurado(db,d['usuario']):raise RuntimeError('Configura la conexión Drive del responsable de la recepción.')
        d['embarques']=original['embarques'];db.rollback()
        estado=entregas.llamar('estado',uuid4().hex,d)
        if 'carpetasRecepcion62' not in estado.get('capacidades',[]):raise RuntimeError('Publica la versión 62 de Servidor.gs en el mismo /exec para preparar las carpetas por embarque.')
        respuesta=entregas.llamar('prepararCarpeta',uuid4().hex,d)
        from app.services.enlaces_correo import carpeta_url
        carpeta=carpeta_url(respuesta.get('carpeta'))
        if not carpeta:raise RuntimeError('Drive no confirmó la carpeta de la recepción.')
        f=db.scalar(select(AppConfig).where(AppConfig.clave==f.clave).with_for_update().execution_options(populate_existing=True))
        if f.datos.get('embarques')!=original['embarques']:db.rollback();return True
        f.datos={**original,'estado':'LISTA','carpeta':carpeta,'proximo':0}
        operacion.auditoria(db,original['recepcion'],d['usuario'],'CARPETA_DRIVE_VERIFICADA',{'carpeta':carpeta})
        from app.services.procesos import registrar
        registrar(db,'CARPETAS','LISTA',original['recepcion'],d['usuario'],recepcion=original['recepcion'])
    except Exception as exc:
        db.rollback();f=db.get(AppConfig,f.clave)
        # El estado expone la incidencia sin filtrar credenciales del puente.
        if f and f.datos.get('embarques')==original['embarques']:
            f.datos={**original,'estado':'PENDIENTE','proximo':time.time()+300,'mensaje':str(exc)[:250] if type(exc) is RuntimeError else 'Carpetas pendientes: revisa la conexión Google de almacenamiento.'}
            from app.services.procesos import registrar
            registrar(db,'CARPETAS','ERROR',original['recepcion'],recepcion=original['recepcion'],codigo=type(exc).__name__)
    db.commit();return True


def trabajar():
    from app.db import SessionLocal
    with SessionLocal() as db:return procesar_uno(db)
