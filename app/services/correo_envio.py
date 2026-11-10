"""Envía el grupo revisado usando la cola y los acuses existentes, sin alterar conteos."""
import hashlib
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppArchivo,AppEntrega,AppInforme
from app.services import app_modelo as m,correo_redactado as correo,entregas,informes,ajustes,archivos
from app.services.instantaneas import compactar


def enviar(db,codigo,datos,usuario):
    r=m.obtener(db,codigo,bloquear=True);origen=str(datos.get('origen') or '')
    if datos.get('confirmar') is not True:raise HTTPException(422,'Revisa el correo y confirma su envío al ejecutivo de cuenta.')
    v=correo.vista(db,r.codigo,usuario,origen=origen,actual=True)
    if not origen and v['correosSeparados']:raise HTTPException(422,'Abre el correo del embarque o packing list que deseas enviar.')
    if datos.get('version')!=v['version']:raise HTTPException(409,'El correo o los datos cambiaron. Actualiza y revisa antes de enviar.')
    destinatarios=entregas.validar_destinatarios(v['campos']['destinatarios'])
    if not destinatarios:raise HTTPException(422,'Indica el correo del ejecutivo de cuenta asignado.')
    if v.get('respuestaOtraCuenta'):raise HTTPException(409,'Selecciona el hilo desde tu propia cuenta de Gmail.')
    f=db.get(AppInforme,str(datos.get('informeId') or ''))
    if v.get('adjuntosPersonalizados'):
        from app.services.adjuntos_correo import validar,disponibles
        validar(db,r.codigo,origen,[{'id':a['id'],'nombre':a['nombre']} for a in v['archivos']])
        opciones={a['id']:a for a in disponibles(db,r.codigo,origen)}
        f=db.get(AppInforme,opciones[v['archivos'][0]['id']]['informeId'])
    if not f or f.recepcion!=r.codigo or f.datos.get('formato') not in (('envio','envio-ampliado','auditable') if v.get('adjuntosPersonalizados') else ('envio','envio-ampliado')) or not f.datos.get('archivos'):raise HTTPException(409,'Prepara los documentos finales dentro de este correo antes de enviarlo.')
    if f.datos.get('huellaContenido')!=informes.huella_contenido(db,r):raise HTTPException(409,'Los conteos, posiciones o evidencias cambiaron. Prepara los documentos actualizados antes de enviar.')
    docs=[a['id'] for a in v['archivos']] if v.get('adjuntosPersonalizados') else [a['id'] for a in f.datos['archivos'] if not origen or a.get('grupo',a.get('origen'))==origen]
    if not docs or set(docs)!={a['id'] for a in v['archivos']}:raise HTTPException(409,'Los documentos no corresponden al grupo y revisión mostrados. Actualiza el correo.')
    if any(not (a:=db.get(AppArchivo,i)) or a.recepcion!=r.codigo or not (a.drive_id or archivos.ruta(a).is_file()) for i in docs):raise HTTPException(409,'Falta un documento final. Vuelve a preparar los documentos.')
    firma=hashlib.sha256(('correo62|'+r.codigo+'|'+origen+'|'+v['version']+'|'+f.id+'|'+usuario).encode()).hexdigest()
    previa=db.scalar(select(AppEntrega).where(AppEntrega.recepcion==r.codigo,AppEntrega.clave==firma).with_for_update().execution_options(populate_existing=True))
    if previa:return entregas.documento(previa)
    if entregas.activas(db,r.codigo):raise HTTPException(409,'Hay una entrega pendiente o en revisión. Consúltala en Entregas antes de programar otro correo.')
    from app.services.remitentes import elegir
    remitente,modo=elegir(db,r.codigo,{'modoRemitente':'PERSONAL','remitenteConfirmado':datos.get('remitenteConfirmado'),'destinatarios':destinatarios},usuario)
    from app.services.drive import resumen_fotos,manifiesto
    if resumen_fotos(db,r.codigo)['pendientes']:raise HTTPException(409,'Hay imágenes sin confirmar u organizar en Drive. Revisa Fotos y actualiza sus carpetas antes de enviar.')
    _,_,fuente,_=correo._fuente(db,r.codigo,origen=origen)
    if v['fotosSeleccionadas'] and not fuente.get('enlacesCarpetas'):raise HTTPException(409,'Comprueba las carpetas y enlaces de esta recepción antes de enviar sus fotografías.')
    if not fuente['skus'] or any(not s.get('verificado') for s in fuente['skus']):raise HTTPException(409,'Valida todas las referencias del grupo antes de enviar su informe final.')
    from app.services.correos_embarque import validar_cierre
    validar_cierre(db,r)  # Un informe descargable no acredita la asignación de conteos antiguos a sus listas.
    if len(v['html'])>500000:raise HTTPException(422,'Reduce el contenido del correo; supera el tamaño permitido.')
    final={k:v[k] for k in ('asunto','html','texto','remitente','campos','imagenesDrive','presentacion','fotosSeleccionadas','validacionDepot','respuestaGmail')}
    from app.services.agrupacion_correo import configuracion
    from app.services.operacion import destino_drive
    plan=configuracion(db,r.codigo);destino=destino_drive(db,r.codigo);destino.pop('supervisor',None)
    fotos=[p['archivoId'] for p in manifiesto(db,r.codigo)]
    e=AppEntrega(id=uuid4().hex,recepcion=r.codigo,usuario=usuario,clave=firma,estado='PENDIENTE',datos=compactar({
        'correoRevisado62':True,'reporteSinCierre':True,'destinatarios':destinatarios,'remitente':remitente,'modoRemitente':modo,
        'informes':docs,'nombresAdjuntos':{a['id']:a['nombre'] for a in v['archivos']},'fotos':list(dict.fromkeys(fotos)),'destino':destino,'carpetaMes':'','carpetaRecepcion':r.codigo,
        'skus':m.leer_coleccion(db,r.codigo,'skus',actual=True),'eventos':m.leer_coleccion(db,r.codigo,'eventos',actual=True),
        'lineas':m.leer_coleccion(db,r.codigo,'lineas',actual=True),'recepcion':m.doc_recepcion(r),
        'planCorreos':plan,'informeId':f.id,'informe':{'id':f.id,'numero':f.numero,'usuario':f.usuario,'creadoEn':m._iso(f.creado_en)},
        'correosPorOrigen':[{'origen':origen or (r.origenes or ['PRINCIPAL'])[0],'nombre':v['nombreGrupo'] or r.codigo,
            'destinatarios':destinatarios,'correoFinal':final,'informes':docs,'fotos':[p['id'] for p in v['fotos']],'estado':'PENDIENTE'}]}))
    db.add(e);ajustes.auditar(db,usuario,'CORREO_REVISADO_PROGRAMADO',r.codigo,{'entregaId':e.id,'origen':origen,'informeId':f.id,'destinatarios':destinatarios})
    db.commit();return entregas.documento(e)
