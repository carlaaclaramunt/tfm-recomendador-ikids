"""Núcleo MCDM del recomendador.

Primera iteración: suma ponderada simple (Weighted Sum Model). Es
suficiente para validar el pipeline completo de punta a punta. La
sustitución por TOPSIS, AHP o BWM se aborda en una iteración posterior,
una vez consolidado el flujo.

La función principal es puntuar_candidatos, que devuelve cada programa
candidato junto con su puntuación global y la descomposición de dicha
puntuación por criterio. Esa descomposición es la base sobre la que se
construye la explicación trazable.
"""

from __future__ import annotations

from src.models import PerfilCliente, Programa, Recomendacion


CRITERIOS = ("precio", "duracion", "ubicacion", "alojamiento", "edad_ajuste")


def puntuar_candidatos(
    perfil: PerfilCliente,
    candidatos: list[Programa],
) -> list[Recomendacion]:
    """Calcula la puntuación MCDM de cada programa candidato.

    Args:
        perfil: Perfil del cliente con sus preferencias y pesos.
        candidatos: Programas que ya han pasado el filtrado duro.

    Returns:
        Lista de recomendaciones ordenadas de mayor a menor puntuación.
    """
    if not candidatos:
        return []

    pesos = _normalizar_pesos(perfil.pesos)

    recomendaciones: list[Recomendacion] = []
    for programa in candidatos:
        descomposicion = _descomponer(perfil, programa, candidatos)
        puntuacion = sum(pesos.get(c, 0.0) * descomposicion[c] for c in CRITERIOS)
        recomendaciones.append(
            Recomendacion(
                programa=programa,
                puntuacion=round(puntuacion, 4),
                descomposicion={c: round(descomposicion[c], 4) for c in CRITERIOS},
            )
        )

    recomendaciones.sort(key=lambda r: r.puntuacion, reverse=True)
    return recomendaciones


# ---------------------------------------------------------------------------
# Cálculo de cada criterio en escala [0, 1] (1 = mejor para el cliente)
# ---------------------------------------------------------------------------


def _descomponer(
    perfil: PerfilCliente,
    programa: Programa,
    todos: list[Programa],
) -> dict[str, float]:
    return {
        "precio": _score_precio(perfil, programa, todos),
        "duracion": _score_duracion(perfil, programa),
        "ubicacion": _score_ubicacion(perfil, programa),
        "alojamiento": _score_alojamiento(perfil, programa),
        "edad_ajuste": _score_edad_ajuste(perfil, programa),
    }


def _score_precio(
    perfil: PerfilCliente,
    programa: Programa,
    todos: list[Programa],
) -> float:
    """Programas más baratos puntúan más alto. Normalizado sobre el rango."""
    precios = [p.precio_eur for p in todos if p.precio_eur is not None]
    if not precios or programa.precio_eur is None:
        return 0.5  # neutro cuando no hay datos suficientes
    pmin, pmax = min(precios), max(precios)
    if pmax == pmin:
        return 1.0
    return 1.0 - (programa.precio_eur - pmin) / (pmax - pmin)


def _score_duracion(perfil: PerfilCliente, programa: Programa) -> float:
    """Penaliza la distancia al punto medio del rango deseado."""
    if programa.duracion_dias is None:
        return 0.5
    if perfil.duracion_min_dias is None and perfil.duracion_max_dias is None:
        return 0.5
    objetivo = _punto_medio(perfil.duracion_min_dias, perfil.duracion_max_dias)
    if objetivo is None:
        return 0.5
    distancia = abs(programa.duracion_dias - objetivo)
    return max(0.0, 1.0 - distancia / max(objetivo, 1))


def _score_ubicacion(perfil: PerfilCliente, programa: Programa) -> float:
    if perfil.pais_preferido is None:
        return 0.5
    return 1.0 if programa.pais.strip().lower() == perfil.pais_preferido.strip().lower() else 0.0


def _score_alojamiento(perfil: PerfilCliente, programa: Programa) -> float:
    if perfil.tipo_alojamiento_preferido is None or programa.tipo_alojamiento is None:
        return 0.5
    return 1.0 if programa.tipo_alojamiento == perfil.tipo_alojamiento_preferido else 0.0


def _score_edad_ajuste(perfil: PerfilCliente, programa: Programa) -> float:
    """Programas cuyo rango de edad encaja mejor con la del estudiante."""
    if programa.edad_min is None or programa.edad_max is None:
        return 0.5
    rango_centro = (programa.edad_min + programa.edad_max) / 2
    rango_amplitud = max(programa.edad_max - programa.edad_min, 1)
    distancia_normalizada = abs(perfil.edad_estudiante - rango_centro) / rango_amplitud
    return max(0.0, 1.0 - distancia_normalizada)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _normalizar_pesos(pesos: dict[str, float]) -> dict[str, float]:
    total = sum(pesos.values())
    if total <= 0:
        return {c: 1.0 / len(CRITERIOS) for c in CRITERIOS}
    return {c: pesos.get(c, 0.0) / total for c in CRITERIOS}


def _punto_medio(a: int | None, b: int | None) -> float | None:
    if a is None and b is None:
        return None
    if a is None:
        return float(b)  # type: ignore[arg-type]
    if b is None:
        return float(a)
    return (a + b) / 2