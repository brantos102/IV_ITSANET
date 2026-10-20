"""Un cierre, documentos separados y un mensaje auditable por packing list."""
import hashlib
import json
from fastapi import HTTPException
from app.models import AppConfig, utcnow
from app.services import app_modelo as m, ajustes


def clave(codigo):return 'correo:p:'+hashlib.sha256(m.limpiar(codigo).upper().encode()).hexdigest()[:30]
def asignaciones(db,codigo):
    f=db.get(AppConfig,clave(codigo));return dict((f.datos if f else {}).get('asignaciones',{}))


def plan(db,codigo):
    r=m.obtener(db,codigo);skus=m.leer_coleccion(db,codigo,'skus',actual=True)
    eventos=m.leer_coleccion(db,codigo,'eventos',actual=True)
    asignadas=asignaciones(db,codigo)
    version=hashlib.sha256(json.dumps([r.formatos,eventos,asignadas],sort_keys=True,default=str).encode()).hexdigest()
    return {'origenes':r.origenes or [],'version':version,'asignaciones':asignadas,
        'adicionales':[{'sku':s['sku'],'descripcion':s.get('descripcion','')} for s in skus if s.get('enPackingList') is False]}


def guardar_plan(db,codigo,datos,usuario):
    r=m.obtener(db,codigo,bloquear=True)
    if r.estado=='CERRADA':raise HTTPException(409,'La recepción ya está cerrada; se conserva su plan de correos.')
    p=plan(db,codigo)
    if datos.get('version')!=p['version']:raise HTTPException(409,'Cambió la recepción o su asignación de adicionales. Revisa el cierre de nuevo.')
    mapa=datos.get('asignaciones',{})
    if not isinstance(mapa,dict) or set(mapa)!={s['sku'] for s in p['adicionales']} or any(v not in p['origenes'] for v in mapa.values()):
        raise HTTPException(422,'Asigna cada producto adicional a un packing list de esta recepción.')
    f=db.get(AppConfig,clave(codigo)) or AppConfig(clave=clave(codigo));f.datos={'asignaciones':mapa};f.usuario=usuario;db.add(f)
    ajustes.auditar(db,usuario,'CORREOS_POR_EMBARQUE',codigo,{'origenes':p['origenes'],'asignaciones':mapa});db.commit()
    return plan(db,codigo)


def pertenencias(lineas,mapa):
    grupos={}
    for l in lineas:grupos.setdefault(l['sku'],set()).add(l.get('origen') or 'PRINCIPAL')
    for sku,origen in mapa.items():grupos.setdefault(sku,set()).add(origen)
    return grupos


