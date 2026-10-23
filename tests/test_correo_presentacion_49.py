"""El borrador elige evidencia sin alterar cantidades, fotos ni correos emitidos."""
import base64
import io

import pytest
from PIL import Image
from sqlalchemy import select

from app.models import AppArchivo, AppEntrega
from app.services import app_modelo as m, correo_redactado as correo_svc
from app.services.instantaneas import expandir
from tests.test_remitente_responsable import correo


def subir(cliente, codigo, color, categoria='RECEPCION', sku=''):
    b = io.BytesIO(); Image.new('RGB', (12, 12), color).save(b, format='PNG')
    r = cliente.post(f'/api/app/recepciones/{codigo}/archivos/foto', json={
        'nombre': color+'.png', 'tipo':'image/png', 'base64':base64.b64encode(b.getvalue()).decode(),
        'categoria':categoria, 'sku':sku, 'tipoEvidencia':'ITEM_NOVEDAD' if sku else 'PANORAMICA'})
    assert r.status_code == 201, r.text
    return r.json()['id']


def ruta(codigo): return f'/api/operacion/recepciones/{codigo}/correo'


def test_propone_solo_fotos_de_novedades_actuales_y_oculta_totales(cliente, db, correo):
    codigo,_ = correo
    # Un faltante anterior resuelto no se vuelve foto de PNC por defecto.
    historica = subir(cliente, codigo, 'red', 'FALTANTE', 'SKU1')
    general = subir(cliente, codigo, 'white')
    m.registrar_conteo(db, codigo, 'sup', {'id':'pnc49','sku':'SKU1','cantidad':1,'pallet':'A2',
        'confirmarSobrante':True, 'incidencias':[{'tipo':'MAL_ESTADO','cantidad':1}]})
    pnc = subir(cliente, codigo, 'blue', 'PNC', 'SKU1')
    v = cliente.get(ruta(codigo)).json()
    assert v['fotosSeleccionadas'] == [pnc]
    assert {f['id'] for f in v['fotos']} == {historica, general, pnc}
    assert 'Resumen de unidades' not in v['html'] and 'Fotografías registradas' not in v['html']
    assert 'Producto no conforme' in v['html'] and 'background:#16345c' in v['html']
    assert next(f for f in v['fotos'] if f['id']==historica)['categoria'] == 'FALTANTE'
    # Una misma imagen vinculada a varios SKU se describe con el de la sección.
    _,_,fuente,archivos=correo_svc._fuente(db,codigo)
    fuente['fotos']=[{'archivoId':'compartida49','fileId':'drive-compartida49','sku':'SKU_ANTERIOR','categoria':'FALTANTE',
        'rutasVinculadas':[{'sku':'SKU_ANTERIOR','categoria':'FALTANTE'},{'sku':'SKU1','categoria':'PNC'}]}]
    html=correo_svc.renderizar(codigo,fuente,v['campos'],archivos,'personal@example.test')['html']
    assert 'alt="SKU1"' in html and 'alt="SKU_ANTERIOR"' not in html



def test_editar_seleccion_no_modifica_fotos_o_conteos_y_admite_cliente_anterior(cliente, db, correo):
    codigo,_ = correo
    a = subir(cliente, codigo, 'green'); b = subir(cliente, codigo, 'yellow')
    antes = cliente.get(f'/api/app/recepciones/{codigo}/eventos').json()
    v = cliente.get(ruta(codigo)).json()
    opciones = {'mostrarTotales':True,'fotosModo':'ELEGIDAS','fotosIds':[b]}
    r = cliente.put(ruta(codigo), json={'version':v['version'],'campos':{**v['campos'],'notas':'Ubicación revisada'},'presentacion':opciones})
    assert r.status_code==200,r.text
    v=r.json(); assert v['fotosSeleccionadas']==[b] and 'Resumen de unidades' in v['html']
    assert a not in v['html'] and 'Ubicación revisada' in v['html']
    r = cliente.put(ruta(codigo),json={'version':v['version'],'campos':{**v['campos'],'saludo':'Buenos días,'}})
    assert r.status_code==200 and r.json()['presentacion']==opciones
    assert cliente.get(f'/api/app/recepciones/{codigo}/eventos').json()==antes
    db.rollback(); assert len(list(db.scalars(select(AppArchivo).where(AppArchivo.recepcion==codigo))))==2


