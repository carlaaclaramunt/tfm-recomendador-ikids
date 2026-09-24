"""Tests para el comparador list_of_costs (LD14)."""

from src.evaluation.comparators import Veredicto, comparar_campo


def _coste(concepto, tipo, importe=None, moneda="EUR", obligatorio=False):
    return {
        "concepto": concepto, "tipo": tipo, "importe": importe,
        "moneda": moneda, "obligatorio": obligatorio,
        "incluido_en_precio": False, "descripcion": None,
    }


def test_dos_listas_vacias_es_tn():
    c = comparar_campo("costes_adicionales", [], [])
    assert c.veredicto == Veredicto.TN


def test_gt_vacio_extraido_con_costes_es_fp():
    extraido = [_coste("Airport transfer", "traslado", 25)]
    c = comparar_campo("costes_adicionales", [], extraido)
    assert c.veredicto == Veredicto.FP


def test_gt_con_costes_extraido_vacio_es_fn():
    esperado = [_coste("Airport transfer", "traslado", 25)]
    c = comparar_campo("costes_adicionales", esperado, [])
    assert c.veredicto == Veredicto.FN


def test_match_perfecto_es_tp():
    esperado = [
        _coste("Airport transfer", "traslado", 25),
        _coste("Insurance", "seguro", 14),
    ]
    extraido = [
        _coste("Insurance", "seguro", 14),
        _coste("Airport transfer", "traslado", 25),  # orden distinto
    ]
    c = comparar_campo("costes_adicionales", esperado, extraido)
    assert c.veredicto == Veredicto.TP


def test_falta_coste_es_fp():
    esperado = [
        _coste("Airport transfer", "traslado", 25),
        _coste("Insurance", "seguro", 14),
    ]
    extraido = [_coste("Airport transfer", "traslado", 25)]
    c = comparar_campo("costes_adicionales", esperado, extraido)
    assert c.veredicto == Veredicto.FP
    assert "faltantes" in c.detalle


def test_coste_de_mas_es_fp():
    esperado = [_coste("Airport transfer", "traslado", 25)]
    extraido = [
        _coste("Airport transfer", "traslado", 25),
        _coste("Pocket money", "pocket_money", 30),
    ]
    c = comparar_campo("costes_adicionales", esperado, extraido)
    assert c.veredicto == Veredicto.FP
    assert "sobrantes" in c.detalle


def test_importe_dentro_de_tolerancia_5pct():
    esperado = [_coste("Airport transfer", "traslado", 25)]
    extraido = [_coste("Airport transfer", "traslado", 26)]  # 4% de diferencia
    c = comparar_campo("costes_adicionales", esperado, extraido)
    assert c.veredicto == Veredicto.TP


def test_importe_fuera_de_tolerancia_es_fp():
    esperado = [_coste("Airport transfer", "traslado", 25)]
    extraido = [_coste("Airport transfer", "traslado", 40)]  # 60% de diferencia
    c = comparar_campo("costes_adicionales", esperado, extraido)
    assert c.veredicto == Veredicto.FP
    assert "fuera de tolerancia" in c.detalle


def test_normaliza_case_y_acentos_en_concepto():
    esperado = [_coste("Traslado privado", "traslado", 25)]
    extraido = [_coste("TRASLADO Privado", "traslado", 25)]
    c = comparar_campo("costes_adicionales", esperado, extraido)
    assert c.veredicto == Veredicto.TP


def test_importe_none_en_ambos_lados_matchea():
    esperado = [_coste("Pocket money", "pocket_money", None)]
    extraido = [_coste("Pocket money", "pocket_money", None)]
    c = comparar_campo("costes_adicionales", esperado, extraido)
    assert c.veredicto == Veredicto.TP


def test_importe_none_vs_valor_no_matchea():
    esperado = [_coste("Pocket money", "pocket_money", None)]
    extraido = [_coste("Pocket money", "pocket_money", 30)]
    c = comparar_campo("costes_adicionales", esperado, extraido)
    assert c.veredicto == Veredicto.FP


def test_diferente_tipo_es_coste_distinto():
    esperado = [_coste("Insurance", "seguro", 14)]
    extraido = [_coste("Insurance", "otro", 14)]  # mismo concepto, tipo distinto
    c = comparar_campo("costes_adicionales", esperado, extraido)
    assert c.veredicto == Veredicto.FP
