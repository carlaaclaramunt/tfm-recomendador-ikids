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


CRITERIOS = ("precio", "duracion", "ubicacion", "alojamiento", "edad_ajuste", "afinidad")


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
        "afinidad": _score_afinidad(perfil, programa),
    }


def _score_precio(
        perfil: PerfilCliente,
        programa: Programa,
        todos: list[Programa],
) -> float:
    """Programas más baratos puntúan más alto, normalizado sobre el catálogo.

    Usa precio_semanal_min_eur como referencia (la opción más barata del programa).
    Si el programa no tiene precio extraído, score neutro (0.5).
    """
    # Sin datos del programa: neutro
    if programa.precio_semanal_min_eur is None:
        return 0.5

    # Normalizamos sobre el rango de precios mínimos del catálogo entero
    precios_min = [p.precio_semanal_min_eur for p in todos if p.precio_semanal_min_eur is not None]
    if not precios_min:
        return 0.5

    pmin, pmax = min(precios_min), max(precios_min)
    if pmax == pmin:
        return 1.0

    # Más barato = mejor
    return 1.0 - (programa.precio_semanal_min_eur - pmin) / (pmax - pmin)


def _score_duracion(perfil: PerfilCliente, programa: Programa) -> float:
    """Score por solapamiento entre el rango de duración del programa y el del cliente.

    La pregunta que se responde es: ¿este programa permite al cliente
    elegir una duración dentro de su rango deseado? Cuanto mayor es el
    solapamiento con el rango del cliente, mejor.

    - 1.0 → el programa cubre todo el rango deseado por el cliente
    - 0.7 → el programa permite alguna duración deseada (match mínimo)
    - 0.0 → el programa no ofrece ninguna duración aceptable
    """
    prog_min = programa.duracion_min_dias
    prog_max = programa.duracion_max_dias
    cli_min = perfil.duracion_min_dias
    cli_max = perfil.duracion_max_dias

    # Sin información en alguno de los lados: score neutro
    if prog_min is None and prog_max is None:
        return 0.5
    if cli_min is None and cli_max is None:
        return 0.5

    # Rellenar nulls como cotas abiertas, coherente con _duracion_compatible:
    # prog_min=None → 1; prog_max=None → 365 (curso abierto, no fijo).
    prog_min = prog_min if prog_min is not None else 1
    prog_max = prog_max if prog_max is not None else 365
    cli_min = cli_min if cli_min is not None else 1
    cli_max = cli_max if cli_max is not None else 365

    # Solapamiento entre rangos
    overlap_min = max(prog_min, cli_min)
    overlap_max = min(prog_max, cli_max)

    if overlap_min > overlap_max:
        return 0.0  # rangos disjuntos: el programa no puede satisfacer al cliente

    # Hay solapamiento → score base alto + bonus proporcional a cuánto del
    # rango del cliente queda cubierto por el programa
    overlap_size = overlap_max - overlap_min + 1
    cli_size = max(cli_max - cli_min + 1, 1)
    cobertura_cliente = min(1.0, overlap_size / cli_size)

    return 0.7 + 0.3 * cobertura_cliente


def _score_ubicacion(perfil: PerfilCliente, programa: Programa) -> float:
    if perfil.pais_preferido is None:
        return 0.5
    return 1.0 if programa.pais.strip().lower() == perfil.pais_preferido.strip().lower() else 0.0


def _score_alojamiento(perfil: PerfilCliente, programa: Programa) -> float:
    if perfil.tipo_alojamiento_preferido is None or not programa.tipo_alojamiento:
        return 0.5
    return 1.0 if perfil.tipo_alojamiento_preferido in programa.tipo_alojamiento else 0.0


def _score_edad_ajuste(perfil: PerfilCliente, programa: Programa) -> float:
    """Programas cuyo rango de edad encaja mejor con la del estudiante."""
    if programa.edad_min is None or programa.edad_max is None:
        return 0.5
    rango_centro = (programa.edad_min + programa.edad_max) / 2
    rango_amplitud = max(programa.edad_max - programa.edad_min, 1)
    distancia_normalizada = abs(perfil.edad_estudiante - rango_centro) / rango_amplitud
    return max(0.0, 1.0 - distancia_normalizada)


def _score_afinidad(perfil: PerfilCliente, programa: Programa) -> float:
    """Score de afinidad tematica entre el perfil y el programa.

    Compara los keywords declarados en ``perfil.intereses`` contra el texto
    combinado del programa (nombre + partnerships + cursos especialistas +
    acreditaciones). Cada match aporta relevancia adicional.

    - Sin intereses declarados: score neutro (0.5), no penaliza ni bonifica.
    - Con intereses y al menos un match: 0.75 (1 match) o 1.0 (2+ matches).
    - Con intereses y ningun match: 0.0 (no encaja tematicamente).

    Esta funcion introduce el criterio LDX (afinidad tematica) motivado por
    los perfiles temaicos (adolescente deportivo, senior 50+, docente CLIL,
    preparacion de examenes oficiales) donde los cinco criterios genericos
    no capturaban la relevancia semantica del programa para el segmento.
    """
    if not perfil.intereses:
        return 0.5

    partes = [programa.nombre or ""]
    for pt in getattr(programa, "partnerships", []) or []:
        partes.append(getattr(pt, "nombre", "") or "")
        partes.append(getattr(pt, "descripcion", "") or "")
    for ce in getattr(programa, "cursos_especialistas", []) or []:
        partes.append(getattr(ce, "nombre", "") or "")
        partes.append(getattr(ce, "actividad", "") or "")
    for acr in getattr(programa, "acreditaciones", []) or []:
        partes.append(acr)

    texto = " ".join(partes).lower()

    hits = sum(1 for interes in perfil.intereses if interes.lower() in texto)
    if hits == 0:
        return 0.0
    return min(1.0, 0.5 + 0.25 * hits)


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