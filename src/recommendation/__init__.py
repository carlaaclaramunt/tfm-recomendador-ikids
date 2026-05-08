"""Subsistema de recomendación: filtros + MCDM."""

from src.recommendation.filtros import filtrar_candidatos
from src.recommendation.mcdm import puntuar_candidatos

__all__ = ["filtrar_candidatos", "puntuar_candidatos"]