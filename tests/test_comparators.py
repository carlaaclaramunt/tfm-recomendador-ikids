"""Tests para los comparadores campo a campo."""

from src.evaluation.comparators import Veredicto, comparar_campo, es_nulo


def test_es_nulo_detecta_listas_vacias_y_strings_vacios():
    assert es_nulo(None)
    assert es_nulo([])
    assert es_nulo("")
    assert not es_nulo(0)
    assert not es_nulo("x")
    assert not es_nulo(["x"])


def test_tn_cuando_ambos_son_nulos():
    c = comparar_campo("precio_semanal_min_eur", None, None)
    assert c.veredicto == Veredicto.TN


def test_fp_cuando_gt_nulo_y_extraido_no():
    c = comparar_campo("precio_semanal_min_eur", None, 100)
    assert c.veredicto == Veredicto.FP


def test_fn_cuando_gt_tiene_valor_y_extraido_nulo():
    c = comparar_campo("precio_semanal_min_eur", 100, None)
    assert c.veredicto == Veredicto.FN


def test_tp_numerico_dentro_de_tolerancia_5pct():
    # 100 vs 104 = 4% < 5% → TP
    assert comparar_campo("precio_semanal_min_eur", 100, 104).veredicto == Veredicto.TP


def test_fp_numerico_fuera_de_tolerancia_5pct():
    # 100 vs 110 = ~9% > 5% → FP
    assert comparar_campo("precio_semanal_min_eur", 100, 110).veredicto == Veredicto.FP


def test_tolerancia_cubre_conversion_gbp_eur_aproximada():
    # £2940 × 1.17 = 3439.8; extracción real 3440 o 3441 → TP
    assert comparar_campo("precio_semanal_min_eur", 3441, 3440).veredicto == Veredicto.TP


def test_numerico_exacto_para_duracion():
    assert comparar_campo("duracion_min_dias", 7, 7).veredicto == Veredicto.TP
    # duracion no tiene tolerancia: 14 vs 15 → FP
    assert comparar_campo("duracion_min_dias", 14, 15).veredicto == Veredicto.FP


def test_string_loose_tolera_variaciones_de_nombre():
    # "St. Julians" vs "St Julians" → similitud alta → TP
    c = comparar_campo("ciudad", "St. Julians", "St Julians")
    assert c.veredicto == Veredicto.TP


def test_enum_exact_es_estricto():
    assert comparar_campo("idioma", "inglés", "inglés").veredicto == Veredicto.TP
    assert comparar_campo("idioma", "inglés", "english").veredicto == Veredicto.FP


def test_set_strings_compara_alojamiento_como_conjunto():
    assert comparar_campo(
        "tipo_alojamiento", ["familia", "hotel"], ["hotel", "familia"]
    ).veredicto == Veredicto.TP
    assert comparar_campo(
        "tipo_alojamiento", ["familia"], ["familia", "hotel"]
    ).veredicto == Veredicto.FP


def test_nombre_acepta_extraccion_mas_especifica():
    # extracción enriquecida con la variante/campaña → TP
    assert comparar_campo(
        "nombre", "NSX at Woodbridge School",
        "NSX at Woodbridge School - English+ Horse Riding",
    ).veredicto == Veredicto.TP
    assert comparar_campo(
        "nombre", "Millfield School", "Millfield School Summer Programme",
    ).veredicto == Veredicto.TP


def test_nombre_rechaza_extraccion_mas_generica():
    # extractor pierde información → FP (asimetría)
    assert comparar_campo(
        "nombre", "NSX at Woodbridge School - English+ Horse Riding",
        "NSX at Woodbridge School",
    ).veredicto == Veredicto.FP


def test_fechas_iso_exactas():
    assert comparar_campo("fecha_inicio", "2026-06-29", "2026-06-29").veredicto == Veredicto.TP
    assert comparar_campo("fecha_inicio", "2026-06-29", "2026-06-30").veredicto == Veredicto.FP
