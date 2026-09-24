"""Tests para las métricas de ranking usadas en H2."""

from src.evaluation.ranking_metrics import (
    ndcg_at_k,
    precision_at_k,
    macro_promedio,
)


def test_precision_at_5_perfecto():
    baseline = ["A", "B", "C", "D", "E"]
    assert precision_at_k(baseline, baseline, 5) == 1.0


def test_precision_at_5_ninguno_relevante():
    baseline = ["A", "B", "C", "D", "E"]
    sistema = ["X", "Y", "Z", "W", "V"]
    assert precision_at_k(sistema, baseline, 5) == 0.0


def test_precision_at_5_parcial():
    baseline = ["A", "B", "C", "D", "E"]
    sistema = ["A", "X", "C", "Y", "E"]  # 3 de 5 en top5
    assert precision_at_k(sistema, baseline, 5) == 0.6


def test_precision_normaliza_acentos_y_mayusculas():
    baseline = ["General English"]
    sistema = ["GENERAL english"]
    assert precision_at_k(sistema, baseline, 1) == 1.0


def test_precision_k_mayor_que_ranking():
    baseline = ["A", "B", "C"]
    sistema = ["A"]
    # Solo tenemos 1 candidato, evaluamos top5 → 1 acierto de 5 slots
    assert precision_at_k(sistema, baseline, 5) == 0.2


def test_ndcg_perfecto_es_uno():
    baseline = ["A", "B", "C", "D", "E"]
    assert ndcg_at_k(baseline, baseline, 10) == 1.0


def test_ndcg_reverso_menor_que_perfecto():
    baseline = ["A", "B", "C", "D", "E"]
    sistema_reverso = ["E", "D", "C", "B", "A"]
    ndcg = ndcg_at_k(sistema_reverso, baseline, 10)
    assert 0.4 < ndcg < 0.7  # todos presentes pero mal ordenados


def test_ndcg_baseline_vacio_es_cero():
    assert ndcg_at_k(["A", "B"], [], 10) == 0.0


def test_ndcg_ninguno_relevante_es_cero():
    baseline = ["A", "B", "C"]
    sistema = ["X", "Y", "Z"]
    assert ndcg_at_k(sistema, baseline, 10) == 0.0


def test_ndcg_pondera_posicion():
    baseline = ["A", "B", "C", "D", "E"]
    # Sistema pone A en posición 1 (mejor caso para A)
    ndcg_alto = ndcg_at_k(["A"], baseline, 10)
    # Sistema pone A en posición 5 (peor caso para A dentro del top5)
    ndcg_bajo = ndcg_at_k(["X", "X", "X", "X", "A"], baseline, 10)
    assert ndcg_alto > ndcg_bajo


def test_macro_promedio_lista_vacia_es_cero():
    assert macro_promedio([]) == 0.0


def test_macro_promedio_valores():
    assert macro_promedio([0.4, 0.6, 1.0]) == (0.4 + 0.6 + 1.0) / 3
