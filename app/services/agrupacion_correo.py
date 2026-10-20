"""Packing list es archivo; embarque es un dato de sus filas. Reparto revisado, sin alterar conteos."""
import hashlib
import json
import math
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppConfig
from app.services import app_modelo as m,ajustes


def firma(valor):return hashlib.sha256(json.dumps(valor,sort_keys=True,default=str).encode()).hexdigest()
def configuracion(db,codigo,*,actual=False):
    from app.services.correos_embarque import clave
    llave=clave(codigo)
    f=db.scalar(select(AppConfig).where(AppConfig.clave==llave).with_for_update().execution_options(populate_existing=True)) if actual else db.get(AppConfig,llave)
    return {'modo':'PACKING_LIST','asignaciones':{},'embarquesPorLinea':{},'repartos':{},**(f.datos if f else {})}
def linea_id(l):return str(l.get('id') or str(l.get('origen') or 'PRINCIPAL')+'-'+str(l['linea']))
def embarque(l,c):return str(l.get('embarque') or c.get('embarquesPorLinea',{}).get(linea_id(l)) or '').strip().upper()
def grupo_id(emb):return 'EMB-'+hashlib.sha256(emb.encode()).hexdigest()[:20]
def reparto_id(origen,sku):return hashlib.sha256((origen+'\x1f'+sku).encode()).hexdigest()[:24]


def grupos(lineas,origenes,c):
    if c.get('modo')=='RECEPCION':
        nombres=', '.join(dict.fromkeys(embarque(l,c) for l in lineas if embarque(l,c)))
        return [{'id':'RECEPCION','nombre':'Recepción completa'+(' · '+nombres if nombres else ''),'tipo':'RECEPCION','packingLists':list(origenes)}]
    if c.get('modo')!='EMBARQUE':
        resultado=[]
        for o in origenes:
            nombres=list(dict.fromkeys(embarque(l,c) for l in lineas if (l.get('origen') or 'PRINCIPAL')==o and embarque(l,c)))
            nombre=o+' - '+', '.join(nombres) if o=='PRINCIPAL' and nombres else o
            resultado.append({'id':o,'nombre':nombre,'tipo':'PACKING_LIST','packingLists':[o]})
        return resultado
    salida={}
    for l in lineas:
        emb=embarque(l,c)
        if not emb:continue
        g=salida.setdefault(emb,{'id':grupo_id(emb),'nombre':emb,'tipo':'EMBARQUE','packingLists':[]})
        o=l.get('origen') or 'PRINCIPAL'
        if o not in g['packingLists']:g['packingLists'].append(o)
    return list(salida.values())


def fuente(db,codigo):
    return {k:m.leer_coleccion(db,codigo,k,actual=True) for k in ('skus','eventos','lineas')}


def distribuir(total,pesos):
    restante=float(total or 0);salida=[]
    for i,p in enumerate(pesos):
        n=restante if i==len(pesos)-1 else min(max(restante,0),float(p or 0));salida.append(n);restante-=n
    return salida


def proyecciones(f,lineas,c):
    from app.services.correos_embarque import filtrar
    filas=[];pendientes=[]
    for o in dict.fromkeys(l.get('origen') or 'PRINCIPAL' for l in lineas):
        ls=[l for l in lineas if (l.get('origen') or 'PRINCIPAL')==o]
        base=filtrar({**f,'fotos':[]},lineas,o,{})
        for s in base['skus']:
            propias=[l for l in ls if l['sku']==s['sku']]
            embs=list(dict.fromkeys(embarque(l,c) for l in propias if embarque(l,c)))
            if not embs:continue
            gs=[grupo_id(e) for e in embs];rid=reparto_id(o,s['sku'])
            notas=' · '.join(dict.fromkeys(e['observacion'] for e in base['eventos'] if e.get('sku')==s['sku'] and e.get('observacion')))
            cantidades=distribuir(s['contado'],[sum(float(l['cantidad']) for l in propias if embarque(l,c)==e) for e in embs])
            inc_por_grupo=[{} for _ in gs];pnc_por_grupo=[{} for _ in gs];disponibles=list(cantidades)
            for inc in s.get('incidencias',[]):
                ns=distribuir(inc['cantidad'],disponibles)
                pn=distribuir(inc.get('pnc',0),ns)
                for i,n in enumerate(ns):inc_por_grupo[i][inc['tipo']]=n;pnc_por_grupo[i][inc['tipo']]=pn[i];disponibles[i]-=n
            propuesta={g:{'cantidad':cantidades[i],'incidencias':inc_por_grupo[i],'pnc':pnc_por_grupo[i], 'observacion':notas if len(gs)==1 else '',
                'pallets':'-'.join(p for p,n in s.get('pallets',{}).items() if n) if len(gs)==1 else ''} for i,g in enumerate(gs)}
            elegidos=c.get('repartos',{}).get(rid,propuesta) if len(gs)>1 else propuesta
            if len(gs)>1:
                pendientes.append({'id':rid,'origen':o,'sku':s['sku'],'cantidad':s['contado'], 'incidencias':s.get('incidencias',[]),
                    'grupos':[{'id':g,'nombre':e} for g,e in zip(gs,embs)],'propuesta':elegidos})
            for g,e in zip(gs,embs):
                x=elegidos.get(g,{})
                incidencias=[]
                for i in s.get('incidencias',[]):
                    n=x.get('incidencias',{}).get(i['tipo'],0);np=x.get('pnc',{}).get(i['tipo'],0)
                    incidencias.extend({**i,'cantidad':q,'pnc':pnc} for q,pnc in ((np,True),(n-np,False)) if q>0)
                filas.append({'grupo':g,'embarque':e,'origen':o,'sku':s['sku'],'esperado':sum(float(l['cantidad']) for l in propias if embarque(l,c)==e),
                    'contado':x.get('cantidad',0),'incidencias':incidencias,'observacion':x.get('observacion',''),'pallets':x.get('pallets','')})
    return filas,pendientes