def filtrar(fuente,lineas,origen,mapa):
    grupos=pertenencias(lineas,mapa)
    anulados={e.get('anulaA') for e in fuente['eventos'] if e.get('tipo')=='ANULACION'}
    activos=[e for e in fuente['eventos'] if e.get('id') not in anulados and e.get('tipo')!='ANULACION']
    def corresponde(e):return (e.get('origen')==origen or not e.get('origen') and grupos.get(e.get('sku'))=={origen})
    eventos=[e for e in activos if corresponde(e)]
    ids={e['id'] for e in eventos}
    eventos += [e for e in sorted(activos,key=lambda e:(e.get('creadoEn') or '',e['id'])) if e.get('tipo')=='CALIDAD' and e.get('eventoId') in ids and e not in eventos]
    correcciones={e['eventoId']:e['incidencias'] for e in sorted(activos,key=lambda e:(e.get('creadoEn') or '',e['id'])) if e.get('tipo')=='CALIDAD' and e.get('eventoId')}
    skus=[]
    for s in fuente['skus']:
        ls=[l for l in lineas if l['sku']==s['sku'] and (l.get('origen') or 'PRINCIPAL')==origen]
        if not ls and mapa.get(s['sku'])!=origen:continue
        es=[e for e in eventos if e.get('sku')==s['sku'] and e.get('tipo') in ('CONTEO','CERO','NO_ENCONTRADO')]
        pallets={};incidencias={};contado=0
        for e in es:
            n=float(e.get('cantidad') or 0);contado+=n
            if n>0:pallets[e.get('pallet') or '']=pallets.get(e.get('pallet') or '',0)+n
            fs=correcciones.get(e['id'],e.get('incidencias'))
            if fs is None:fs=[{'tipo':'MAL_ESTADO','nombre':'PNC','cantidad':n,'pnc':True}] if e.get('estadoFisico')=='PNC' and n>0 else []
            for f in fs:
                g=incidencias.setdefault(f['tipo'],{'tipo':f['tipo'],'nombre':f.get('nombre',f['tipo']),'cantidad':0,'pnc':0})
                g['cantidad']+=f['cantidad'];g['pnc']+=f['cantidad'] if f.get('pnc') else 0
                if f.get('pallet'):g.setdefault('pallets',{})[f['pallet']]=g.get('pallets',{}).get(f['pallet'],0)+f['cantidad']
        pnc=sum(i['pnc'] for i in incidencias.values())
        skus.append({**s,'esperado':sum(float(l['cantidad']) for l in ls),'contado':contado,'pallets':pallets,
            'cantidadPnc':pnc,'cantidadConforme':max(0,contado-pnc),'tienePnc':pnc>0,'incidencias':list(incidencias.values())})
    fotos=[]
    for foto in fuente.get('fotos',[]):
        vinculos=[v for v in foto.get('rutasVinculadas') or [foto] if
            v.get('origen')==origen or not v.get('origen') and (not v.get('sku') or grupos.get(v['sku'])=={origen})]
        if vinculos:fotos.append({**foto,'sku':vinculos[0].get('sku',''),'categoria':vinculos[0].get('categoria','RECEPCION'),'rutasVinculadas':vinculos})
    depot=fuente.get('validacionDepot')
    if depot:depot={**depot,'porSku':{s['sku']:depot['porSku'][s['sku']] for s in skus if s['sku'] in depot['porSku']}}
    return {**fuente,'origen':origen,'skus':skus,'eventos':eventos,'fotos':fotos,'validacionDepot':depot}


def validar_cierre(db,r):
    mapa=asignaciones(db,r.codigo);lineas=m.leer_coleccion(db,r.codigo,'lineas',actual=True)
    grupos=pertenencias(lineas,mapa)
    skus=m.leer_coleccion(db,r.codigo,'skus',actual=True)
    if any(s.get('tienePnc') and s.get('cantidadPnc') is None for s in skus):
        raise HTTPException(409,'Revisa las unidades PNC de los registros anteriores antes de separar los correos por embarque.')
    from app.services.agrupacion_correo import configuracion,grupos as grupos_envio
    config=configuracion(db,r.codigo)
    from app.services.agrupacion_correo import embarque
    if len({embarque(l,config) for l in lineas if embarque(l,config)})>1 and config.get('modo')!='EMBARQUE' and not config.get('consolidadoConfirmado'):
        raise HTTPException(409,'La recepción contiene varios embarques. Organiza sus correos por embarque antes de finalizar.')
    grupos_actuales=grupos_envio(lineas,r.origenes or [],config)
    destinos=[g['id'] for g in grupos_actuales]
    if any(s.get('enPackingList') is False and mapa.get(s['sku']) not in destinos for s in skus):
        raise HTTPException(409,'Asigna los productos adicionales a su embarque al comenzar la finalización.')
    eventos=m.leer_coleccion(db,r.codigo,'eventos',actual=True)
    anulados={e.get('anulaA') for e in eventos if e.get('tipo')=='ANULACION'}
    for e in eventos:
        if config.get('modo')=='RECEPCION':continue
        if config.get('modo')=='EMBARQUE' and e.get('id') not in anulados and e.get('tipo')=='CONTEO' and e.get('cantidad',0)>0 and e.get('sku') in mapa and e.get('origen'):
            destino=next((g for g in grupos_actuales if g['id']==mapa[e['sku']]),None)
            if destino and e['origen'] not in destino['packingLists']:raise HTTPException(409,'El packing list del adicional '+e['sku']+' no pertenece al embarque elegido. Corrige su asignación antes de finalizar.')
        if config.get('modo')!='EMBARQUE' and e.get('id') not in anulados and e.get('tipo')=='CONTEO' and e.get('cantidad',0)>0 and e.get('sku') in mapa and e.get('origen') and e['origen']!=mapa[e['sku']]:
            raise HTTPException(409,'La asignación del adicional '+e['sku']+' no coincide con el origen de su conteo. Corrige la asignación antes de finalizar.')
        if e.get('id') not in anulados and e.get('tipo')=='CONTEO' and e.get('cantidad',0)>0 and not e.get('origen') and len(grupos.get(e.get('sku'),set()))>1:
            raise HTTPException(409,'Asigna el packing list de los conteos compartidos antes de finalizar. SKU: '+e['sku'])
    return mapa,lineas


