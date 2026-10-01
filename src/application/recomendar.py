"""Caso de uso: recomendar programas para un perfil de cliente.

Orquesta los subsistemas de recomendación y explicación:

    perfil + catálogo
        → filtrado por restricciones duras
        → puntuación MCDM ponderada
        → generación de explicación en lenguaje natural por candidato
        → top-k recomendaciones
"""

from __future__ import annotations

from src.explanation import explicar
from src.models import PerfilCliente, Programa, Recomendacion
from src.recommendation import filtrar_candidatos, puntuar_candidatos


def recomendar(
    perfil: PerfilCliente,
    programas: list[Programa],
    top_k: int = 5,
) -> list[Recomendacion]:
    """Genera las top-k recomendaciones para un perfil dado."""
    candidatos = filtrar_candidatos(perfil, programas)
    print(
        f"Tras el filtrado: {len(candidatos)} candidatos de {len(programas)} programas"
    )

    # Pasamos el catálogo completo como referencia estable para la
    # normalización min-max del precio (C3): la puntuación de un programa
    # no debe depender del subconjunto de rivales que sobrevivió al filtro.
    recomendaciones = puntuar_candidatos(perfil, candidatos, catalogo=programas)
    for r in recomendaciones:
        r.explicacion = explicar(r, perfil)

    return recomendaciones[:top_k]