def vista(db,codigo,datos=None,*,actual=False):
    r=m.obtener(db,codigo);f=fuente(db,r.codigo);guardada=configuracion(db,r.codigo,actual=actual)
    c={**guardada,**{k:v for k,v in (datos or {}).items() if k in ('modo','asignaciones','embarquesPorLinea','repartos')}}
    if c['modo'] not in ('PACKING_LIST','EMBARQUE','RECEPCION'):raise HTTPException(422,'Elige un correo por packing list, embarque o recepción consolidada.')
    if any(not isinstance(c.get(k),dict) for k in ('asignaciones','embarquesPorLinea','repartos')):raise HTTPException(422,'Revisa las asignaciones del plan de correos.')
    for rs in c['repartos'].values():
        if not isinstance(rs,dict) or any(not isinstance(x,dict) or not numero(x.get('cantidad')) or any(not isinstance(x.get(k),dict) or any(not numero(n) for n in x[k].values()) for k in ('incidencias','pnc')) for x in rs.values()):raise HTTPException(422,'Reparto de cantidades o calidad inválido.')
    gs=grupos(f['lineas'],r.origenes or [],c)
    faltan=[{'id':linea_id(l),'origen':l.get('origen') or 'PRINCIPAL','linea':l['linea'],'sku':l['sku']} for l in f['lineas'] if not embarque(l,c)]
    _,repartos=proyecciones(f,f['lineas'],c) if c['modo']=='EMBARQUE' and not faltan else ([],[])
    return {'modo':c['modo'],'consolidadoConfirmado':c.get('consolidadoConfirmado',False),'origenes':r.origenes or [],'grupos':gs,'embarques':list(dict.fromkeys(embarque(l,c) for l in f['lineas'] if embarque(l,c))),
        'version':firma([r.formatos,f,guardada]),'asignaciones':c['asignaciones'],'embarquesPorLinea':c['embarquesPorLinea'],
        'faltanEmbarques':faltan,'filasSinEmbarque':[{'id':linea_id(l),'origen':l.get('origen') or 'PRINCIPAL','linea':l['linea'],'sku':l['sku']} for l in f['lineas'] if not str(l.get('embarque') or '').strip()],'repartos':repartos,
        'adicionales':[{'sku':s['sku'],'descripcion':s.get('descripcion','')} for s in f['skus'] if s.get('enPackingList') is False]}


def numero(n):return type(n) in (int,float) and math.isfinite(n) and n>=0

