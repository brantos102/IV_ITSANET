"""La API real del WMS: /gettoken y /getstock.

Estas pruebas no hablan con el WMS. Le ponen delante un httpx.MockTransport que
responde como él —incluido lo que hace cuando revoca un token— y comprueban que
el cliente lo entiende. Es lo único que se puede comprobar sin credenciales, y
es justo donde estaban las suposiciones: el cliente anterior hablaba con una API
inventada (`GET /productos/{sku}` con un Bearer) que el WMS no tiene.

Los nombres de campo son los reales, copiados del proxy de Apps Script que ya
lleva meses en producción: «COD. PRODUCTO», «NRO. LOTE», «COD. CLIENTE».
"""
from __future__ import annotations

import httpx
import pytest

from app.services import depot as svc

BASE = "https://ejemplo.invalid/q_apidepot"


def api(respuestas, **kw):
    """Un DepotAPI contra un WMS de mentira. `respuestas(peticion) -> Response`."""
    llamadas = []

    def manejar(peticion: httpx.Request) -> httpx.Response:
        llamadas.append(peticion)
        return respuestas(peticion, llamadas)

    cli = svc.DepotAPI(base_url=BASE, usuario="u", clave="c", cliente="VENTURA",
                       transporte=httpx.MockTransport(manejar), **kw)
    return cli, llamadas


FILA = {
    "COD. PRODUCTO": "2H0 525.345", "DESCRIPCION": "ARANDELA", "UNIDAD": "UND",
    "FAMILIA": "REPUESTOS", "COD. CLIENTE": "ventura", "CANTIDAD": "12",
    "NAVE": "A", "CALLE": "01", "COLUMNA": "03", "NIVEL": "2",
    "NRO. LOTE": "L1", "EST. MERC.": "BUENO",
}


# --------------------------------------------------------------------------- #
# El token
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cuerpo", [
    '{"token":"ABC"}',
    '{"Token":"ABC"}',
    '{"Result":"ABC"}',
    '[{"token":"ABC"}]',
    '{"Result":{"token":"ABC"}}',
    '"ABC"',
    'ABC',
    '\ufeffABC',
    '\ufeff"ABC"',
    '\ufeff{"token":"ABC"}',
    '{"token":"\\ufeffABC"}',
])
def test_el_token_se_lee_en_todas_las_formas_que_lo_devuelve(cuerpo):
    """El mismo surtido que acepta el proxy: si uno lo entiende, el otro también."""
    assert svc.extraer_token(cuerpo) == "ABC"


@pytest.mark.parametrize("cuerpo", ["", "   ", "{}", "{no es json", '\ufeff', '<html>Acceso</html>', '{"token":["T"]}', 'T\r\npassword: x'])
def test_una_respuesta_sin_token_no_se_confunde_con_un_token(cuerpo):
    assert svc.extraer_token(cuerpo) is None


def test_las_credenciales_viajan_en_las_cabeceras_que_espera_el_wms():
    cli, llamadas = api(lambda p, _: httpx.Response(200, text='{"token":"T1"}'))
    assert cli.token() == "T1"
    p = llamadas[0]
    assert p.url.path.endswith("/gettoken")
    assert p.headers["userid"] == "u"
    assert p.headers["password"] == "c"
    assert "usuario" not in p.headers and "clave" not in p.headers
    assert "cliente" not in p.headers  # coincide con obtenerTokenCliente_ de Clientes.gs


def test_el_token_no_se_vuelve_a_pedir_en_cada_llamada():
    """Pedirlo en cada escaneo multiplicaría por dos el tráfico contra el WMS."""
    cli, llamadas = api(lambda p, _: httpx.Response(
        200, text='{"token":"T1"}' if "gettoken" in str(p.url) else "[]"))
    cli.token(); cli.token(); cli.pedir("/getstock")
    assert sum(1 for p in llamadas if "gettoken" in str(p.url)) == 1


