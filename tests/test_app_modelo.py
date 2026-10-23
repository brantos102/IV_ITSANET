"""El modelo de la aplicación de los operarios, en el servidor.

Es la migración: lo que lleva meses funcionando contra Firestore, aquí. Estas
pruebas no comprueban que el código corra; comprueban que las cuatro reglas que
no se pueden perder siguen puestas, porque son las que costó descubrir y las que
el cliente nota si se rompen:

1. 22 filas = 22 filas. Lo que llega sin estar en el packing list no añade filas.
2. El reparto por lista. Dos packing lists con el mismo SKU no se mezclan.
3. La clave de idempotencia. Repetir un escaneo no cuenta dos veces.
4. Nada se edita ni se borra. Una anulación es otro evento.
"""
from __future__ import annotations

import pytest

from app.models import AppEvento, AppLinea, AppSku
from app.services import app_modelo as m


# --------------------------------------------------------------------------- #
# Ayudas
# --------------------------------------------------------------------------- #
def packing(lineas, hoja="PACKING", encabezados=None, resumen=None):
    """Lo que el navegador manda después de leer el Excel."""
    por_sku: dict[str, float] = {}
    for l in lineas:
        por_sku[l["sku"]] = por_sku.get(l["sku"], 0) + l["cantidad"]
    return {
        "lineas": lineas,
        "porSku": por_sku,
        "unidades": sum(l["cantidad"] for l in lineas),
        "encabezados": encabezados or ["ITEM", "COD. PRODUCTO", "DESCRIPCION", "CANTIDAD"],
        "columnas": {"sku": 1, "cantidad": 3},
        "hoja": hoja,
        "embarques": ["RB48529"],
        **({"resumen": resumen} if resumen else {}),
    }


LINEAS_22 = [
    {"linea": i, "sku": f"SKU{i:03d}", "descripcion": f"PIEZA {i}", "cantidad": 10}
    for i in range(1, 23)
]


@pytest.fixture()
def rec(db):
    m.crear_recepcion(db, {"codigo": "rec0260002", "cliente": "ventura",
                           "descripcion": "prueba", "bultos": 5}, "sup@itsanet.com")
    return "REC0260002"


def contar(db, codigo, sku, cantidad, pallet="A1-B04-C1", **extra):
    base = {"id": extra.pop("id", f"ev-{sku}-{pallet}-{cantidad}"),
            "sku": sku, "cantidad": cantidad, "pallet": pallet}
    return m.registrar_conteo(db, codigo, "op@itsanet.com", {**base, **extra})


# --------------------------------------------------------------------------- #
# Alta
# --------------------------------------------------------------------------- #
def test_el_codigo_es_el_identificador_y_va_en_mayusculas(db):
    doc = m.crear_recepcion(db, {"codigo": " rec0260003 ", "cliente": "ventura"}, "sup")
    assert doc["id"] == "REC0260003" == doc["codigo"]
    assert doc["cliente"] == "VENTURA"
    assert doc["estado"] == "ABIERTA"


def test_no_se_crean_dos_recepciones_con_el_mismo_codigo(db, rec):
    with pytest.raises(m.ErrorApp) as e:
        m.crear_recepcion(db, {"codigo": rec}, "sup")
    assert e.value.codigo == "DUPLICADA"


def test_una_recepcion_que_no_existe_se_dice_con_su_codigo(db):
    with pytest.raises(m.ErrorApp) as e:
        m.obtener(db, "REC-NADA")
    assert e.value.codigo == "NO_ENCONTRADA"


# --------------------------------------------------------------------------- #
# Regla 1: 22 filas = 22 filas
# --------------------------------------------------------------------------- #
def test_veintidos_filas_entran_como_veintidos_filas(db, rec):
    res = m.guardar_packing_list(db, rec, packing(LINEAS_22))
    assert res["lineas"] == 22
    assert len(m.leer_coleccion(db, rec, "lineas")) == 22


def test_el_orden_del_archivo_se_conserva(db, rec):
    """El informe se devuelve con las filas en su sitio; ordenar por SKU no vale."""
    m.guardar_packing_list(db, rec, packing([
        {"linea": 1, "sku": "ZZZ", "descripcion": "ULTIMA ALFABETICAMENTE", "cantidad": 1},
        {"linea": 2, "sku": "AAA", "descripcion": "PRIMERA", "cantidad": 1},
    ]))
    assert [l["sku"] for l in m.leer_coleccion(db, rec, "lineas")] == ["ZZZ", "AAA"]