def guardar(db,codigo,datos,usuario):
    from app.services.correos_embarque import clave
    r=m.obtener(db,codigo,bloquear=True)
    vigente=configuracion(db,r.codigo,actual=True)
    anterior=vista(db,r.codigo,actual=True)
    if datos.get('version')!=anterior['version']:raise HTTPException(409,'Cambió la recepción o el plan de correos. Actualiza y revisa el reparto.')
    c={k:datos.get(k,vigente.get(k)) for k in ('modo','asignaciones','embarquesPorLinea','repartos')}
    p=vista(db,r.codigo,c,actual=True);f=fuente(db,r.codigo)
    if c['modo']=='RECEPCION' or len(p['embarques'])>1 and c['modo']=='PACKING_LIST':
        if datos.get('confirmarConsolidado') is not True:raise HTTPException(422,'Confirma que deseas consolidar estos embarques en el mismo correo.')
        c['consolidadoConfirmado']=True
    vacias={linea_id(l) for l in f['lineas'] if not str(l.get('embarque') or '').strip()}
    if any(k not in vacias or not isinstance(v,str) or not 1<=len(v.strip())<=80 for k,v in c['embarquesPorLinea'].items()):raise HTTPException(422,'Asigna embarque únicamente a las filas que no lo tienen, hasta 80 caracteres.')
    if c['modo']=='EMBARQUE' and p['faltanEmbarques']:raise HTTPException(422,'Asigna el embarque de todas las filas antes de dividir el correo.')
    ids={g['id'] for g in p['grupos']}
    if set(c['asignaciones'])!={s['sku'] for s in p['adicionales']} or any(v not in ids for v in c['asignaciones'].values()):raise HTTPException(422,'Asigna cada producto adicional a un grupo de envío.')
    anulados={e.get('anulaA') for e in f['eventos'] if e.get('tipo')=='ANULACION'}
    for e in f['eventos']:
        if e.get('tipo')!='CONTEO' or e.get('id') in anulados or not e.get('origen') or e.get('sku') not in c['asignaciones'] or not e.get('cantidad',0)>0:continue
        destino=next(g for g in p['grupos'] if g['id']==c['asignaciones'][e['sku']])
        if e['origen'] not in destino['packingLists']:raise HTTPException(422,'El packing list del conteo adicional '+e['sku']+' no pertenece al grupo elegido. Revisa su asignación.')
    if c['modo']=='EMBARQUE':
        if p['repartos'] and datos.get('repartoConfirmado') is not True:raise HTTPException(422,'Revisa y confirma cómo se reparten los SKU presentes en varios embarques.')
        if set(c['repartos'])!={s['id'] for s in p['repartos']}:raise HTTPException(422,'Completa el reparto de cada SKU compartido entre embarques.')
        for s in p['repartos']:
            rs=c['repartos'][s['id']];gs={g['id'] for g in s['grupos']}
            if not isinstance(rs,dict) or set(rs)!=gs:raise HTTPException(422,'Completa todos los embarques del SKU '+s['sku'])
            for x in rs.values():
                if not isinstance(x,dict) or not numero(x.get('cantidad')) or not isinstance(x.get('incidencias'),dict) or any(not numero(n) for n in x['incidencias'].values()):raise HTTPException(422,'Cantidades de reparto inválidas para '+s['sku'])
                if set(x['incidencias'])!={i['tipo'] for i in s['incidencias']} or set(x['pnc'])!=set(x['incidencias']) or any(x['pnc'][k]>n for k,n in x['incidencias'].items()) or sum(x['incidencias'].values())>x['cantidad']+1e-7:raise HTTPException(422,'Las incidencias no pueden superar la cantidad asignada de '+s['sku'])
                if any(not isinstance(x.get(k,''),str) or len(x.get(k,''))>300 for k in ('observacion','pallets')):raise HTTPException(422,'Revisa observación y pallets del reparto.')
            if abs(sum(x['cantidad'] for x in rs.values())-s['cantidad'])>1e-7:raise HTTPException(422,'La suma por embarques debe conservar el conteo de '+s['sku'])
            for i in s['incidencias']:
                if abs(sum(x['incidencias'][i['tipo']] for x in rs.values())-i['cantidad'])>1e-7 or abs(sum(x['pnc'][i['tipo']] for x in rs.values())-i.get('pnc',0))>1e-7:raise HTTPException(422,'Conserva las unidades de '+i['nombre']+' de '+s['sku'])
    else:c['repartos']={}
    registro=db.get(AppConfig,clave(r.codigo)) or AppConfig(clave=clave(r.codigo));registro.datos=c;registro.usuario=usuario;db.add(registro)
    ajustes.auditar(db,usuario,'AGRUPACION_CORREOS_REVISADA',r.codigo,{'modo':c['modo'],'grupos':p['grupos'],'repartos':c['repartos']})
    db.commit();return vista(db,r.codigo)


def reparto_vigente(c,pendientes):
    for s in pendientes:
        rs=c.get('repartos',{}).get(s['id'],{})
        if set(rs)!={g['id'] for g in s['grupos']} or abs(sum(x.get('cantidad',0) for x in rs.values())-s['cantidad'])>1e-7:
            raise HTTPException(409,'Cambió el conteo de '+s['sku']+'. Revisa su distribución entre embarques antes de preparar el informe.')
        tipos={i['tipo'] for i in s['incidencias']}
        if any(set(x.get('incidencias',{}))!=tipos or set(x.get('pnc',{}))!=tipos for x in rs.values()):
            raise HTTPException(409,'Cambió la calidad de '+s['sku']+'. Revisa el reparto de incidencias y PNC.')
        for i in s['incidencias']:
            if any(i['tipo'] not in x.get('incidencias',{}) or i['tipo'] not in x.get('pnc',{}) for x in rs.values()) or abs(sum(x['incidencias'][i['tipo']] for x in rs.values())-i['cantidad'])>1e-7 or abs(sum(x['pnc'][i['tipo']] for x in rs.values())-i.get('pnc',0))>1e-7:
                raise HTTPException(409,'Cambió la calidad de '+s['sku']+'. Revisa el reparto de incidencias y PNC.')