def congelar(db,r,datos,usuario,informe,entrega_id=''):
    from app.services import correo_redactado as correo, entregas
    if not entrega_id:validar_cierre(db,r)
    from app.services.agrupacion_correo import configuracion,grupos
    if entrega_id:
        from app.models import AppEntrega
        from app.services.instantaneas import expandir
        previo=expandir(db.get(AppEntrega,entrega_id).datos)
        config=previo.get('planCorreos',{'modo':'PACKING_LIST','asignaciones':previo.get('asignacionesAdicionales',{})});lineas=previo['lineas']
    else:config=configuracion(db,r.codigo);lineas=m.leer_coleccion(db,r.codigo,'lineas',actual=True)
    destinos=grupos(lineas,r.origenes or [],config);ids={g['id'] for g in destinos}
    revisados=datos.get('correos')
    if not isinstance(revisados,list) or any(not isinstance(d,dict) or not isinstance(d.get('origen'),str) for d in revisados) or len(revisados)!=len(ids) or {d['origen'] for d in revisados}!=ids:
        raise HTTPException(409,'Revisa un correo separado por cada packing list antes de cerrar la recepción.')
    if not informe or informe.datos.get('formato') not in ('envio','envio-ampliado'):
        raise HTTPException(422,'Para enviar por embarque, genera un documento independiente por packing list.')
    if datos.get('modoEntrega') not in ('MANUAL','MANUAL_ENVIADO'):
        from app.services.drive import resumen_fotos
        if resumen_fotos(db,r.codigo)['pendientes']:
            raise HTTPException(409,'Confirma las fotos en Drive antes de enviar los correos por embarque, o elige envío manual.')
    anteriores={}
    if entrega_id:
        from app.models import AppEntrega
        anteriores={c['origen']:c for c in db.get(AppEntrega,entrega_id).datos.get('correosPorOrigen',[])}
    salida=[]
    for grupo in destinos:
        origen=grupo['id']
        d=next(d for d in revisados if d['origen']==origen)
        if anteriores.get(origen,{}).get('estado')=='ENTREGADA':
            salida.append(anteriores[origen]);continue
        v=correo.vista(db,r.codigo,usuario,entrega_id,origen,actual=True)
        if v.get('respuestaOtraCuenta'):raise HTTPException(409,'Selecciona el hilo Gmail de '+grupo['nombre']+' desde tu propia cuenta antes de enviar.')
        if d.get('correoVersion')!=v['version'] or entregas.validar_destinatarios(d.get('destinatarios'))!=v['campos']['destinatarios']:
            raise HTTPException(409,'Cambió el correo de '+origen+'. Revisa nuevamente todos los correos antes de finalizar.')
        if not v['campos']['destinatarios']:raise HTTPException(422,'Completa los destinatarios de '+origen)
        docs=[a['id'] for a in informe.datos.get('archivos',[]) if a.get('grupo',a.get('origen'))==origen]
        if len(docs)!=(len(grupo['packingLists']) if config.get('modo')=='EMBARQUE' else 1):raise HTTPException(409,'Faltan documentos finales independientes de '+grupo['nombre'])
        if len(v['html'])>500000:raise HTTPException(422,'El correo de '+origen+' supera el tamaño permitido.')
        final={k:v[k] for k in ('asunto','html','texto','remitente','campos','imagenesDrive','presentacion','fotosSeleccionadas','validacionDepot','respuestaGmail')}
        salida.append({'origen':origen,'nombre':grupo['nombre'],'destinatarios':v['campos']['destinatarios'],'correoFinal':final,'informes':docs,
            'fotos':[f['id'] for f in v['fotos']],'estado':'PENDIENTE'})
    return salida


