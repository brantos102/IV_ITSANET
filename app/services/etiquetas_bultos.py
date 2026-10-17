"""Lotes correlativos con instantánea durable y una etiqueta por unidad física."""
import hashlib
import json
import re
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.models import AppImpresion, AppIngreso, AppUnidadLogistica
from app.services import app_modelo as m, operacion


def estado(db, codigo):
    r = m.obtener(db, codigo)
    f = db.get(AppIngreso, r.codigo)
    anteriores = list(db.scalars(select(AppImpresion).where(AppImpresion.recepcion == r.codigo,
        AppImpresion.datos['tipo'].as_string() == 'BULTOS')
        .order_by(AppImpresion.datos['lote'].as_integer().desc()).limit(10)))
    return {'recepcion': r.codigo, 'cliente': r.cliente, 'total': r.bultos,
        'version': (f.datos or {}).get('version', 0) if f else 0,
        'literal': (f.datos or {}).get('etiquetasBultos', {}).get('literal', 'B') if f else 'B',
        'formato': (f.datos or {}).get('etiquetasBultos', {}).get('formato', '100x150') if f else '100x150',
        'cerrada': r.estado not in m.ABIERTAS,
        'anteriores': [{'id': j.id, 'lote': j.datos['lote'], 'usuario': j.usuario,
            'fecha': m._iso(j.creado_en), 'estado': j.estado, 'total': j.datos['copias']} for j in anteriores[:10]]}


def zpl(etiquetas, formato, recepcion, cliente, marca):
    alto = 1200 if formato == '100x150' else 400
    def texto(y, h, valor, lineas=1):
        valor = ''.join('\\' + format(b, '02X') for b in str(valor).encode())
        return f'^FO24,{y}^A0N,{h},{h-3}^FB752,{lineas},2,C,0^FH\\^FD{valor}^FS'
    partes = []
    for e in etiquetas:
        grande = alto == 1200
        partes += ['^XA', '^CI28', '^PW800', f'^LL{alto}', '^LH0,0',
            texto(24, 34, cliente[:60]), texto(75, 28, recepcion[:80], 2),
            texto(200 if grande else 140, 90 if grande else 50, e['rotulo']),
            texto(330 if grande else 205, 58 if grande else 32, f"BULTO {e['numero']} DE {e['total']}"),
            texto(440 if grande else 250, 28 if grande else 20, marca[:60]),
            texto(510, 27, e['codigoMadre'][:80], 2) if grande else '',
            f"^FO62,{760 if grande else 290}^BY1,2,{150 if grande else 55}^BCN,{150 if grande else 55},N,N,N,A^FD{e['serie']}^FS",
            texto(950 if grande else 355, 22 if grande else 17, 'ID ' + e['unidadId']),
            '^PQ1', '^XZ']
    return '\n'.join(partes)


def generar(db, codigo, datos, usuario, estacion=None):
    r = m.obtener(db, codigo, bloquear=True)
    clave = str(datos.get('clave') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,80}', clave): raise HTTPException(422, 'Falta identificador de solicitud')
    huella = hashlib.sha256(json.dumps({k:v for k,v in datos.items() if k != 'clave'}, sort_keys=True).encode()).hexdigest()
    previo = db.scalar(select(AppImpresion).where(AppImpresion.clave == clave))
    if previo:
        if previo.recepcion != r.codigo or previo.usuario != usuario or previo.datos.get('huellaBultos') != huella:
            raise HTTPException(409, 'El identificador ya corresponde a otra solicitud')
        return documento(previo)
    f = db.get(AppIngreso, r.codigo)
    revision = (f.datos or {}).get('version', 0) if f else 0
    if datos.get('version') != revision or datos.get('cantidadAnterior') != r.bultos:
        raise HTTPException(409, 'Otro supervisor cambió la recepción. Actualiza antes de imprimir.')
    literal = str(datos.get('literal') or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{1,8}', literal): raise HTTPException(422, 'Literal: de 1 a 8 letras o números')
    formato, destino = datos.get('formato'), datos.get('destino')
    if formato not in ('100x50', '100x150') or destino not in ('NAVEGADOR', 'ZPL', 'ESTACION'):
        raise HTTPException(422, 'Selecciona tamaño y destino de impresión')
    n = datos.get('total')
    if type(n) is not int or not 1 <= n <= min(1000, operacion.configuracion(db)['maxCopias']):
        raise HTTPException(422, 'Total fuera del máximo de etiquetas configurado por ADMIN')
    if destino == 'ESTACION' and not estacion: raise HTTPException(422, 'Selecciona una estación habilitada')
    operacion.ajustar_bultos(db, r.codigo, {'cantidad': n, 'cantidadAnterior': r.bultos}, usuario, confirmar=False)
    unidades = list(db.scalars(select(AppUnidadLogistica).where(AppUnidadLogistica.recepcion == r.codigo,
        AppUnidadLogistica.tipo == 'BULTO').order_by(AppUnidadLogistica.numero)))
    etiquetas = []
    for u in unidades:
        etiquetas.append({'unidadId': u.id, 'numero': u.numero, 'total': n,
            'rotulo': f'{literal}-{u.numero:03d}', 'codigoMadre': u.codigo or '', 'serie': 'LB'+u.id})
        u.datos = {**(u.datos or {}), 'etiquetaEmitida': True}
    f = f or AppIngreso(recepcion=r.codigo, datos={})
    d = {'protocolo': 'REGLAMENTARIO', **(f.datos or {}),
        'etiquetasBultos': {'literal': literal, 'formato': formato}, 'version': revision+1}
    f.datos = d; db.add(f)
    lote = 1 + db.scalar(select(func.count()).select_from(AppImpresion).where(AppImpresion.recepcion == r.codigo,
        AppImpresion.datos['tipo'].as_string() == 'BULTOS'))
    snapshot = {'tipo': 'BULTOS', 'sku': 'BULTOS', 'copias': n, 'cantidadPorEtiqueta': 1,
        'lote': lote, 'huellaBultos': huella, 'literal': literal, 'formato': formato,
        'destino': destino, 'cliente': r.cliente, 'recepcion': r.codigo, 'marca': d.get('marca', ''),
        'etiquetas': etiquetas}
    snapshot['zpl'] = zpl(etiquetas, formato, r.codigo, r.cliente, snapshot['marca'])
    j = AppImpresion(id=uuid4().hex, clave=clave, estacion=estacion or 'NAVEGADOR', recepcion=r.codigo,
        usuario=usuario, estado='PENDIENTE' if destino == 'ESTACION' else 'GENERADA', datos=snapshot)
    db.add(j)
    operacion.auditoria(db, r.codigo, usuario, 'ETIQUETAS_BULTOS_GENERADAS',
        {'trabajoId': j.id, 'lote': lote, 'total': n, 'literal': literal, 'formato': formato, 'destino': destino})
    try: db.commit()
    except IntegrityError:
        db.rollback()
        previo = db.scalar(select(AppImpresion).where(AppImpresion.clave == clave))
        if not previo or previo.recepcion != r.codigo or previo.usuario != usuario or previo.datos.get('huellaBultos') != huella:
            raise HTTPException(409, 'Solicitud de impresión en conflicto') from None
        return documento(previo)
    db.refresh(j)  # MySQL conserva milisegundos: devolver la fecha realmente persistida.
    return documento(j)


def documento(j):
    return {'id': j.id, 'estado': j.estado, 'fecha': m._iso(j.creado_en).replace('+00:00', 'Z'),
        **{k: j.datos[k] for k in ('lote','literal','formato','cliente','recepcion','marca','etiquetas','zpl')}}
