"""Subsistema de evaluación.

Valida cuantitativamente las hipótesis del TFM:

- H1: precisión de la extracción de información (run_h1).
- H2: calidad del ranking de recomendación (run_h2).
- H3: confianza percibida en las explicaciones (validación cualitativa
  con cuestionario, no automatizable aquí).
"""

from src.evaluation.comparators import (
    Veredicto,
    comparar_campo,
    es_nulo,
)
from src.evaluation.extraction_metrics import (
    ResultadoCampo,
    ResultadoCatalogo,
    evaluar_extraccion,
)
from src.evaluation.ranking_metrics import (
    macro_promedio,
    ndcg_at_k,
    precision_at_k,
)

__all__ = [
    "comparar_campo",
    "es_nulo",
    "Veredicto",
    "evaluar_extraccion",
    "ResultadoCampo",
    "ResultadoCatalogo",
    "precision_at_k",
    "ndcg_at_k",
    "macro_promedio",
]
