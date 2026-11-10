"""El aumento del código conserva las áreas del formato Zebra existente."""
import re
import pytest
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


def test_descripcion_aumenta_dentro_del_area_actual_y_respeta_serie():
    salida=zpl({'sku':'5Q0127177C','descripcion':'FILTRO DE COMBUSTIBLE DIESEL','cantidad':1},1)
    assert '^FO22,241^A0N,23,20^FB480,2,' in salida
    assert '^FO22,300' in salida and 241+2*23+2 < 300


@pytest.mark.parametrize('formato,modulo',[('100x50',3),('100x150',4)])
@pytest.mark.parametrize('rotulo',['L11','A01.1','A1000.1000'])
def test_bultos_con_modulo_legible_y_centrado(formato,modulo,rotulo):
    from app.services.etiquetas_bultos import zpl as bultos_zpl
    salida=bultos_zpl([{'rotulo':rotulo}],formato,'PRUEBA','VENTURA','')
    m=re.search(r'\^FO(\d+),(?:220|715)\^BY(\d+),',salida)
    izquierda=int(m[1]);assert int(m[2])==modulo
    modulos=11*(len(rotulo)+2)+13
    assert abs(izquierda+modulos*modulo/2-400)<=.5
    assert izquierda>=10*modulo and 800-izquierda-modulos*modulo>=10*modulo
    assert '^FD'+rotulo+'^FS' in salida
