"""Avisos derivados del estado confirmado en SQL; nunca cambian conteos ni envían correo."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, or_, and_, exists
from app.models import (AppConfig, AppRecepcion, AppSku, AppEvidencia, AppCopiaDrive, AppArchivo,
    Producto, Rol, utcnow)
from app.services import app_modelo as m

ZONA=ZoneInfo('America/Guayaquil')


def _utc(fecha):
    return fecha.replace(tzinfo=timezone.utc) if fecha and fecha.tzinfo is None else fecha


def registrar_catalogo(db, clientes, origen, cantidades, ahora=None):
    """Constancia de carga masiva: un lookup individual no renueva todo el catálogo."""
    ahora=_utc(ahora or utcnow())
    for nombre in set(str(c or '').strip().upper() for c in clientes)-{''}:
        clave='cat65:'+sha256(nombre.encode()).hexdigest()[:32]
        f=db.get(AppConfig,clave) or AppConfig(clave=clave)
        f.datos={'cliente':nombre,'origen':origen,'actualizadoEn':ahora.isoformat(),
            'productos':int(cantidades.get(nombre,0))}
        db.add(f)
    if cantidades:
        from app.services.ajustes import auditar
        auditar(db,'CATALOGO','CATALOGO_CARGADO','catalogo',{'clientes':sorted(cantidades),
            'productos':sum(cantidades.values()),'origen':origen})


def catalogo(db, ahora=None):
    ahora=_utc(ahora or utcnow());dia=ahora.astimezone(ZONA).date().isoformat()
    clientes=set(db.scalars(select(AppRecepcion.cliente).where(AppRecepcion.estado!='CERRADA').distinct()))
    conexiones=list(db.scalars(select(AppConfig).where(AppConfig.clave.like('depot:%'))))
    alias=[];sin_recepciones=not clientes
    for f in conexiones:
        if not f.datos.get('activo',True):continue
        nombres={f.clave[6:].upper(),str(f.datos.get('cliente') or '').strip().upper()}-{''}
        alias.append(nombres)
        if sin_recepciones:clientes.add(str(f.datos.get('cliente') or f.clave[6:]).strip().upper())
    if not clientes:clientes=set(db.scalars(select(Producto.cliente).distinct()))
    cargas={f.datos.get('cliente'):f.datos for f in db.scalars(select(AppConfig).where(AppConfig.clave.like('cat65:%')))}
    compartido=db.get(AppConfig,'catalogo:actualizacion-compartida');compartido=compartido.datos if compartido else {}
    def fecha(valor):
        try:return _utc(datetime.fromisoformat(valor.replace('Z','+00:00'))) if valor else None
        except (TypeError,ValueError):return None
    resultados=[]
    for cliente in sorted(c for c in clientes if c):
        nombres={cliente.upper()}
        for grupo in alias:
            if nombres.intersection(grupo):nombres.update(grupo)
        candidatos=[cargas[n] for n in nombres if n in cargas]
        completo=max(candidatos,key=lambda c:c.get('actualizadoEn',''),default={})
        ultima=fecha(completo.get('actualizadoEn'))
        # Compatibilidad con una actualización completa de v64, sin confundirla con un lookup.
        alcance=compartido.get('alcanceVigente')
        legado=fecha(compartido.get('actualizadoEn')) if alcance=='TODOS' or alcance in nombres else None
        if not cargas and legado and (not ultima or legado>ultima) and not compartido.get('resultado',{}).get('errores'):
            ultima=legado;completo={'productos':compartido.get('resultado',{}).get('productos',0)}
        vigente=bool(ultima and ultima.astimezone(ZONA).date().isoformat()==dia and completo.get('productos',0)>0)
        resultados.append({'cliente':cliente,'vigente':vigente,'actualizadoEn':m._iso(ultima) if ultima else None,
            'productos':completo.get('productos'),'motivo':'' if vigente else 'No hay una carga completa confirmada para la jornada actual.'})
    pendientes=[x['cliente'] for x in resultados if not x['vigente']]
    return {'dia':dia,'zona':'America/Guayaquil','requiereActualizacion':bool(pendientes) or not resultados,
        'clientesPendientes':pendientes,'clientes':resultados,
        'actualizando':bool(compartido.get('hasta') and compartido['hasta']>ahora.isoformat())}


def _revision(datos):
    return sha256(json.dumps(datos,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def consultar(db, op, recepcion='', limite=80, incluir_catalogo=True, tipo=''):
    from fastapi import HTTPException
    if tipo not in ('','PNC','FALTANTE','SOBRANTE','ADICIONAL','SIN_FOTO'):raise HTTPException(422,'Filtro de avisos inválido.')
    filtro=tipo
    supervisor=op.rol in (Rol.SUPERVISOR,Rol.ADMIN)
    if recepcion:recepcion=m.obtener(db,recepcion).codigo
    if not supervisor and not recepcion:
        return {'avisos':[],'catalogo':None,'consultadoEn':m._iso(utcnow()),'hayMas':False}
    ahora=utcnow()
    q=select(AppSku,AppRecepcion).join(AppRecepcion,AppRecepcion.codigo==AppSku.recepcion).where(
        or_(AppSku.tiene_pnc.is_(True),AppSku.contado>AppSku.esperado,
            and_(AppSku.verificado.is_(True),AppSku.contado<AppSku.esperado)))
    filtros={'PNC':AppSku.tiene_pnc.is_(True),'FALTANTE':and_(AppSku.verificado.is_(True),AppSku.contado<AppSku.esperado),
        'SOBRANTE':and_(AppSku.en_packing_list.is_(True),AppSku.contado>AppSku.esperado),
        'ADICIONAL':and_(AppSku.en_packing_list.is_(False),AppSku.contado>AppSku.esperado)}
    def tiene_foto(categorias):
        return exists(select(AppEvidencia.id).where(AppEvidencia.recepcion==AppSku.recepcion,
            AppEvidencia.sku==AppSku.sku,AppEvidencia.eliminado_en.is_(None),AppEvidencia.categoria.in_(categorias)))
    if tipo=='SIN_FOTO':q=q.where(or_(*(and_(condicion,~tiene_foto(('VALIDACION','SOBRANTE','PNC') if t=='ADICIONAL' else (t,))) for t,condicion in filtros.items())))
    elif tipo:q=q.where(filtros[tipo])
    if recepcion:q=q.where(AppSku.recepcion==recepcion)
    else:q=q.where(or_(AppRecepcion.estado!='CERRADA',AppRecepcion.cerrada_en>=ahora-timedelta(days=7)))
    filas=list(db.execute(q.order_by(AppSku.actualizado_en.desc(),AppSku.id.desc()).limit(limite+1)))
    hay_mas=len(filas)>limite;filas=filas[:limite]
    codigos={r.codigo for _,r in filas};skus={s.sku for s,_ in filas};fotos={}
    if codigos and skus:
        query=select(AppEvidencia,AppCopiaDrive.estado,AppArchivo.drive_id,AppArchivo.drive_url).join(
            AppArchivo,AppArchivo.id==AppEvidencia.archivo_id).outerjoin(AppCopiaDrive,
            AppCopiaDrive.archivo_id==AppEvidencia.archivo_id).where(
            AppEvidencia.recepcion.in_(codigos),AppEvidencia.sku.in_(skus),AppEvidencia.eliminado_en.is_(None))
        for e,estado,drive_id,drive_url in db.execute(query):
            nodo=fotos.setdefault((e.recepcion,e.sku,e.categoria),{})
            nodo[e.archivo_id]=bool(estado=='COPIADA' and drive_id and str(drive_url or '').startswith('https://drive.google.com/'))
    lectura=db.get(AppConfig,'avisos65:'+str(op.id));leidos=(lectura.datos or {}).get('leidos',{}) if lectura else {}
    avisos=[]
    for s,r in filas:
        esperado=float(s.esperado);contado=float(s.contado);tipos=[]
        if contado>esperado:tipos.append(('SOBRANTE' if s.en_packing_list else 'ADICIONAL',contado-esperado))
        elif s.verificado and contado<esperado:tipos.append(('FALTANTE',esperado-contado))
        if s.tiene_pnc:tipos.append(('PNC',(s.calidad.datos or {}).get('cantidadPnc') if s.calidad else None))
        for tipo,cantidad in tipos:
            fotos_tipo=fotos.get((r.codigo,s.sku,tipo),{})
            if tipo=='ADICIONAL':
                fotos_tipo={ident:confirmada for categoria in ('VALIDACION','SOBRANTE','PNC')
                    for ident,confirmada in fotos.get((r.codigo,s.sku,categoria),{}).items()}
            # Una foto genérica o de otra incidencia no acredita este tipo de novedad.
            evidencia={'registradas':len(fotos_tipo),'confirmadasDrive':sum(fotos_tipo.values()),
                'pendientesDrive':len(fotos_tipo)-sum(fotos_tipo.values()),'sinEvidencia':not fotos_tipo}
            if filtro and filtro!='SIN_FOTO' and filtro!=tipo:continue
            if filtro=='SIN_FOTO' and fotos_tipo:continue
            provisional=tipo in ('FALTANTE','SOBRANTE') and r.estado!='CERRADA'
            datos={'recepcion':r.codigo,'cliente':r.cliente,'sku':s.sku,'tipo':tipo,'cantidad':cantidad,
                'esperado':esperado,'contado':contado,'provisional':provisional,'estadoRecepcion':r.estado,
                'evidencias':evidencia}
            revision=_revision(datos);ident='n65:'+sha256((r.codigo+'|'+s.sku+'|'+tipo).encode()).hexdigest()[:32]
            avisos.append({'id':ident,'revision':revision,**datos,'leido':leidos.get(ident)==revision,
                'descripcion':s.descripcion or '', 'actualizadoEn':m._iso(s.actualizado_en),
                'mensaje':'SKU fuera del packing list de esta recepción: revisar su identificación.' if tipo=='ADICIONAL' else
                    'Diferencia provisional: revisar el conteo antes de confirmar el resultado.' if provisional else
                    'Producto no conforme: revisar las unidades afectadas y sus evidencias.' if tipo=='PNC' else 'Diferencia en recepción cerrada.'})
    return {'avisos':avisos,'catalogo':catalogo(db,ahora) if supervisor and incluir_catalogo else None,
        'consultadoEn':m._iso(ahora),'hayMas':hay_mas}


def marcar_leidos(db,op,datos):
    from fastapi import HTTPException
    import re
    filas=datos.get('avisos')
    if not isinstance(filas,list) or len(filas)>240 or any(not isinstance(f,dict) or
        not re.fullmatch(r'n65:[a-f0-9]{32}',str(f.get('id',''))) or
        not re.fullmatch(r'[a-f0-9]{64}',str(f.get('revision',''))) for f in filas):
        raise HTTPException(422,'Selección de avisos inválida.')
    clave='avisos65:'+str(op.id)
    if db.get_bind().dialect.name=='mysql':
        from sqlalchemy.dialects.mysql import insert
        q=insert(AppConfig).values(clave=clave,datos={});q=q.on_duplicate_key_update(clave=q.inserted.clave)
    else:
        from sqlalchemy.dialects.sqlite import insert
        q=insert(AppConfig).values(clave=clave,datos={}).on_conflict_do_nothing(index_elements=['clave'])
    db.execute(q)
    f=db.scalar(select(AppConfig).where(AppConfig.clave==clave).with_for_update().execution_options(populate_existing=True))
    leidos=dict((f.datos or {}).get('leidos',{}))
    for aviso in filas:
        leidos.pop(aviso['id'],None);leidos[aviso['id']]=aviso['revision']
    f.datos={'leidos':dict(list(leidos.items())[-240:])};f.usuario=op.usuario;db.add(f);db.commit()
    return {'ok':True}
