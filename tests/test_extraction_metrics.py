"""Tests de las métricas agregadas (precision/recall/F1 + macro)."""

from src.evaluation.extraction_metrics import evaluar_extraccion


def _gt_minimo():
    return {
        "version": "test",
        "campos_evaluados": ["pais", "precio_semanal_min_eur"],
        "programas": [
            {
                "id": "p1",
                "pdf": "test.pdf",
                "match_nombre": "Alpha",
                "campos": {
                    "pais": {"esperado": "Malta"},
                    "precio_semanal_min_eur": {"esperado": 300},
                },
            },
            {
                "id": "p2",
                "pdf": "otro.pdf",
                "match_nombre": "Beta",
                "campos": {
                    "pais": {"esperado": "Irlanda"},
                    "precio_semanal_min_eur": {"esperado": None, "ausente_doc": True},
                },
            },
        ],
    }


def test_extraccion_perfecta_da_macro_1_0():
    gt = _gt_minimo()
    programas = [
        {"nombre": "Alpha", "fuente_documento": "test.pdf", "pais": "Malta", "precio_semanal_min_eur": 300},
        {"nombre": "Beta", "fuente_documento": "otro.pdf", "pais": "Irlanda", "precio_semanal_min_eur": None},
    ]
    res = evaluar_extraccion(gt, programas)
    assert res.macro_f1 == 1.0
    assert res.n_programas_emparejados == 2


def test_un_fp_baja_precision_de_su_campo():
    gt = _gt_minimo()
    programas = [
        {"nombre": "Alpha", "fuente_documento": "test.pdf", "pais": "Italia", "precio_semanal_min_eur": 300},
        {"nombre": "Beta", "fuente_documento": "otro.pdf", "pais": "Irlanda", "precio_semanal_min_eur": None},
    ]
    res = evaluar_extraccion(gt, programas)
    assert res.por_campo["pais"].fp == 1
    assert res.por_campo["pais"].tp == 1
    assert res.por_campo["pais"].precision == 0.5


def test_programa_sin_match_se_marca_y_cuenta_como_fn():
    gt = _gt_minimo()
    programas = [
        {"nombre": "Alpha", "fuente_documento": "test.pdf", "pais": "Malta", "precio_semanal_min_eur": 300}
    ]
    res = evaluar_extraccion(gt, programas)
    assert "p2" in res.programas_sin_match
    assert res.por_campo["pais"].fn == 1


def test_campo_sin_positivos_se_excluye_del_macro():
    # GT con un único campo siempre-nulo no debe contar para macro
    gt = {
        "version": "test",
        "campos_evaluados": ["pais", "fecha_fin"],
        "programas": [
            {
                "id": "p1",
                "pdf": "test.pdf",
                "match_nombre": "Alpha",
                "campos": {
                    "pais": {"esperado": "Malta"},
                    "fecha_fin": {"esperado": None, "ausente_doc": True},
                },
            },
        ],
    }
    programas = [
        {"nombre": "Alpha", "fuente_documento": "test.pdf", "pais": "Malta", "fecha_fin": None}
    ]
    res = evaluar_extraccion(gt, programas)
    # fecha_fin tiene solo un TN → no entra al macro
    assert res.por_campo["fecha_fin"].tn == 1
    assert res.macro_f1 == 1.0
