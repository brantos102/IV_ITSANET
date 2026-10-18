from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Operador, Rol
from app.security import requiere_supervisor, usuario_actual
from app.services import operacion as svc
from app.services import ajustes
from app.services import app_modelo as m

router = APIRouter(prefix='/api/operacion', tags=['operacion'])


def admin(op=Depends(requiere_supervisor)):
    if op.rol != Rol.ADMIN: raise HTTPException(403, 'Solo ADMIN configura la operación')
    return op


@router.get('/preferencias')
def preferencias(db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    return svc.configuracion(db, publica=True)


@router.get('/config')
def configuracion(db: Session = Depends(get_db), _: Operador = Depends(admin)):
    return svc.configuracion(db)


@router.put('/config')
def guardar(datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(admin)):
    return svc.guardar_config(db, datos, op.email or op.usuario)


@router.get('/supervisores')
def supervisores(db: Session = Depends(get_db), _: Operador = Depends(requiere_supervisor)):
    return [{'email': p.email or p.usuario, 'nombre': p.nombre} for p in db.scalars(select(Operador)
        .where(Operador.activo.is_(True), Operador.rol.in_([Rol.ADMIN, Rol.SUPERVISOR])))]


@router.get('/recepciones/{codigo}/ingreso')
def ingreso(codigo: str, db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    try: return svc.obtener_ingreso(db, codigo)
    except m.ErrorApp as exc: raise HTTPException(404, str(exc)) from None


@router.put('/recepciones/{codigo}/ingreso')
def actualizar_ingreso(codigo: str, datos: dict = Body(...), db: Session = Depends(get_db),
                       op: Operador = Depends(requiere_supervisor)):
    try: return svc.guardar_ingreso(db, codigo, datos, op.email or op.usuario)
    except m.ErrorApp as exc: raise HTTPException(404, str(exc)) from None


@router.post('/recepciones/{codigo}/unidades')
def unidad(codigo: str, datos: dict = Body(...), db: Session = Depends(get_db),
           op: Operador = Depends(requiere_supervisor)):
    try: return svc.guardar_unidad(db, codigo, datos, op.email or op.usuario)
    except m.ErrorApp as exc: raise HTTPException(404, str(exc)) from None


@router.post('/lecturas/resolver')
def resolver(datos: dict = Body(...), db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    from app.services.lecturas import resolver
    return resolver(db, datos.get('lectura'), datos.get('recepcion'))


@router.post('/recepciones/{codigo}/bultos')
def bultos(codigo: str, datos: dict = Body(...), db: Session = Depends(get_db), op: Operador = Depends(requiere_supervisor)):
    return svc.ajustar_bultos(db, codigo, datos, op.email or op.usuario)


@router.delete('/evidencias/{archivo_id}')
def eliminar_evidencia(archivo_id: str, db: Session = Depends(get_db), op: Operador = Depends(requiere_supervisor)):
    from app.services.drive import eliminar
    try: return eliminar(db, archivo_id, op.email or op.usuario)
    except m.ErrorApp as exc: raise HTTPException(404, str(exc)) from None


@router.get('/recepciones/{codigo}/drive')
def estado_drive(codigo: str, db: Session = Depends(get_db), op: Operador = Depends(requiere_supervisor)):
    from app.models import AppCopiaDrive, AppEvento
    from app.services.operacion import destino_drive
    codigo = m.obtener(db, codigo).codigo
    copias = list(db.scalars(select(AppCopiaDrive).where(AppCopiaDrive.recepcion == codigo)))
    from app.services.drive import resumen_fotos
    salida = {'sincronizacion': resumen_fotos(db, codigo), 'estados': {e: sum(c.estado == e for c in copias)
        for e in ('PENDIENTE', 'PROCESANDO', 'REVISION', 'COPIADA', 'ELIMINADA')},
        'carpetas': sorted({c.datos.get('carpetaRecepcionUrl') for c in copias if c.datos.get('carpetaRecepcionUrl')})}
    confirmada = db.scalar(select(AppEvento).where(AppEvento.recepcion == codigo,
        AppEvento.tipo == 'AUDITORIA', AppEvento.motivo == 'CARPETA_DRIVE_VERIFICADA')
        .order_by(AppEvento.creado_en.desc(), AppEvento.id.desc()).limit(1))
    if confirmada and (confirmada.datos or {}).get('carpeta'):
        salida['carpetas'] = sorted(set(salida['carpetas']) | {confirmada.datos['carpeta']})
    from app.services.remitentes import responsable
    operativo=destino_drive(db,codigo)
    salida['destinoOperativo']={k:operativo[k] for k in ('cliente','marca')}
    salida['destinoOperativo']['supervisor']=responsable(db,codigo) or operativo['supervisor']
    if op.rol in (Rol.ADMIN,Rol.SUPERVISOR):
        from app.services.remitentes import responsable
        salida['destino'] = destino_drive(db, codigo)
        salida['destino']['supervisor'] = responsable(db, codigo) or salida['destino']['supervisor']
        salida['avisos'] = sorted({c.error for c in copias if c.error})
        from app.models import AppArchivo
        salida['archivos'] = [{'id': a.id, 'nombre': a.nombre, 'estado': c.estado if c else 'SIN_COLA',
            'sku':c.datos.get('sku','') if c else '', 'tipo':c.datos.get('tipoEvidencia','') if c else '',
            'error': c.error if c and c.estado in ('PENDIENTE','REVISION') else None,
            'enlace': a.drive_url if a.drive_id else None,
            'carpeta': (c.datos.get('carpeta') or '') if c and c.estado == 'COPIADA' else '',
            'ruta': c.datos.get('ruta', []) if c else []}
            for a, c in db.execute(select(AppArchivo, AppCopiaDrive).outerjoin(AppCopiaDrive,
                AppCopiaDrive.archivo_id == AppArchivo.id).where(AppArchivo.recepcion == codigo,
                AppArchivo.tipo == 'foto').order_by(AppArchivo.creado_en, AppArchivo.id))
            if not c or c.estado != 'ELIMINADA' and c.datos.get('accion') != 'papelera']
    return salida


@router.post('/recepciones/{codigo}/drive/preparar')
def preparar_drive(codigo: str, db: Session = Depends(get_db), op: Operador = Depends(requiere_supervisor)):
    from uuid import uuid4
    from app.services import entregas, remitentes, drive
    destino = svc.destino_drive(db, codigo)
    correo, _ = remitentes.elegir(db, codigo, {'modoRemitente': 'RESPONSABLE'}, op.email or op.usuario)
    datos = {**destino, 'usuario': correo}
    datos.pop('supervisor', None)
    db.rollback()
    try:
        estado = entregas.llamar('estado', uuid4().hex, datos)
        if str(estado.get('remitente') or '').lower() != correo:
            raise RuntimeError('Google no confirmó la cuenta responsable.')
        if destino['carpetaRaiz'] and estado.get('carpetaId') != destino['carpetaRaiz']:
            raise RuntimeError('Google no confirmó la carpeta raíz configurada.')
        if 'prepararCarpeta' not in estado.get('capacidades', []):
            raise RuntimeError('Actualiza Servidor.gs en Apps Script y publica una versión nueva del mismo despliegue /exec para crear y comprobar las carpetas.')
        resultado = entregas.llamar('prepararCarpeta', uuid4().hex, datos)
        if not str(resultado.get('carpeta') or '').startswith('https://drive.google.com/'):
            raise RuntimeError('Drive no confirmó el enlace de la carpeta de recepción.')
    except Exception as exc:
        mensaje = str(exc) if type(exc) is RuntimeError else 'No se pudo verificar Drive. Revisa el puente del responsable.'
        raise HTTPException(502, mensaje + ' No se envió ningún correo.') from None
    db.rollback()
    m.obtener(db, codigo, bloquear=True)
    svc.auditoria(db, codigo, op.email or op.usuario, 'CARPETA_DRIVE_VERIFICADA',
        {'remitente': correo, 'carpeta': resultado['carpeta']})
    reintento = drive.reintentar_pendientes(db, codigo, op.email or op.usuario)
    return {'carpeta': resultado['carpeta'], 'remitente': correo,
        'programadas': reintento['programadas'], 'mensaje': 'Carpeta confirmada. Las fotos pendientes se copiarán en segundo plano; este paso no envía correo.'}


@router.post('/repositorios/{ident}/probar')
def probar_repositorio(ident: str, datos: dict = Body(default={}), db: Session = Depends(get_db), _: Operador = Depends(admin)):
    from uuid import uuid4
    from app.services.entregas import llamar
    repo = next((r for r in svc.configuracion(db)['repositorios'] if r['id'] == ident), None)
    if not repo: raise HTTPException(404, 'Repositorio no encontrado')
    supervisor = str(datos.get('supervisor') or repo.get('supervisor') or '').strip().lower()
    op = db.scalar(select(Operador).where(Operador.email == supervisor, Operador.activo.is_(True),
        Operador.rol.in_([Rol.ADMIN, Rol.SUPERVISOR])))
    if not op: raise HTTPException(422, 'Indica el correo de un supervisor activo con puente configurado')
    try:
        r = llamar('estado', uuid4().hex, {'usuario': supervisor, 'carpetaRaiz': repo['carpetaId']})
        if r.get('versionPuente', 0) < 2 or r.get('carpetaId') != repo['carpetaId']:
            raise RuntimeError('El puente no confirma la versión o carpeta solicitada')
        return {'carpeta': r.get('carpeta'), 'nombre': r.get('nombreCarpeta'), 'remitente': r.get('remitente')}
    except Exception:
        raise HTTPException(502, 'El puente no confirmó acceso al repositorio. Revisa cuenta, permisos y despliegue.') from None


@router.get('/catalogo/ejecuciones')
def ejecuciones(db: Session = Depends(get_db), _: Operador = Depends(admin)):
    return [{'turno': c.clave, **c.datos} for c in db.scalars(select(svc.AppConfig)
        .where(svc.AppConfig.clave.like('catalogo:%')).order_by(svc.AppConfig.clave.desc()).limit(15))]


@router.get('/recepciones/{codigo}/evidencias.xlsx')
def exportar_evidencias(codigo: str, db: Session = Depends(get_db), _: Operador = Depends(requiere_supervisor)):
    import re
    from fastapi.responses import Response
    from app.services.reporte_evidencias import generar
    try: contenido=generar(db,codigo)
    except m.ErrorApp as exc: raise HTTPException(404,str(exc)) from None
    nombre=re.sub(r'[^A-Za-z0-9_-]','_',codigo)
    return Response(contenido,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':f'attachment; filename="Evidencias_{nombre}.xlsx"','Cache-Control':'private, no-store'})


@router.get('/formatos-packing/{cliente:path}')
def formato_packing(cliente: str, db: Session = Depends(get_db), _: Operador = Depends(requiere_supervisor)):
    from app.models import AppConfig
    c=db.get(AppConfig,'formatos_packing')
    return (c.datos if c else {}).get(cliente.strip().upper(),{})


@router.put('/formatos-packing/{cliente:path}')
def guardar_formato_packing(cliente: str, datos: dict=Body(...), db: Session=Depends(get_db), op: Operador=Depends(ajustes.requiere('gestionarClientes'))):
    from app.models import AppConfig, utcnow
    if len(cliente)>60 or not cliente.strip():raise HTTPException(422,'Cliente inválido')
    columnas=datos.get('columnas')
    permitidas={'sku','cantidad','descripcion','embarque','factura','referencia','precioUnit','precioTotal'}
    if not isinstance(columnas,dict) or not {'sku','cantidad'}.issubset(set(columnas.values())):
        raise HTTPException(422,'Selecciona SKU y cantidad')
    if any(not str(k).isdigit() or not 0<=int(k)<=1000 or v not in permitidas for k,v in columnas.items()):
        raise HTTPException(422,'Columnas inválidas')
    if type(datos.get('encabezado')) is not int or not 1<=datos['encabezado']<=1000:
        raise HTTPException(422,'Fila de encabezado inválida')
    cabeceras=datos.get('encabezados')
    if not isinstance(cabeceras,list) or not cabeceras or len(cabeceras)>1000:
        raise HTTPException(422,'Confirma las cabeceras de la vista previa')
    c=db.get(AppConfig,'formatos_packing') or AppConfig(clave='formatos_packing',datos={})
    c.datos={**c.datos,cliente.strip().upper():{'hoja':str(datos.get('hoja') or '')[:120],
        'encabezado':datos['encabezado'],'columnas':columnas,'encabezados':[str(v)[:200] for v in cabeceras]}}
    c.usuario,c.modificado_en=op.email or op.usuario,utcnow();db.add(c);db.commit()
    return {'guardado':True}


@router.post('/recepciones/{codigo}/drive/desde-mi-cuenta')
def recuperar_fotos_propias(codigo:str,db:Session=Depends(get_db),op:Operador=Depends(requiere_supervisor)):
    from app.services.drive import reintentar_desde_cuenta
    return reintentar_desde_cuenta(db,codigo,op.email or op.usuario)


@router.put('/evidencias/{archivo_id}')
def editar_evidencia(archivo_id:str,datos:dict=Body(...),db:Session=Depends(get_db),op:Operador=Depends(requiere_supervisor)):
    return svc.editar_evidencia(db,archivo_id,datos,op.email or op.usuario)