def test_credenciales_rechazadas_no_se_reintentan():
    """Un 401 al PEDIR el token es la clave mal: insistir solo bloquea la cuenta."""
    cli, llamadas = api(lambda p, _: httpx.Response(401, text="no"))
    with pytest.raises(svc.DepotRechazado):
        cli.token()
    assert len(llamadas) == 1


# --------------------------------------------------------------------------- #
# El reintento: el WMS revoca tokens antes de su vencimiento
# --------------------------------------------------------------------------- #
def test_un_token_revocado_se_renueva_y_la_llamada_sale_adelante():
    def responder(p, llamadas):
        if "gettoken" in str(p.url):
            return httpx.Response(200, text='{"token":"T%d"}' % len(llamadas))
        # El primer /getstock va con el token viejo y el WMS lo rechaza.
        if p.headers["token"] == "T1":
            return httpx.Response(403, text="token revocado")
        return httpx.Response(200, json={"Result": [FILA]})

    cli, llamadas = api(responder)
    filas = cli.stock()
    assert len(filas) == 1, "una revocación no puede perder la consulta"
    assert sum(1 for p in llamadas if "gettoken" in str(p.url)) == 2


def test_pero_solo_una_vez():
    """Si el segundo token también lo rechaza, son las credenciales."""
    cli, llamadas = api(lambda p, _: httpx.Response(200, text='{"token":"T"}')
                        if "gettoken" in str(p.url) else httpx.Response(401))
    with pytest.raises(svc.DepotRechazado):
        cli.pedir("/getstock")
    assert sum(1 for p in llamadas if "getstock" in str(p.url)) == 2


def test_el_token_viaja_en_la_cabecera_token_no_como_bearer():
    cli, llamadas = api(lambda p, _: httpx.Response(200, text='{"token":"T1"}')
                        if "gettoken" in str(p.url) else httpx.Response(200, json=[]))
    cli.pedir("/getstock")
    p = [x for x in llamadas if "getstock" in str(x.url)][0]
    assert p.headers["token"] == "T1"
    assert "authorization" not in p.headers


def test_si_el_wms_no_contesta_se_dice_que_no_contesta():
    def caerse(p, _):
        raise httpx.ConnectError("sin ruta al host")
    cli, _ = api(caerse)
    with pytest.raises(svc.DepotNoDisponible):
        cli.token()


def test_una_respuesta_que_no_es_json_no_sale_como_error_interno():
    cli, _ = api(lambda p, _: httpx.Response(200, text='{"token":"T"}')
                 if "gettoken" in str(p.url) else httpx.Response(200, text="<html>502"))
    with pytest.raises(svc.DepotNoDisponible) as e:
        cli.pedir("/getstock")
    assert "no es JSON" in str(e.value)


# --------------------------------------------------------------------------- #
# La traducción de una fila
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cuerpo,cuantas", [
    ([FILA], 1),
    ({"Result": [FILA]}, 1),
    ({"result": [FILA, FILA]}, 2),
    ({"data": [FILA]}, 1),
    ({"Table": [FILA]}, 1),
    ({}, 0),
    (None, 0),
])
def test_las_filas_se_encuentran_donde_sea_que_vengan(cuerpo, cuantas):
    assert len([f for f in svc.filas_de(cuerpo) if f]) == cuantas


def test_una_fila_de_stock_se_traduce_entera():
    f = svc.mapear_stock(FILA)
    assert f["sku"] == "2H0525345", "el escaneo no lleva espacios ni puntos"
    assert f["descripcion"] == "ARANDELA"
    assert f["unidad"] == "UND"
    assert f["familia"] == "REPUESTOS"
    assert f["cliente"] == "VENTURA", "en mayúsculas: es con lo que se compara"
    assert f["stock"] == 12
    assert f["posicion"] == "A-01-03-2", "nave-calle-columna-nivel, como el WMS"
    assert f["lote"] == "L1"
    assert f["ean"] is None, "/getstock no devuelve código de barras: no inventarlo"


