"""Selección de documentos vigentes del mismo grupo; nombres de salida independientes."""
import re
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppArchivo, AppInforme
from app.services import informes, archivos, app_modelo as m


def disponibles(db,codigo,origen=''):
    r=m.obtener(db,codigo);huella=informes.huella_contenido(db,r);salida=[]
    for f in db.scalars(select(AppInforme).where(AppInforme.recepcion==codigo).order_by(AppInforme.numero.desc()).limit(100)):
        if f.datos.get('huellaContenido')!=huella or f.datos.get('formato') not in ('envio','envio-ampliado','auditable'):continue
        for dato in f.datos.get('archivos',[]):
            if origen and dato.get('grupo',dato.get('origen'))!=origen:continue
            a=db.get(AppArchivo,dato['id'])
            if a and a.recepcion==codigo and (a.drive_id or archivos.ruta(a).is_file()):
                salida.append({'id':a.id,'nombre':a.nombre,'informeId':f.id,'revision':f.numero,
                    'formato':f.datos['formato'],'url':'/api/app/archivos/'+a.id})
    return salida


def nombre_salida(nombre,original):
    if not isinstance(nombre,str):raise HTTPException(422,'Escribe un nombre válido para el documento.')
    n=nombre.strip();extension=original.rsplit('.',1)[-1]
    if len(n)>160 or not re.fullmatch(r'[^\\/<>:"|?*\x00-\x1f]+\.'+re.escape(extension),n,re.I):raise HTTPException(422,'Nombre del documento: conserva la extensión, sin barras ni caracteres reservados (máximo 160).')
    return n


def validar_nombres(db,codigo,origen,nombres):
    permitidos={a['id']:a for a in disponibles(db,codigo,origen)}
    if not isinstance(nombres,dict) or len(nombres)>len(permitidos):raise HTTPException(422,'Revisa los nombres de los documentos disponibles.')
    if any(ident not in permitidos for ident in nombres):raise HTTPException(409,'Un nombre corresponde a un documento ajeno o de datos anteriores. Actualiza los documentos.')
    return {ident:nombre_salida(nombre,permitidos[ident]['nombre']) for ident,nombre in nombres.items()}


def validar(db,codigo,origen,seleccion,*,permitir_vacio=False):
    if not isinstance(seleccion,list) or not (0 if permitir_vacio else 1)<=len(seleccion)<=12:raise HTTPException(422,'Selecciona de 1 a 12 documentos vigentes para adjuntar.')
    permitidos={a['id']:a for a in disponibles(db,codigo,origen)};vistos=set();nombres=set();salida=[]
    for d in seleccion:
        if not isinstance(d,dict) or set(d)!={'id','nombre'} or not isinstance(d.get('id'),str) or d['id'] not in permitidos or d['id'] in vistos:raise HTTPException(409,'Un adjunto no corresponde al grupo y revisión actuales. Actualiza los documentos.')
        n=nombre_salida(d['nombre'],permitidos[d['id']]['nombre'])
        if n.casefold() in nombres:raise HTTPException(422,'Usa nombres diferentes para los documentos seleccionados.')
        vistos.add(d['id']);nombres.add(n.casefold());salida.append({'id':d['id'],'nombre':n})
    return salida


def objetos(db,codigo,seleccion):
    salida=[]
    for d in seleccion:
        a=db.get(AppArchivo,d['id'])
        if a and a.recepcion==codigo:salida.append(SimpleNamespace(id=a.id,nombre=d['nombre']))
    return salida