@pytest.mark.parametrize('opciones',[
    {'mostrarTotales':'false','fotosModo':'NINGUNA','fotosIds':[]},
    {'mostrarTotales':False,'fotosModo':'ELEGIDAS','fotosIds':['foto-ajena']},
    {'mostrarTotales':False,'fotosModo':'ELEGIDAS','fotosIds':['repetida']*2},
    {'mostrarTotales':False,'fotosModo':'ELEGIDAS','fotosIds':[str(i) for i in range(13)]},
    {'mostrarTotales':False,'fotosModo':'HTML','fotosIds':[]},
])
def test_no_acepta_imagen_ajena_opciones_invalidas_o_exceso(cliente, correo, opciones):
    codigo,_=correo;v=cliente.get(ruta(codigo)).json()
    r=cliente.put(ruta(codigo),json={'version':v['version'],'campos':v['campos'],'presentacion':opciones})
    assert r.status_code in (409,422),r.text
    assert cliente.get(ruta(codigo)).json()['revision']==v['revision']


def test_seleccion_obsoleta_no_sobrescribe_otro_supervisor(cliente, correo):
    codigo,_=correo;v=cliente.get(ruta(codigo)).json()
    datos={'version':v['version'],'campos':v['campos'],'presentacion':{'mostrarTotales':False,'fotosModo':'NINGUNA','fotosIds':[]}}
    assert cliente.put(ruta(codigo),json=datos).status_code==200
    assert cliente.put(ruta(codigo),json=datos).status_code==409


def test_html_id_drive_y_seleccion_se_congelan_juntos_en_cierre_manual(cliente, db, correo):
    codigo,datos=correo;a=subir(cliente,codigo,'orange')
    db.rollback();foto=db.get(AppArchivo,a);foto.drive_id='drive-foto-49';db.commit()
    v=cliente.get(ruta(codigo)).json()
    opciones={'mostrarTotales':False,'fotosModo':'ELEGIDAS','fotosIds':[a]}
    v=cliente.put(ruta(codigo),json={'version':v['version'],'campos':{**v['campos'],'destinatarios':datos['destinatarios']},'presentacion':opciones}).json()
    assert v['imagenesDrive']==['drive-foto-49']
    datos['eventos']=[e['id'] for e in cliente.get(f'/api/app/recepciones/{codigo}/eventos').json()]
    r=cliente.post(f'/api/app/recepciones/{codigo}/entrega',json={**datos,'modoEntrega':'MANUAL','correoVersion':v['version']})
    assert r.status_code==201,r.text
    db.rollback();db.expire_all();e=db.get(AppEntrega,r.json()['id']);final=expandir(e.datos)['correoFinal']
    assert final['html']==v['html'] and final['presentacion']==opciones and final['fotosSeleccionadas']==[a]
    e.estado='ENTREGADA';db.commit()
    cerrado=cliente.get(ruta(codigo)+'?entregaId='+e.id).json()
    assert cerrado['soloLectura'] and cerrado['html']==final['html']
    assert cliente.put(ruta(codigo),json={'version':cerrado['version'],'entregaId':e.id,'campos':v['campos'],'presentacion':opciones}).status_code==409


def test_dos_supervisores_no_sobrescriben_borrador_mysql(cliente, db, correo):
    if db.bind.dialect.name != 'mysql': pytest.skip('Bloqueo real de MySQL en base desechable')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException
    from app.db import SessionLocal
    codigo,_=correo
    versiones={u:correo_svc.vista(db,codigo,u) for u in ('personal@example.test','responsable@example.test')}
    db.rollback();barrera=Barrier(2)
    def guardar(u):
        with SessionLocal() as sesion:
            v=versiones[u];barrera.wait(timeout=10)
            try:
                correo_svc.guardar(sesion,codigo,{'version':v['version'],'campos':{**v['campos'],'notas':'Revisado por '+u},
                    'presentacion':{'mostrarTotales':False,'fotosModo':'NINGUNA','fotosIds':[]}},u)
                return 200
            except HTTPException as exc:
                sesion.rollback();return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados=list(pool.map(guardar,versiones))
    assert sorted(resultados)==[200,409]
    db.expire_all();assert correo_svc.vista(db,codigo,'personal@example.test')['revision']==1