def metadatos(db,codigo):
    r=m.obtener(db,codigo);c=configuracion(db,r.codigo)
    if c['modo']!='EMBARQUE':
        from app.services.fotos_embarques import informacion
        return {'modo':c['modo'],'configuracion':c,'grupos':grupos(informacion(db,r.codigo)[2],r.origenes or [],c)}
    f=fuente(db,r.codigo)
    if any(not embarque(l,c) for l in f['lineas']):raise HTTPException(409,'Completa la asignación de embarques antes de preparar sus documentos.')
    filas,rs=proyecciones(f,f['lineas'],c)
    reparto_vigente(c,rs)
    return {'modo':c['modo'],'configuracion':c,'grupos':grupos(f['lineas'],r.origenes or [],c),'resultados':filas}


def filtrar(f,lineas,ident,c):
    from app.services.correos_embarque import filtrar as por_lista
    if c.get('modo')=='RECEPCION':
        if ident!='RECEPCION':raise HTTPException(422,'Grupo consolidado inválido')
        return {**f,'origen':ident,'nombreGrupo':'Recepción completa','tipoGrupo':'RECEPCION','packingLists':list(dict.fromkeys(l.get('origen') or 'PRINCIPAL' for l in lineas))}
    if c.get('modo')!='EMBARQUE':
        mapa=dict(c.get('asignaciones',{}))
        if {l.get('origen') or 'PRINCIPAL' for l in lineas}=={ident}:mapa.update({s['sku']:ident for s in f['skus'] if s.get('enPackingList') is False})
        grupo=next((g for g in grupos(lineas,[ident],c) if g['id']==ident),None)
        return {**por_lista(f,lineas,ident,mapa),'nombreGrupo':grupo['nombre'] if grupo else ident,'tipoGrupo':'PACKING_LIST'}
    gs=grupos(lineas,[],c);g=next((g for g in gs if g['id']==ident),None)
    if not g:raise HTTPException(422,'El embarque no pertenece a este plan de correos.')
    filas,pendientes=proyecciones(f,lineas,c)
    reparto_vigente(c,pendientes)
    eventos=[]
    for x in filas:
        if x['grupo']!=ident:continue
        eventos.append({'id':'reparto-'+firma([x['origen'],x['sku'],ident])[:24],'tipo':'CONTEO','sku':x['sku'],'origen':ident,
            'cantidad':x['contado'],'pallet':x['pallets'],'observacion':x['observacion'],'incidencias':[i for i in x['incidencias'] if i['cantidad']>0]})
    for s in f['skus']:
        if s.get('enPackingList') is False and c.get('asignaciones',{}).get(s['sku'])==ident:
            eventos.append({'id':'adicional-'+s['sku'],'tipo':'CONTEO','sku':s['sku'],'origen':ident,'cantidad':s['contado'],
                'pallet':'-'.join(s.get('pallets',{})),'incidencias':[{**i,'cantidad':n,'pnc':pnc} for i in s.get('incidencias',[]) for n,pnc in ((i.get('pnc',0),True),(i['cantidad']-i.get('pnc',0),False)) if n>0]})
    ls=[{**l,'origen':ident} for l in lineas if grupo_id(embarque(l,c))==ident]
    filtrado=por_lista({**f,'eventos':eventos,'fotos':[]},ls,ident,c.get('asignaciones',{}))
    miembros={s['sku'] for s in filtrado['skus']};fotos=[]
    for foto in f.get('fotos',[]):
        vs=[v for v in foto.get('rutasVinculadas') or [foto] if (not v.get('origen') or v['origen'] in g['packingLists']) and (not v.get('sku') or v['sku'] in miembros) and (not v.get('embarque') or v['embarque']==g['nombre'])]
        if not vs:continue
        compartida=any(v.get('sku') and v.get('embarque') is None and len({embarque(l,c) for l in lineas if l['sku']==v['sku'] and (not v.get('origen') or l.get('origen')==v['origen'])})>1 for v in vs)
        fotos.append({**foto,'sku':vs[0].get('sku',''),'categoria':vs[0].get('categoria','RECEPCION'),
            'origen':vs[0].get('origen',''),'embarque':vs[0].get('embarque'),'rutasVinculadas':vs,'requiereRevision':compartida})
    return {**filtrado,'fotos':fotos,'nombreGrupo':g['nombre'],'tipoGrupo':'EMBARQUE','packingLists':g['packingLists']}
