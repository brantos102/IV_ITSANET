from app.services.normalize import (
    a_numero, entero_si_aplica, normalizar_ean, normalizar_pallet, normalizar_sku,
    pallet_padre, pallet_valido, sanear_celda,
)


def test_normalizar_sku_quita_invisibles_y_separadores():
    # El maestro real trae \xa0 delante del producto_id.
    assert normalizar_sku("\xa05C6845202B") == "5C6845202B"
    assert normalizar_sku(" 2h0-525345 ") == "2H0525345"
    assert normalizar_sku("2GY853685B041") == "2GY853685B041"
    assert normalizar_sku(None) == ""


def test_pallets_alfanumericos_y_subpallets():
    assert pallet_valido("A1") and pallet_valido("B04.3") and pallet_valido("A1.1")
    assert not pallet_valido("B 04..3")
    assert not pallet_valido("")
    assert pallet_padre("B04.3") == "B04"
    assert pallet_padre("B04") is None
    assert normalizar_pallet(" b04.1 ") == "B04.1"


def test_sanear_celda_quita_acentos_y_simbolos():
    assert sanear_celda("Descripción ñandú — ok!") == "DESCRIPCION NANDU OK"
    assert sanear_celda("P.N.C. PRODUCTO DOBLADO") == "P.N.C. PRODUCTO DOBLADO"


def test_numeros():
    assert a_numero("1,5") == 1.5
    assert a_numero("") == 0.0
    assert entero_si_aplica(3.0) == 3 and entero_si_aplica(1.5) == 1.5


def test_ean():
    assert normalizar_ean(" 017204364780 ") == "017204364780"
