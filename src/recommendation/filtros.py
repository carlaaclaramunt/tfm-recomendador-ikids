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

    if (
        perfil.presupuesto_max_eur is not None
        and programa.precio_eur is not None
        and programa.precio_eur > perfil.presupuesto_max_eur
    ):
        return False

    if not _duracion_compatible(perfil, programa):
        return False

    if (
        perfil.pais_preferido is not None
        and programa.pais.strip().lower() != perfil.pais_preferido.strip().lower()
    ):
        return False

    return True


def _edad_compatible(perfil: PerfilCliente, programa: Programa) -> bool:
    edad = perfil.edad_estudiante
    if programa.edad_min is not None and edad < programa.edad_min:
        return False
    if programa.edad_max is not None and edad > programa.edad_max:
        return False
    return True


def _duracion_compatible(perfil: PerfilCliente, programa: Programa) -> bool:
    if programa.duracion_dias is None:
        return True
    if (
        perfil.duracion_min_dias is not None
        and programa.duracion_dias < perfil.duracion_min_dias
    ):
        return False
    if (
        perfil.duracion_max_dias is not None
        and programa.duracion_dias > perfil.duracion_max_dias
    ):
        return False
    return True