def test_un_sku_repetido_en_dos_lineas_sigue_siendo_dos_lineas(db, rec):
    m.guardar_packing_list(db, rec, packing([
        {"linea": 1, "sku": "X1", "descripcion": "PIEZA", "cantidad": 4},
        {"linea": 2, "sku": "X1", "descripcion": "PIEZA", "cantidad": 6},
    ]))
    assert len(m.leer_coleccion(db, rec, "lineas")) == 2
    skus = m.leer_coleccion(db, rec, "skus")
    assert len(skus) == 1, "una pieza, dos filas"
    assert skus[0]["esperado"] == 10, "y lo esperado es la suma"


def test_lo_que_llega_sin_estar_en_la_lista_no_anade_filas(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    contar(db, rec, "SORPRESA", 3, confirmarSobrante=True, descripcion="NO ESTABA")

    assert len(m.leer_coleccion(db, rec, "lineas")) == 22, "22 filas siguen siendo 22"
    adicionales = m.leer_coleccion(db, rec, "adicionales")
    assert [a["sku"] for a in adicionales] == ["SORPRESA"]
    assert adicionales[0]["detectadoPorEmail"] == "op@itsanet.com"


def test_las_columnas_raras_del_archivo_se_guardan_para_devolverlo_igual(db, rec):
    m.guardar_packing_list(db, rec, packing([
        {"linea": 1, "sku": "X1", "descripcion": "PIEZA", "cantidad": 1,
         "NRO. PARTIDA": "P-9", "PESO": 12.5},
    ]))
    linea = m.leer_coleccion(db, rec, "lineas")[0]
    assert linea["NRO. PARTIDA"] == "P-9" and linea["PESO"] == 12.5


def test_la_cabecera_original_queda_guardada_por_lista(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22), origen="PL-A")
    formatos = m.doc_recepcion(m.obtener(db, rec))["formatos"]
    assert "PL-A" in formatos, "la clave conserva el guion del nombre de la lista"
    assert formatos["PL-A"]["encabezados"][1] == "COD. PRODUCTO"


# --------------------------------------------------------------------------- #
# Regla 2: el reparto entre packing lists
# --------------------------------------------------------------------------- #
def test_dos_listas_acumulan_lo_esperado_y_dicen_cuanto_declara_cada_una(db, rec):
    m.guardar_packing_list(db, rec, packing(
        [{"linea": 1, "sku": "COMUN", "descripcion": "PIEZA", "cantidad": 4}]), origen="PL-A")
    res = m.guardar_packing_list(db, rec, packing(
        [{"linea": 1, "sku": "COMUN", "descripcion": "PIEZA", "cantidad": 6}]), origen="PL-B")

    assert res["compartidos"] == ["COMUN"], "quien carga tiene que saber que se comparte"
    s = m.leer_coleccion(db, rec, "skus")[0]
    assert s["esperado"] == 10
    assert s["origenes"] == ["PL-A", "PL-B"]
    assert s["esperadoPorOrigen"] == {"PL-A": 4, "PL-B": 6}


def test_lo_contado_se_imputa_a_la_lista_que_dice_el_operario(db, rec):
    m.guardar_packing_list(db, rec, packing(
        [{"linea": 1, "sku": "COMUN", "descripcion": "P", "cantidad": 4}]), origen="PL-A")
    m.guardar_packing_list(db, rec, packing(
        [{"linea": 1, "sku": "COMUN", "descripcion": "P", "cantidad": 6}]), origen="PL-B")

    contar(db, rec, "COMUN", 4, pallet="A1", origen="PL-A", id="e1")
    contar(db, rec, "COMUN", 6, pallet="A2", origen="PL-B", id="e2")

    s = m.leer_coleccion(db, rec, "skus")[0]
    assert s["contado"] == 10
    assert s["porOrigen"] == {"PL-A": {"A1": 4}, "PL-B": {"A2": 6}}, \
        "repartirlo después sería adivinar"


def test_dos_veces_el_mismo_nombre_de_lista_se_rechaza(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22), origen="PRINCIPAL")
    with pytest.raises(m.ErrorApp) as e:
        m.guardar_packing_list(db, rec, packing(LINEAS_22), origen="principal")
    assert e.value.codigo == "ORIGEN_DUPLICADO"
    assert len(m.leer_coleccion(db, rec, "lineas")) == 22, "y no deja nada a medias"


