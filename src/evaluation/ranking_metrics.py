"""Métricas de ranking para la evaluación de H2.

Implementa las dos métricas estándar exigidas por el objetivo específico OE3:

    - Precision@k: fracción de los k primeros items del ranking del sistema
      que aparecen en el conjunto relevante (top-5 del baseline manual).

    - nDCG@k (normalized Discounted Cumulative Gain): mide la calidad del
      orden ponderando cada posición por su descuento logarítmico. Se apoya
      en una escala de relevancia graduada [5, 4, 3, 2, 1] para las
      posiciones 1 a 5 del baseline (0 para el resto).

Ambas métricas se computan por perfil y se promedian macro para dar la
métrica global reportable. La comparación estadística sistema vs baseline
se realiza en ``run_h2.py`` con el test de Wilcoxon para rangos con signo.
"""

from __future__ import annotations

import unicodedata
import math
from typing import Iterable


def _normalizar(s: str) -> str:
    """Normalización textual robusta para emparejar nombres de programa."""
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def _mapa_relevancia(baseline_top: list[str]) -> dict[str, int]:
    """De la lista ordenada del baseline devuelve un mapa nombre → relevancia.

    Escala fija: posición 1 → 5, posición 2 → 4, ..., posición 5 → 1.
    """
    mapa = {}
    for idx, nombre in enumerate(baseline_top):
        rel = max(5 - idx, 0)
        mapa[_normalizar(nombre)] = rel
    return mapa


def precision_at_k(sistema_ranking: list[str], baseline_top: list[str], k: int = 5) -> float:
    """Fracción de los top-k del sistema que aparecen en el baseline.

    Args:
        sistema_ranking: lista de nombres de programa devueltos por el sistema, en orden.
        baseline_top: lista de nombres relevantes según el baseline manual.
        k: profundidad del corte.

    Returns:
        Precision@k en [0, 1]. Si el sistema no devuelve nada, 0.
    """
    if k <= 0 or not sistema_ranking:
        return 0.0
    top_sistema = [_normalizar(n) for n in sistema_ranking[:k]]
    relevantes = {_normalizar(n) for n in baseline_top}
    aciertos = sum(1 for n in top_sistema if n in relevantes)
    return aciertos / k


def dcg_at_k(sistema_ranking: list[str], mapa_rel: dict[str, int], k: int) -> float:
    """DCG estándar con la variante 2^rel - 1 en el numerador."""
    dcg = 0.0
    for i, nombre in enumerate(sistema_ranking[:k], start=1):
        rel = mapa_rel.get(_normalizar(nombre), 0)
        if rel > 0:
            dcg += (2**rel - 1) / math.log2(i + 1)
    return dcg


def ndcg_at_k(sistema_ranking: list[str], baseline_top: list[str], k: int = 10) -> float:
    """nDCG@k con relevancia graduada extraída de las posiciones del baseline.

    Args:
        sistema_ranking: ranking del sistema, lista de nombres en orden.
        baseline_top: lista ordenada del baseline manual (posición → relevancia decreciente).
        k: profundidad estándar según OE3 (k=10).

    Returns:
        nDCG@k en [0, 1]. Si el baseline está vacío, 0.
    """
    if not baseline_top:
        return 0.0
    mapa_rel = _mapa_relevancia(baseline_top)
    dcg = dcg_at_k(sistema_ranking, mapa_rel, k)
    # IDCG: ordenación perfecta (el propio baseline)
    idcg = dcg_at_k(baseline_top, mapa_rel, k)
    if idcg == 0:
        return 0.0
    return dcg / idcg


def macro_promedio(valores: Iterable[float]) -> float:
    """Promedio simple de una lista de valores. Devuelve 0 si está vacía."""
    valores = list(valores)
    if not valores:
        return 0.0
    return sum(valores) / len(valores)