def test_una_fila_sin_codigo_se_salta_sin_romper_la_descarga():
    assert svc.mapear_stock({"DESCRIPCION": "SIN CODIGO"}) is None
    assert svc.mapear_stock({}) is None
    assert svc.mapear_stock("no es una fila") is None


def test_una_posicion_incompleta_no_queda_con_guiones_sueltos():
    f = svc.mapear_stock({**FILA, "COLUMNA": "", "NIVEL": None})
    assert f["posicion"] == "A-01"


# --------------------------------------------------------------------------- #
# Del WMS al espejo local
# --------------------------------------------------------------------------- #
def test_sincronizar_deja_los_productos_en_el_espejo(db):
    from app.models import Producto

    cli, _ = api(lambda p, _: httpx.Response(200, text='{"token":"T"}')
                 if "gettoken" in str(p.url)
                 else httpx.Response(200, json={"Result": [
                     FILA,
                     {**FILA, "COD. PRODUCTO": "1K0145828", "DESCRIPCION": "TUBO"},
                 ]}))
    res = svc.sincronizar_maestro(db, api=cli)
    assert res["productos"] == 2
    assert res["por_cliente"] == {"VENTURA": 2}
    assert db.get(Producto, "2H0525345").descripcion == "ARANDELA"
    assert db.get(Producto, "2H0525345").origen == "API"


def test_el_mismo_sku_en_dos_ubicaciones_es_un_producto_no_dos(db):
    """Una fila de /getstock es una posición. Dos posiciones no son dos piezas."""
    cli, _ = api(lambda p, _: httpx.Response(200, text='{"token":"T"}')
                 if "gettoken" in str(p.url)
                 else httpx.Response(200, json=[FILA, {**FILA, "NIVEL": "3"}]))
    res = svc.sincronizar_maestro(db, api=cli)
    assert res["filas_recibidas"] == 2
    assert res["productos"] == 1


def test_el_recuento_por_cliente_delata_una_credencial_equivocada(db):
    """Con una sola credencial el WMS puede devolver varios clientes."""
    cli, _ = api(lambda p, _: httpx.Response(200, text='{"token":"T"}')
                 if "gettoken" in str(p.url)
                 else httpx.Response(200, json=[
                     FILA,
                     {**FILA, "COD. PRODUCTO": "X1", "COD. CLIENTE": "IMPOFACTOR"},
                 ]))
    res = svc.sincronizar_maestro(db, api=cli)
    assert res["por_cliente"] == {"IMPOFACTOR": 1, "VENTURA": 1}
    assert [c["cliente"] for c in svc.clientes_en_espejo(db)].count("IMPOFACTOR") == 1


def test_se_puede_sincronizar_un_solo_cliente(db):
    cli, _ = api(lambda p, _: httpx.Response(200, text='{"token":"T"}')
                 if "gettoken" in str(p.url)
                 else httpx.Response(200, json=[
                     FILA, {**FILA, "COD. PRODUCTO": "X1", "COD. CLIENTE": "OTRO"}]))
    res = svc.sincronizar_maestro(db, api=cli, cliente="ventura")
    assert res["por_cliente"] == {"VENTURA": 1}


def test_sin_credenciales_lo_dice_y_no_llama_a_nadie(db):
    cli = svc.DepotAPI(base_url=BASE, usuario="", clave="")
    with pytest.raises(svc.DepotNoDisponible) as e:
        svc.sincronizar_maestro(db, api=cli)
    assert "DEPOT_USUARIO" in str(e.value)


def test_sincronizar_dos_veces_no_duplica_ni_pierde_lo_anterior(db):
    from app.models import Producto
    from sqlalchemy import func, select

    def wms(filas):
        return api(lambda p, _: httpx.Response(200, text='{"token":"T"}')
                   if "gettoken" in str(p.url) else httpx.Response(200, json=filas))[0]

    svc.sincronizar_maestro(db, api=wms([FILA]))
    svc.sincronizar_maestro(db, api=wms([{**FILA, "DESCRIPCION": "ARANDELA PLANA"}]))
    assert db.scalar(select(func.count()).select_from(Producto)) == 1
    assert db.get(Producto, "2H0525345").descripcion == "ARANDELA PLANA"


