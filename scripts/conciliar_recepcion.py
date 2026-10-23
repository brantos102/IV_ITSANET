#!/usr/bin/env python3
"""Conciliación de una recepción con SELECT y transacción MySQL READ ONLY.

No importa la aplicación, no inicializa tablas y no muestra credenciales.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import unicodedata


def documento(valor,defecto):
    decodificado=json.loads(valor) if isinstance(valor,str) else valor
    return defecto if decodificado is None else decodificado


def numero(valor):return Decimal(str(valor or 0))


def resumen(filas):
    return {'lineas':len(filas),'sku_distintos':len({f['sku'] for f in filas}),
        'unidades':sum((numero(f['cantidad']) for f in filas),Decimal(0))}


def agrupar(filas,campos):
    grupos=defaultdict(list)
    for fila in filas:grupos[tuple(str(fila.get(c) or 'SIN DATO') for c in campos)].append(fila)
    return [{**dict(zip(campos,k)),**resumen(fs)} for k,fs in sorted(grupos.items())]


def normalizar(v):return ''.join(c for c in unicodedata.normalize('NFD',str(v)).upper() if c.isalnum())


def analizar(recepcion,lineas,skus):
    formatos=documento(recepcion.get('formatos'),{});filas=[];distintos=0;cantidades_originales=[];cantidades_distintas=0
    for linea in lineas:
        extra=documento(linea.get('extra'),{});formato=formatos.get(str(linea['origen']).replace('.','~'),{})
        # La clave de formato puede usar el escape histórico de app_modelo.
        if not formato:
            formato=next((v for v in formatos.values() if v.get('encabezados') and len(formatos)==1),{})
        cab=[normalizar(v) for v in formato.get('encabezados',[])];cruda=extra.get('cruda') or []
        def celda(nombres):
            idx=next((i for i,v in enumerate(cab) if v in nombres),None)
            return str(cruda[idx]).strip().upper() if idx is not None and idx<len(cruda) and cruda[idx] is not None else None
        original=celda({'CANTIDAD','QTY','QUANTITY'})
        if original is not None:
            try:
                valor=numero(original)
                if valor.is_finite():
                    cantidades_originales.append(valor)
                    cantidades_distintas+=valor!=numero(linea['cantidad'])
            except Exception:pass
        emb=celda({'EMBARQUE','SHIPMENT'});cont=celda({'NOMBRECONTENEDOR','CONTENEDOR','NUMEROCONTENEDOR','CONTAINER'})
        if emb is not None and emb!=str(extra.get('embarque') or '').upper() or cont is not None and cont!=str(extra.get('contenedor') or '').upper():distintos+=1
        filas.append({'origen':linea['origen'],'sku':linea['sku'],'cantidad':linea['cantidad'],
            'embarque':extra.get('embarque'),'contenedor':extra.get('contenedor'),
            'embarque_excel':emb,'contenedor_excel':cont})
    totales=documento(recepcion.get('totales'),{});rs=resumen(filas)
    declarados=[s for s in skus if s['en_packing_list']]
    esperado=sum((numero(s['esperado']) for s in declarados),Decimal(0))
    avisos=[]
    if numero(totales.get('unidades'))!=rs['unidades']:avisos.append('Las unidades de cabecera no coinciden con la suma de líneas.')
    if esperado!=rs['unidades']:avisos.append('El esperado por SKU no coincide con la suma de líneas.')
    if numero(totales.get('skus'))!=rs['sku_distintos']:avisos.append('Los SKU de cabecera difieren de los SKU de las líneas; revisar adicionales y caché de totales.')
    if cantidades_distintas:avisos.append('Hay cantidades guardadas distintas de las celdas originales; no corregir sin conciliar con el archivo.')
    if distintos:avisos.append('Hay identificación logística distinta de las celdas originales; revisar antes de corregir embarques.')
    return {'recepcion':recepcion['codigo'],'estado':recepcion['estado'],'capturado_utc':datetime.now(timezone.utc).isoformat(),
        'cabecera':totales,'lineas_guardadas':rs,
        'sku_declarados':len(declarados),'sku_adicionales':len(skus)-len(declarados),
        'unidades_esperadas_por_sku':esperado,
        'unidades_fisicas_registradas':sum((numero(s['contado']) for s in skus),Decimal(0)),
        'por_lista':agrupar(filas,['origen']),
        'por_embarque':agrupar(filas,['embarque']),
        'por_contenedor':agrupar(filas,['embarque','contenedor']),
        'segun_celdas_originales':agrupar(filas,['embarque_excel','contenedor_excel']),
        'lineas_con_metadatos_distintos':distintos,
        'lineas_con_cantidad_original_verificable':len(cantidades_originales),
        'lineas_con_cantidad_distinta_original':cantidades_distintas,
        'unidades_en_celdas_originales':sum(cantidades_originales,Decimal(0)) if len(cantidades_originales)==len(filas) else None,
        'avisos':avisos,
        'alcance':'Lectura consistente de MySQL; no consulta Google ni modifica registros. Las referencias por contenedor o embarque pueden repetirse entre grupos.'}


def consultar(url,codigo):
    import pymysql
    from sqlalchemy.engine import make_url
    u=make_url(url)
    if not u.drivername.startswith(('mysql','mariadb')) or not u.database:raise ValueError('Se requiere una base MySQL configurada.')
    extras={k:u.query[k] for k in ('unix_socket','ssl_ca') if u.query.get(k)}
    con=pymysql.connect(host=u.host or 'localhost',port=u.port or 3306,user=u.username,password=u.password,
        database=u.database,charset='utf8mb4',connect_timeout=5,read_timeout=15,autocommit=True,**extras)
    try:
        with con.cursor(pymysql.cursors.DictCursor) as c:
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            c.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            c.execute('SELECT codigo,estado,totales,formatos FROM app_recepciones WHERE codigo=%s',(codigo,))
            recepcion=c.fetchone()
            if not recepcion:raise ValueError('La recepción no existe en esta base.')
            c.execute('SELECT origen,sku,cantidad,extra FROM app_lineas WHERE recepcion=%s ORDER BY orden,id',(codigo,));lineas=c.fetchall()
            c.execute('SELECT sku,esperado,contado,en_packing_list FROM app_skus WHERE recepcion=%s',(codigo,));skus=c.fetchall()
            return analizar(recepcion,lineas,skus)
    finally:
        con.rollback();con.close()


def serializar(v):
    if isinstance(v,Decimal):return int(v) if v==v.to_integral_value() else float(v)
    raise TypeError(type(v).__name__)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--codigo',required=True);args=p.parse_args()
    try:r=consultar(os.environ.get('VAL_DATABASE_URL',''),args.codigo.strip().upper())
    except Exception as exc:
        print('No se pudo completar la lectura ('+type(exc).__name__+'). No se modificaron registros.');return 1
    print(json.dumps(r,ensure_ascii=False,indent=2,default=serializar));return 0


if __name__=='__main__':raise SystemExit(main())