def enviar_lote(db,e,d,guardados,manifest,llamar):
    from datetime import timedelta
    from app.models import AppArchivo
    from app.services.entregas import RevisionEntrega,resumen_final
    items=[dict(c) for c in e.datos['correosPorOrigen']]
    por_archivo={ident:db.get(AppArchivo,ident) for ident in d['informes']+d['fotos']}
    for item in items:
        if item.get('estado')=='ENTREGADA':continue
        from app.services.agrupacion_correo import filtrar as filtrar_grupo
        scoped=filtrar_grupo({'skus':d['skus'],'eventos':d['eventos'],'fotos':manifest},d['lineas'],item['origen'],d.get('planCorreos',{'modo':'PACKING_LIST','asignaciones':d.get('asignacionesAdicionales',{})}))
        ids=set(item['informes']+item['fotos'])
        if any(not por_archivo.get(i) or not por_archivo[i].drive_id for i in ids):
            raise RuntimeError('Falta confirmar un documento o fotografía del embarque '+item['origen'])
        drive_ids={por_archivo[i].drive_id for i in ids if por_archivo.get(i)}
        fotos=[f for f in scoped['fotos'] if f['archivoId'] in set(item['fotos'])]
        payload={**d.get('destino',{}),'recepcion':e.recepcion,'codigo':e.recepcion,'origen':item['origen'],
            'usuario':d.get('remitente') or e.usuario,'solicitadoPor':e.usuario,'destinatarios':item['destinatarios'],
            'correoFinal':item['correoFinal'],'archivos':[a for a in guardados if a['fileId'] in drive_ids],
            'manifiesto':fotos,'resumen':resumen_final(scoped['skus'],scoped['eventos']),
            'carpetaMes':d['carpetaMes'],'carpetaRecepcion':d['carpetaRecepcion'],'duracion':d.get('duracion',''),
            'informe':d.get('informe'),'exportarSheet':d.get('exportarSheet',False)}
        if payload['exportarSheet']:
            from app.services.agrupacion_correo import embarque,grupo_id
            por_embarque=d.get('planCorreos',{}).get('modo')=='EMBARQUE'
            payload.update(skus=scoped['skus'],eventos=[{**ev,'tipo':'ASIGNACION_INFORME'} for ev in scoped['eventos']] if por_embarque else scoped['eventos'],
                lineas=[l for l in d['lineas'] if (grupo_id(embarque(l,d['planCorreos']))==item['origen'] if por_embarque else d.get('planCorreos',{}).get('modo')=='RECEPCION' or (l.get('origen') or 'PRINCIPAL')==item['origen'])])
        e.proximo_en=utcnow()+timedelta(minutes=15);db.commit()
        llave=hashlib.sha256((e.id+'\x1f'+item['origen']).encode()).hexdigest()[:32]
        resultado=llamar('finalizar',llave,payload)
        normalizar=lambda v:{c.strip().lower() for c in str(v or '').split(',') if c.strip()}
        if normalizar(resultado.get('enviadoA'))!=normalizar(item['destinatarios']) or str(resultado.get('remitente') or '').lower()!=payload['usuario'].lower():
            raise RevisionEntrega('No se confirmó el correo de '+item['origen']+'. Revisa Enviados antes de reintentar; los embarques confirmados se conservan.')
        respuesta=item['correoFinal'].get('respuestaGmail')
        if respuesta and (not (resultado.get('gmail') or {}).get('mensajeId') or (resultado.get('gmail') or {}).get('threadId')!=respuesta['threadId']):
            raise RevisionEntrega('Gmail no confirmó la respuesta en el hilo de '+item['nombre']+'. Revisa Enviados antes de repetir.')
        item.update(estado='ENTREGADA',confirmadoEn=resultado.get('confirmadoEn') or m._iso(utcnow()),resultado={k:resultado.get(k) for k in ('enviadoA','remitente','carpeta','sheet','gmail')})
        # Copiar las filas evita mutar el JSON ya persistido antes de que
        # SQLAlchemy compare el cambio del siguiente acuse.
        e.datos={**e.datos,'correosPorOrigen':[dict(c) for c in items]};db.commit()
    return {'exito':True,'enviadoA':d['destinatarios'],'remitente':d.get('remitente') or e.usuario,
        'confirmadoEn':m._iso(utcnow()),'correos':[{'origen':c['origen'],'estado':c['estado'],'confirmadoEn':c.get('confirmadoEn')} for c in items],
        'carpeta':next((c.get('resultado',{}).get('carpeta') for c in items if c.get('resultado',{}).get('carpeta')),'')}
