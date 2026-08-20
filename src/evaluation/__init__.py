"""Subsistema de evaluación.

Valida cuantitativamente las hipótesis del TFM:

- H1: precisión de la extracción de información (este módulo, run_h1).
- H2: calidad del ranking de recomendación (futuro: run_h2).
- H3: confianza percibida en las explicaciones (validación cualitativa
  con cuestionario, no automatizable aquí).
"""

from src.evaluation.comparators import (
    comparar_campo,
    es_nulo,
    Veredicto,
)
from src.evaluation.extraction_metrics import (
    evaluar_extraccion,
    ResultadoCampo,
    ResultadoCatalogo,
)

__all__ = [
    "comparar_campo",
    "es_nulo",
    "Veredicto",
    "evaluar_extraccion",
    "ResultadoCampo",
    "ResultadoCatalogo",
]
