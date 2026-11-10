"""El aumento del código conserva las áreas del formato Zebra existente."""
import re
from app.routers.impresion import zpl


def test_barras_y_literal_caben_antes_de_la_descripcion_sin_mover_campos():
    salida = zpl({'sku': '2H0615301D', 'cantidad': 1, 'serie': 'SERIE123'}, 1)
    assert '^FO36,101^BY2,2,78^BCN,78,' in salida
    assert '^FO70,180^A0N,30,27^FB440,' in salida
    assert 101 + 78 < 180 and 180 + 30 < 216
    for coordenada in [(22,22),(22,68),(22,216),(22,241),(22,300),(36,326),
                       (22,367),(534,27),(534,62),(532,139),(662,139),
                       (538,185),(605,226),(667,194),(533,280),(534,318)]:
        assert '^FO%d,%d' % coordenada in salida


def test_literal_largo_se_ajusta_en_su_ancho_sin_recortar_el_codigo():
    sku = '123456789012345678901234567890123456789012'
    salida = zpl({'sku': sku, 'cantidad': 1}, 1)
    ancho = int(re.search(r'\^FO70,180\^A0N,30,(\d+)', salida).group(1))
    assert ancho * len(sku) <= 440
    assert ''.join('\\' + format(b, '02X') for b in sku.encode()) in salida