# --------------------------------------------------------------------------- #
# Lo que ve el supervisor
# --------------------------------------------------------------------------- #
def test_el_estado_dice_que_falta_y_nunca_la_clave(db):
    e = svc.estado_integracion(db)
    assert "clave_puesta" in e and isinstance(e["clave_puesta"], bool)
    assert "clave" not in e, "la contraseña del WMS no sale en ninguna respuesta"
    assert "DEPOT_USUARIO" in e["falta"] or e["api_configurada"]


def test_supervisor_no_prueba_ni_ve_configuracion_tecnica(cliente):
    r = cliente.get("/api/catalogo/depot/probar")
    assert r.status_code == 403, r.text
    estado = cliente.get('/api/catalogo/estado').json()
    assert estado['productos_en_cache'] == 0
    assert not {'base_url', 'ruta_token', 'ruta_stock', 'falta', 'clave_puesta'} & estado.keys()


def test_sincronizar_sin_credenciales_responde_503_no_500(cliente):
    r = cliente.post("/api/catalogo/depot/sincronizar")
    assert r.status_code == 503, r.text
    assert "administrador" in r.json()["detail"] and 'DEPOT_USUARIO' not in r.text


def test_los_clientes_del_espejo_se_consultan_por_la_api(cliente):
    r = cliente.get("/api/catalogo/depot/clientes")
    assert r.status_code == 200
    assert r.json() == {"clientes": []}


def test_url_de_endpoint_se_normaliza_como_en_clientes_gs():
    llamadas=[]
    def responder(p):
        llamadas.append(p)
        assert p.url.path == '/q_apidepot/gettoken'
        assert p.headers['userid'] == 'u' and p.headers['password'] == 'c'
        return httpx.Response(200,json={'token':'T'})
    for sufijo in ['/gettoken','/getstock/']:
        cli=svc.DepotAPI(base_url=BASE+sufijo,usuario='u',clave='c',transporte=httpx.MockTransport(responder))
        assert cli.token()=='T'
    assert len(llamadas)==2


def test_redirect_de_ruta_conserva_cabeceras_solo_en_mismo_origen():
    def responder(p, _):
        assert p.headers['userid']=='u' and p.headers['password']=='c'
        if p.url.path.endswith('/gettoken'):
            return httpx.Response(308,headers={'location':'/q_apidepot/gettoken/'})
        return httpx.Response(200,json={'token':'T'})
    cli,llamadas=api(responder)
    assert cli.token()=='T' and len(llamadas)==2


def test_redirect_a_otro_host_no_filtra_credenciales():
    cli,llamadas=api(lambda p,_:httpx.Response(302,headers={'location':'https://otro.example.test/token'}))
    with pytest.raises(svc.DepotNoDisponible):cli.token()
    assert len(llamadas)==1


@pytest.mark.parametrize('respuesta', ['\ufeffTOKEN', '\ufeff"TOKEN"', '\ufeff{"token":"TOKEN"}', '{"token":"\\ufeffTOKEN"}'])
def test_token_con_bom_consulta_stock_con_cabecera_limpia(respuesta):
    def responder(p, _):
        if p.url.path.endswith('/gettoken'):
            return httpx.Response(200, text=respuesta)
        assert p.headers['token'] == 'TOKEN'
        return httpx.Response(200, json=[FILA])
    cli, llamadas = api(responder)
    assert cli.stock()[0]['sku'] == '2H0525345'
    assert len(llamadas) == 2


def test_credencial_unicode_se_envia_sin_500_y_sin_alterar_valor():
    def responder(p):
        assert dict(p.headers.raw)[b'password'] == 'contraseña'.encode('utf-8')
        return httpx.Response(200, json={'token': 'T'})
    cli = svc.DepotAPI(base_url=BASE, usuario='u', clave='contraseña', transporte=httpx.MockTransport(responder))
    assert cli.token() == 'T'