def test_las_lineas_de_dos_listas_no_se_pisan(db, rec):
    """Dos archivos con una línea 1 cada uno son dos líneas, no una."""
    m.guardar_packing_list(db, rec, packing(
        [{"linea": 1, "sku": "A", "descripcion": "", "cantidad": 1}]), origen="PL-A")
    m.guardar_packing_list(db, rec, packing(
        [{"linea": 1, "sku": "B", "descripcion": "", "cantidad": 1}]), origen="PL-B")
    lineas = m.leer_coleccion(db, rec, "lineas")
    assert len(lineas) == 2
    assert [l["orden"] for l in lineas] == [1, 2], "y la segunda va detrás"


def test_cuantas_lineas_trajo_cada_lista_queda_apuntado(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22), origen="PL-A")
    m.guardar_packing_list(db, rec, packing(LINEAS_22[:5]), origen="PL-B")
    doc = m.doc_recepcion(m.obtener(db, rec))
    assert doc["lineasPorOrigen"] == {"PL-A": 22, "PL-B": 5}
    assert doc["totales"]["lineas"] == 27
    assert doc["totales"]["skus"] == 22, "los 5 de la segunda ya estaban"


# --------------------------------------------------------------------------- #
# Regla 3: la clave de idempotencia
# --------------------------------------------------------------------------- #
def test_repetir_un_escaneo_no_cuenta_dos_veces(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    primero = contar(db, rec, "SKU001", 10, id="mismo")
    segundo = contar(db, rec, "SKU001", 10, id="mismo")

    assert primero["duplicado"] is False and segundo["duplicado"] is True
    assert segundo["contado"] == 10, "la red se cortó después de escribir, no antes"
    assert db.query(AppEvento).filter(AppEvento.recepcion == rec).count() == 1


def test_sin_clave_no_se_cuenta(db, rec):
    """Sin ella no hay forma de distinguir un reintento de un escaneo nuevo."""
    with pytest.raises(m.ErrorApp) as e:
        m.registrar_conteo(db, rec, "op", {"sku": "X1", "cantidad": 1, "pallet": "A1"})
    assert e.value.codigo == "CLAVE_REQUERIDA"


# --------------------------------------------------------------------------- #
# Regla 4: nada se edita ni se borra
# --------------------------------------------------------------------------- #
def test_anular_no_borra_nada_escribe_lo_contrario(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    ev = contar(db, rec, "SKU001", 10, id="e1")["eventoId"]
    res = m.anular_conteo(db, rec, "sup@itsanet.com", ev, "se contó dos veces")

    assert res["contado"] == 0
    assert db.get(AppEvento, ev) is not None, "el original no se toca"
    assert db.query(AppEvento).filter(AppEvento.recepcion == rec).count() == 2
    assert res["estado"] == "FALTANTE", "ya no están, y alguien lo miró"


def test_una_anulacion_necesita_motivo(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    ev = contar(db, rec, "SKU001", 10, id="e1")["eventoId"]
    with pytest.raises(m.ErrorApp) as e:
        m.anular_conteo(db, rec, "sup", ev, "   ")
    assert e.value.codigo == "MOTIVO_REQUERIDO"


def test_lo_mismo_no_se_anula_dos_veces(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    ev = contar(db, rec, "SKU001", 10, id="e1")["eventoId"]
    m.anular_conteo(db, rec, "sup", ev, "motivo")
    with pytest.raises(m.ErrorApp) as e:
        m.anular_conteo(db, rec, "sup", ev, "otra vez")
    assert e.value.codigo == "YA_ANULADO"


def test_el_pallet_vacio_desaparece_del_mapa_al_anular(db, rec):
    """Un pallet a cero no es «pallet con cero unidades»: ahí ya no hay nada."""
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    ev = contar(db, rec, "SKU001", 10, pallet="A1-B04-C1.3", id="e1")["eventoId"]
    s = m.leer_coleccion(db, rec, "skus")
    pallets = next(x for x in s if x["sku"] == "SKU001")["pallets"]
    assert pallets == {"A1-B04-C1~3": 10}, "el punto del subpallet se protege, no se borra"

    m.anular_conteo(db, rec, "sup", ev, "motivo")
    pallets = next(x for x in m.leer_coleccion(db, rec, "skus")
                   if x["sku"] == "SKU001")["pallets"]
    assert pallets == {}


def test_el_agregado_y_el_libro_mayor_no_discrepan(db, rec):
    """El agregado existe por velocidad; la verdad son los eventos."""
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    contar(db, rec, "SKU001", 4, pallet="A1", origen="PRINCIPAL", id="e1")
    contar(db, rec, "SKU001", 6, pallet="A2", origen="PRINCIPAL", id="e2")
    m.anular_conteo(db, rec, "sup", "e2", "mal contado")

    antes = next(x for x in m.leer_coleccion(db, rec, "skus") if x["sku"] == "SKU001")
    despues = m.recalcular_sku(db, rec, "SKU001")
    for campo in ("contado", "pallets", "porOrigen", "estado", "verificado"):
        assert antes[campo] == despues[campo], f"discrepan en {campo}"


# --------------------------------------------------------------------------- #
# El semáforo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("esperado,contado,verificado,estado", [
    (10, 0, False, "PENDIENTE"),
    (10, 0, True, "FALTANTE"),
    (10, 4, True, "FALTANTE"),
    (10, 10, True, "OK"),
    (10, 12, True, "SOBRANTE"),
    (0, 3, True, "ADICIONAL"),
])
def test_el_semaforo_es_el_mismo_que_pinta_la_pantalla(esperado, contado, verificado, estado):
    assert m.estado_de(esperado, contado, verificado) == estado


def test_un_cero_declarado_no_es_lo_mismo_que_no_haber_mirado(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    antes = next(x for x in m.leer_coleccion(db, rec, "skus") if x["sku"] == "SKU001")
    assert antes["estado"] == "PENDIENTE" and antes["verificado"] is False

    m.declarar_no_encontrado(db, rec, "op@itsanet.com",
                             {"id": "cero1", "sku": "SKU001"})
    despues = next(x for x in m.leer_coleccion(db, rec, "skus") if x["sku"] == "SKU001")
    assert despues["estado"] == "FALTANTE", "alguien lo buscó y no estaba"
    assert despues["verificado"] is True


# --------------------------------------------------------------------------- #
# Lo que protege al operario
# --------------------------------------------------------------------------- #
def test_un_sobrante_lo_confirma_el_operario_no_el_servidor(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    with pytest.raises(m.ErrorApp) as e:
        contar(db, rec, "SKU001", 12, id="e1")
    assert e.value.codigo == "CONFIRMAR_SOBRANTE"
    assert "declara 10" in str(e.value)
    assert db.query(AppEvento).filter(AppEvento.recepcion == rec).count() == 0

    r = contar(db, rec, "SKU001", 12, id="e1", confirmarSobrante=True)
    assert r["contado"] == 12 and r["estado"] == "SOBRANTE"


def test_un_codigo_que_no_estaba_avisa_de_que_no_estaba(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    with pytest.raises(m.ErrorApp) as e:
        contar(db, rec, "NOESTA", 1, id="e1")
    assert "no está en el packing list" in str(e.value)


def test_un_ajuste_no_puede_dejar_el_conteo_en_negativo(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    contar(db, rec, "SKU001", 4, id="e1")
    with pytest.raises(m.ErrorApp) as e:
        contar(db, rec, "SKU001", -9, id="e2")
    assert e.value.codigo == "CANTIDAD_INVALIDA"


def test_una_recepcion_cerrada_no_admite_mas_conteos(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    m.cerrar_recepcion(db, rec, "sup@itsanet.com")
    with pytest.raises(m.ErrorApp) as e:
        contar(db, rec, "SKU001", 1, id="e1")
    assert e.value.codigo == "RECEPCION_CERRADA"


def test_contar_pone_la_recepcion_en_validacion(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    assert m.doc_recepcion(m.obtener(db, rec))["estado"] == "ABIERTA"
    contar(db, rec, "SKU001", 1, id="e1")
    assert m.doc_recepcion(m.obtener(db, rec))["estado"] == "EN_VALIDACION"


def test_quien_conto_sale_del_libro_mayor_no_de_una_lista_aparte(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    contar(db, rec, "SKU001", 1, id="e1")
    m.registrar_conteo(db, rec, "otro@itsanet.com",
                       {"id": "e2", "sku": "SKU002", "cantidad": 1, "pallet": "A1"})
    assert sorted(m.operarios_de(db, rec)) == ["op@itsanet.com", "otro@itsanet.com"]


# --------------------------------------------------------------------------- #
# Cierre y reapertura
# --------------------------------------------------------------------------- #
def test_cerrar_y_reabrir_dejan_rastro(db, rec):
    m.guardar_packing_list(db, rec, packing(LINEAS_22))
    m.cerrar_recepcion(db, rec, "sup@itsanet.com")
    m.reabrir_recepcion(db, rec, "admin@itsanet.com", "faltaba un pallet")

    tipos = [e["tipo"] for e in m.leer_coleccion(db, rec, "auditoria")]
    assert "CIERRE" in tipos and "REAPERTURA" in tipos
    assert m.doc_recepcion(m.obtener(db, rec))["estado"] == "EN_VALIDACION"


def test_no_se_cierra_dos_veces(db, rec):
    m.cerrar_recepcion(db, rec, "sup")
    with pytest.raises(m.ErrorApp) as e:
        m.cerrar_recepcion(db, rec, "sup")
    assert e.value.codigo == "YA_CERRADA"


def test_borrar_se_lo_lleva_todo(db, rec):
    m.guardar_packing_list(db, rec, packing(
        LINEAS_22, resumen={"huella": "abc123", "lineas": 22, "skus": 22,
                            "unidades": 220, "archivo": "PL.xlsx"}))
    contar(db, rec, "SKU001", 10, id="e1")

    res = m.borrar_recepcion(db, rec)
    assert res["borrado"]["lineas"] == 22 and res["borrado"]["eventos"] == 1
    assert db.query(AppLinea).count() == 0 and db.query(AppSku).count() == 0
    with pytest.raises(m.ErrorApp):
        m.obtener(db, rec)


# --------------------------------------------------------------------------- #
# Packing lists duplicados
# --------------------------------------------------------------------------- #
def test_un_packing_list_ya_cargado_se_reconoce_por_su_contenido(db, rec):
    resumen = {"huella": "ff00ff00", "lineas": 22, "skus": 22,
               "unidades": 220, "archivo": "PACKING VENTURA.xlsx"}
    m.guardar_packing_list(db, rec, packing(LINEAS_22, resumen=resumen))

    # El mismo archivo, con otro nombre: un duplicado cambia de nombre con un
    # clic; su contenido no.
    hallados = m.packing_lists_parecidos(db, {**resumen, "archivo": "PACKING (2).xlsx"})
    assert len(hallados) == 1
    assert hallados[0]["recepcion"] == rec and hallados[0]["huella"] == "ff00ff00"


def test_la_propia_recepcion_no_se_avisa_a_si_misma(db, rec):
    resumen = {"huella": "ff00ff00", "lineas": 22, "skus": 22, "unidades": 220,
               "archivo": "PL.xlsx"}
    m.guardar_packing_list(db, rec, packing(LINEAS_22, resumen=resumen))
    assert m.packing_lists_parecidos(db, resumen, excluir=rec) == []


def test_un_packing_list_distinto_no_salta(db, rec):
    m.guardar_packing_list(db, rec, packing(
        LINEAS_22, resumen={"huella": "aaaa", "lineas": 22, "skus": 22,
                            "unidades": 220, "archivo": "A.xlsx"}))
    assert m.packing_lists_parecidos(db, {
        "huella": "bbbb", "lineas": 7, "skus": 7, "unidades": 70, "archivo": "B.xlsx"}) == []


# --------------------------------------------------------------------------- #
# Normalización: la misma que el navegador
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("entrada,salida", [
    (" 2h0-525.345 ", "2H0525345"),
    ("6Q0 959 858 9B9", "6Q09598589B9"),
    ("​1K0 145‍828", "1K0145828"),
    (None, ""),
])
def test_normalizar_codigo(entrada, salida):
    assert m.normalizar_codigo(entrada) == salida


@pytest.mark.parametrize("entrada,salida", [
    (" b04 . 1 ", "B04.1"),
    ("a-1", "A-1"),
])
def test_normalizar_pallet_conserva_el_punto_del_subpallet(entrada, salida):
    assert m.normalizar_pallet(entrada) == salida


def test_la_clave_de_una_lista_conserva_su_guion(db):
    """«PL-A» como «PLA» hacía que lo imputado a una lista no se encontrara."""
    assert m.clave_mapa("PL-A") == "PL-A"
    assert m.clave_mapa("v1.2") == "V1~2", "el punto no, que en un mapa es una ruta"
    assert m.clave_pallet("A1-B04-C1.3") == "A1-B04-C1~3"
