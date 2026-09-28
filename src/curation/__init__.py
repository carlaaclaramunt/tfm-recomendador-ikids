"""Subsistema de curación documental y trazabilidad."""

from src.curation.obsolescence import evaluar_obsolescencia
from src.curation.merge import fusionar_programas, resumen_fusion
from src.curation.origin import evaluar_origen_documental, evaluar_partnerships
from src.curation.evidence import (
    generar_evidencias,
    tasa_trazabilidad_literal,
    verificar_evidencias,
)

__all__ = [
    "evaluar_obsolescencia",
    "fusionar_programas",
    "resumen_fusion",
    "evaluar_origen_documental",
    "evaluar_partnerships",
    "generar_evidencias",
    "verificar_evidencias",
    "tasa_trazabilidad_literal",
]
