"""Filtros duros del recomendador basado en conocimiento.

Aplican las restricciones que un programa DEBE cumplir para ser
considerado un candidato válido. Estas restricciones constituyen la base
de conocimiento del dominio (recomendador basado en conocimiento, según
la taxonomía de Burke).
"""

from __future__ import annotations

from src.models import PerfilCliente, Programa


def filtrar_candidatos(
    perfil: PerfilCliente,
    programas: list[Programa],
) -> list[Programa]:
    """Devuelve los programas que satisfacen las restricciones duras del cliente.

    Las restricciones duras actuales son:

    - El idioma del programa debe coincidir con el deseado.
    - La edad del estudiante debe estar dentro del rango admitido por el programa
      (si el programa especifica rangos de edad).
    - El precio no debe superar el presupuesto máximo (si se ha indicado).
    - La duración debe estar en el rango deseado (si se ha indicado).
    - Si se ha indicado país preferido, el programa debe coincidir.
    """
    return [p for p in programas if _cumple_restricciones(perfil, p)]


def _cumple_restricciones(perfil: PerfilCliente, programa: Programa) -> bool:
    if programa.idioma != perfil.idioma_deseado:
        return False

    if not _edad_compatible(perfil, programa):
        return False

    # Los precios están normalizados a €/semana. Para comparar contra el
    # presupuesto TOTAL del cliente hay que multiplicar por las semanas
    # que va a pasar. Usamos la duración MÍNIMA que aceptaría el cliente
    # (equivalente al total más barato que podría acabar pagando en este
    # programa). Si eso ya supera el presupuesto, descartamos.
    if (
        perfil.presupuesto_max_eur is not None
        and programa.precio_semanal_min_eur is not None
    ):
        semanas_cliente_min = _semanas_minimas_cliente(perfil, programa)
        total_min = programa.precio_semanal_min_eur * semanas_cliente_min
        if total_min > perfil.presupuesto_max_eur:
            return False

    if not _duracion_compatible(perfil, programa):
        return False

    if (
        perfil.pais_preferido is not None
        and programa.pais.strip().lower() != perfil.pais_preferido.strip().lower()
    ):
        return False

    return True


def _semanas_minimas_cliente(perfil: PerfilCliente, programa: Programa) -> float:
    """Semanas mínimas que el cliente pasaría en este programa.

    Es el mayor entre lo mínimo que quiere el cliente y lo mínimo que
    permite el programa (ambos en días, convertidos a semanas). Si no hay
    información se asume 1 semana (la unidad más barata razonable).
    """
    cli_dias = perfil.duracion_min_dias or 7
    prog_dias = programa.duracion_min_dias or cli_dias
    dias = max(cli_dias, prog_dias)
    return max(1.0, dias / 7)


def _edad_compatible(perfil: PerfilCliente, programa: Programa) -> bool:
    edad = perfil.edad_estudiante
    if programa.edad_min is not None and edad < programa.edad_min:
        return False
    if programa.edad_max is not None and edad > programa.edad_max:
        return False
    return True


def _duracion_compatible(perfil: PerfilCliente, programa: Programa) -> bool:
    """Comprueba si el rango de duración del programa se solapa con el rango
    deseado por el cliente. Se considera compatible si ambos rangos
    intersectan al menos en un día.
    """
    prog_min = programa.duracion_min_dias
    prog_max = programa.duracion_max_dias

    # Sin información del programa: no filtramos por falta de datos
    if prog_min is None and prog_max is None:
        return True

    # Sin restricción del cliente: no filtramos
    if perfil.duracion_min_dias is None and perfil.duracion_max_dias is None:
        return True

    # Rellenar nulls como cotas abiertas, no como "= al otro extremo":
    # prog_min=None → 1 (desde el principio); prog_max=None → 365 (sin límite).
    # Trata "Minimum 1 week" (7, None) como un curso abierto [7, 365], no como
    # un curso fijo de 7 días.
    prog_min = prog_min if prog_min is not None else 1
    prog_max = prog_max if prog_max is not None else 365
    cli_min = perfil.duracion_min_dias if perfil.duracion_min_dias is not None else 1
    cli_max = perfil.duracion_max_dias if perfil.duracion_max_dias is not None else 365

    # Hay solapamiento si los rangos intersectan
    return prog_min <= cli_max and prog_max >= cli_min