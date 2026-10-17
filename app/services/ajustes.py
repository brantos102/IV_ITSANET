"""Políticas operativas editables desde ADMIN; secretos siguen separados."""
from copy import deepcopy
from uuid import uuid4
from fastapi import Depends, HTTPException
from app.db import get_db
from app.models import AppConfig, AppAuditoriaGeneral, Rol
from app.security import usuario_actual

ACCIONES={'gestionarUsuarios':'Gestionar y aprobar cuentas','asignarSupervisor':'Asignar rol de supervisor',
 'gestionarClientes':'Gestionar clientes y reglas operativas',
 'exportarInformes':'Generar y descargar informes','cerrarRecepciones':'Finalizar y enviar informes',
 'verEquipo':'Consultar operarios activos'}
INCIDENCIAS=[{'codigo':'OK','nombre':'OK','descripcion':'Conforme','pnc':False,'activo':True},
 {'codigo':'FALTANTE','nombre':'FALTANTE','descripcion':'Faltan piezas','pnc':False,'activo':True},
 {'codigo':'SOBRANTE','nombre':'SOBRANTE','descripcion':'Sobran piezas','pnc':False,'activo':True},
 {'codigo':'CAJA_MALTRATADA','nombre':'CAJA MALTRATADA O ABIERTA','descripcion':'Caja rota, aplastada o abierta','pnc':False,'activo':True},
 {'codigo':'MAL_ESTADO','nombre':'MAL ESTADO','descripcion':'Producto roto, rayado o golpeado','pnc':True,'activo':True},
 {'codigo':'INCORRECTO','nombre':'INCORRECTO','descripcion':'Producto equivocado','pnc':True,'activo':True},
 {'codigo':'ROTULADO_ERRONEO','nombre':'ROTULADO ERRONEO','descripcion':'Etiqueta o lote erróneo','pnc':True,'activo':True}]
DEFECTO={'permisos':{'SUPERVISOR':{a:True for a in ACCIONES},'OPERADOR':{a:False for a in ACCIONES}},
 'clientes':{},'incidencias':INCIDENCIAS}


def configuracion(db):
    f=db.get(AppConfig,'politicas');d=deepcopy(DEFECTO)
    if f:
        d.update(deepcopy(f.datos))
        for rol in ('SUPERVISOR','OPERADOR'):
            d['permisos'][rol]={**DEFECTO['permisos'][rol],**d['permisos'].get(rol,{})}
    return d


def permisos(db,op):
    return {a:True for a in ACCIONES} if op.rol==Rol.ADMIN else configuracion(db)['permisos'].get(op.rol.value,{})


def requiere(accion):
    def validar(db=Depends(get_db),op=Depends(usuario_actual)):
        if not permisos(db,op).get(accion):raise HTTPException(403,'Tu rol no tiene permiso para esta operación')
        return op
    return validar


def cliente(db,nombre):
    f=configuracion(db)['clientes'].get(str(nombre).strip().upper(),{})
    return {'palletRequerido':True,'posicionRequerida':False,'columnas':{},**f}


def auditar(db,usuario,accion,referencia,datos):
    db.add(AppAuditoriaGeneral(id=uuid4().hex,usuario=usuario,accion=accion,referencia=str(referencia),datos=datos))


def guardar(db,datos,usuario):
    d=configuracion(db)
    for k in DEFECTO:
        if k in datos:d[k]=deepcopy(datos[k])
    if not isinstance(d['permisos'],dict) or set(d['permisos'])-{'SUPERVISOR','OPERADOR'}:
        raise HTTPException(422,'Solo se configuran permisos de supervisor y operador; ADMIN conserva su control')
    for rol in ('SUPERVISOR','OPERADOR'):
        p=d['permisos'].setdefault(rol,{})
        if not isinstance(p,dict) or set(p)-set(ACCIONES) or any(type(v)is not bool for v in p.values()):raise HTTPException(422,'Permisos inválidos')
        d['permisos'][rol]={**DEFECTO['permisos'][rol],**p}
    if not isinstance(d['clientes'],dict) or len(d['clientes'])>100:raise HTTPException(422,'Clientes inválidos')
    campos={'marca','cliente','fisica','validacion','desface','pallet','posicion','codigoBarra','cantidadIncidencia','incidencia','observacion','evidencia','depot'}
    for n,c in d['clientes'].items():
        if not n or len(n)>60 or n!=n.upper() or not isinstance(c,dict):raise HTTPException(422,'Usa el identificador del cliente en mayúsculas')
        for k in ('palletRequerido','posicionRequerida'):
            if k in c and type(c[k])is not bool:raise HTTPException(422,'Reglas del cliente inválidas')
        cols=c.get('columnas',{})
        if not isinstance(cols,dict) or set(cols)-campos or any(type(v)is not int or not 0<=v<=1000 for v in cols.values()) or len(set(cols.values()))!=len(cols):
            raise HTTPException(422,'Cada campo debe tener una columna distinta, entre A y ALM')
    if not isinstance(d['incidencias'],list) or any(not isinstance(i,dict) for i in d['incidencias']) or {i.get('codigo') for i in d['incidencias']}!={i['codigo'] for i in INCIDENCIAS} or len(d['incidencias'])!=len(INCIDENCIAS):
        raise HTTPException(422,'Conserva los identificadores de las siete incidencias')
    for i in d['incidencias']:
        if not isinstance(i.get('nombre'),str) or not 1<=len(i['nombre'])<=80 or type(i.get('pnc'))is not bool or type(i.get('activo'))is not bool:raise HTTPException(422,'Incidencia inválida')
        i['descripcion']=str(i.get('descripcion') or '')[:200]
        if i['codigo'] in ('OK','FALTANTE','SOBRANTE'):i['pnc']=False;i['activo']=True
    f=db.get(AppConfig,'politicas') or AppConfig(clave='politicas');f.datos=d;f.usuario=usuario;db.add(f)
    auditar(db,usuario,'POLITICAS_ACTUALIZADAS','politicas',{'clientes':list(d['clientes']),'permisos':d['permisos']});db.commit();return configuracion(db)
