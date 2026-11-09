"""Relaciones de etiquetas separadas por cliente. Nunca convierten conteos."""
from types import SimpleNamespace
import math
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, or_
from app.models import ProductoRelacion, Producto, ProductoCodigo, utcnow
from app.services.normalize import limpiar, normalizar_sku


def variantes(codigo):
    """UPC-A/EAN-13 con cero de relleno: solo equivalencias con dígito válido."""
    n=normalizar_sku(codigo);out=[n]
    if n.isdigit() and len(n) in (12,13):
        control=(10-sum(int(c)*(3 if i%2==0 else 1) for i,c in enumerate(n[-2::-1]))%10)%10
        if control==int(n[-1]):
            if len(n)==12:out.append('0'+n)
            elif n.startswith('0'):out.append(n[1:])
    return out


def candidatos(db, codigo, cliente=None):
    normal=normalizar_sku(codigo)
    vs=variantes(codigo)
    q=select(ProductoRelacion).where(or_(ProductoRelacion.codigo.in_(vs),ProductoRelacion.sku==normal))
    if cliente:q=q.where(ProductoRelacion.cliente==limpiar(cliente).upper())
    rs=list(db.scalars(q));out={}
    for r in rs:
        p=db.get(Producto,r.sku)
        if not p or p.cliente.upper()!=r.cliente:
            p=SimpleNamespace(sku=r.sku,cliente=r.cliente,descripcion='',ean=r.valor,
                unidad=None,inactivo=False,existe_depot=False,codigo_alternativo=None,actualizado_en=None)
        out[(r.cliente,r.sku)]=p
    alias=db.get(ProductoCodigo,normal)
    q=select(Producto).where(or_(Producto.sku==normal,Producto.ean.in_(vs+[limpiar(codigo)]),
        Producto.codigo_alternativo==normal,Producto.sku==(alias.sku if alias else normal)))
    if cliente:q=q.where(Producto.cliente==limpiar(cliente).upper())
    for p in db.scalars(q):out[(p.cliente.upper(),p.sku)]=p
    return list(out.values())


def importar(db, filas, usuario):
    if not isinstance(filas,list) or not 1<=len(filas)<=20000:
        raise HTTPException(422,'Relaciones: entre 1 y 20000 filas por archivo.')
    normalizadas={}
    for i,f in enumerate(filas,2):
        if not isinstance(f,dict):raise HTTPException(422,f'Fila {i}: datos inválidos.')
        c=limpiar(f.get('cliente')).upper();s=normalizar_sku(f.get('sku'));v=limpiar(f.get('codigoBarras'));b=normalizar_sku(v)
        if not c or len(c)>60 or not s or len(s)>80 or not b or len(b)>80 or len(v)>80:
            raise HTTPException(422,f'Fila {i}: cliente, SKU o código inválidos.')
        cant=f.get('cantidadReferencia')
        if cant not in (None,''):
            try:cant=float(cant)
            except (ValueError,TypeError):raise HTTPException(422,f'Fila {i}: cantidad de referencia inválida.') from None
            if not math.isfinite(cant) or not 0<=cant<=99999999999:
                raise HTTPException(422,f'Fila {i}: cantidad de referencia fuera de rango.')
            if Decimal(str(cant)) % Decimal('0.001'):
                raise HTTPException(422,f'Fila {i}: las unidades por empaque admiten como máximo tres decimales, sin redondeo silencioso.')
        else:cant=None
        k=(c,b)
        if k in normalizadas and normalizadas[k]['sku']!=s:
            raise HTTPException(409,f'Fila {i}: código con dos SKU para el mismo cliente.')
        if k in normalizadas:
            previo=normalizadas[k]['cantidad_referencia']
            if previo and cant and previo!=cant:
                raise HTTPException(409,f'Fila {i}: unidades por empaque contradictorias para el mismo código y cliente.')
            if previo and not cant:cant=previo
        normalizadas[k]={'sku':s,'valor':v,'tipo':limpiar(f.get('tipoCodigo') or 'ETIQUETA')[:30],
            'cantidad_referencia':cant,'usuario':usuario,'actualizado_en':utcnow()}
    # Una lectura de cada tabla permite revisar el archivo completo sin consultas por fila.
    previos={(r.cliente,r.codigo):r for r in db.scalars(select(ProductoRelacion))}
    productos={p.sku:p for p in db.scalars(select(Producto))};legacy={}
    for p in productos.values():
        for v in (p.sku,p.ean,p.codigo_alternativo):
            if v:legacy.setdefault((p.cliente.upper(),normalizar_sku(v)),set()).add(p.sku)
    for a in db.scalars(select(ProductoCodigo)):
        if a.sku in productos:legacy.setdefault((productos[a.sku].cliente.upper(),a.codigo),set()).add(a.sku)
    for k,d in normalizadas.items():
        if (k in previos and previos[k].sku!=d['sku']) or legacy.get(k,set())-{d['sku']}:
            raise HTTPException(409,f'{k[0]}: el código {k[1]} tiene otra relación existente. No se reasignó.')
    nuevos=0
    for k,d in normalizadas.items():
        r=previos.get(k)
        if not r:r=ProductoRelacion(cliente=k[0],codigo=k[1]);db.add(r);nuevos+=1
        elif r.cantidad_referencia and not d['cantidad_referencia']:
            d={**d,'cantidad_referencia':r.cantidad_referencia}
        for attr,v in d.items():setattr(r,attr,v)
    db.flush()
    return {'recibidas':len(filas),'equivalentes':len(filas)-len(normalizadas),
        'procesadas':len(normalizadas),'nuevas':nuevos,'existentes':len(normalizadas)-nuevos,
        'clientes':len({k[0] for k in normalizadas}),'sinFactor':sum(not d['cantidad_referencia'] for d in normalizadas.values()),
        'mensaje':'Relaciones por cliente guardadas. No se modificaron productos, conteos ni existencias. CANTIDAD indica unidades por empaque; su aplicación requiere confirmación del operario.'}


def detalle(db,codigo,cliente):
    if not cliente:return {}
    r=db.get(ProductoRelacion,(limpiar(cliente).upper(),normalizar_sku(codigo)))
    if not r:
        for v in variantes(codigo)[1:]:
            r=db.get(ProductoRelacion,(limpiar(cliente).upper(),v))
            if r:break
    if not r:return {}
    return {'unidadesPorCodigo':r.cantidad_referencia if r.cantidad_referencia and r.cantidad_referencia>0 else None,
        'tipoCodigo':r.tipo,'codigoEtiqueta':r.valor,'skuRelacionado':r.sku}
