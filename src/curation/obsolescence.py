"""Detección de obsolescencia documental.

Implementa la notificación de caducidad documental. Aplica reglas heurísticas basadas en el año del
documento y en los campos sensibles a obsolescencia para clasificar
cada Programa en uno de tres estados: vigente, parcialmente obsoleto
o obsoleto.
"""

from __future__ import annotations

from datetime import date

from src.models import Programa, EstadoDocumento

# Campos que pierden vigencia al envejecer el documento.
# Estos valores numéricos / temporales caducan rápido.
CAMPOS_SENSIBLES_OBSOLESCENCIA = {
    "precio_semanal_min_eur",
    "precio_semanal_max_eur",
    "fecha_inicio",
    "fecha_fin",
}

# Campos que mantienen vigencia incluso en documentos antiguos.
# La estructura del programa, la ubicación, el idioma, etc. no caducan.
CAMPOS_ESTRUCTURALES = {
    "nombre",
    "empresa_proveedora",
    "pais",
    "ciudad",
    "idioma",
    "edad_min",
    "edad_max",
    "tipo_alojamiento",
    "acreditaciones",
}


def evaluar_obsolescencia(programa: Programa, anyo_actual: int = 2026) -> Programa:
    """Determina el estado de obsolescencia de un Programa.

    Reglas:
    - Si el año del documento coincide con el año actual o posterior,
      el programa se considera vigente.
    - Si el año del documento es anyo_actual - 1, se considera
      parcialmente obsoleto: la información estructural (idioma,
      ubicación, etc.) sigue siendo útil, pero los precios, las
      fechas y los procesos de inscripción están desfasados.
    - Si el año del documento es anyo_actual - 2 o anterior,
      el programa se considera obsoleto en su conjunto.
    - Si no se ha podido identificar el año del documento, se asume
      vigente por defecto (con la precaución correspondiente).

    Args:
        programa: El Programa a evaluar.
        anyo_actual: Año contra el que comparar (por defecto 2026).

    Returns:
        El mismo Programa con los campos de curación rellenados.
    """
    anyo = programa.anyo_documento

    if anyo is None:
        # Sin año identificado, aplicamos el principio de precaución
        # pero sin marcar como obsoleto.
        return programa.model_copy(update={
            "estado_documento": "vigente",
            "razon_obsolescencia": (
                "Año del documento no identificado; "
                "vigencia asumida por defecto."
            ),
        })

    if anyo >= anyo_actual:
        return programa.model_copy(update={
            "estado_documento": "vigente",
            "campos_obsoletos": [],
            "razon_obsolescencia": None,
        })

    if anyo == anyo_actual - 1:
        return programa.model_copy(update={
            "estado_documento": "parcialmente_obsoleto",
            "campos_obsoletos": sorted(CAMPOS_SENSIBLES_OBSOLESCENCIA),
            "razon_obsolescencia": (
                f"Documento de {anyo}. La estructura del programa "
                f"se mantiene, pero los precios, fechas y procesos "
                f"de inscripción están desfasados respecto a la "
                f"campaña {anyo_actual}."
            ),
        })

    return programa.model_copy(update={
        "estado_documento": "obsoleto",
        "campos_obsoletos": sorted(
            CAMPOS_SENSIBLES_OBSOLESCENCIA | CAMPOS_ESTRUCTURALES
        ),
        "razon_obsolescencia": (
            f"Documento de {anyo}, dos o más años anterior a "
            f"{anyo_actual}. Toda la información se considera "
            f"obsoleta y debe revisarse antes de su uso."
        ),
    })


def filtrar_no_obsoletos(programas: list[Programa]) -> list[Programa]:
    """Filtra programas obsoletos del catálogo, conservando los vigentes
    y los parcialmente obsoletos."""
    return [p for p in programas if p.estado_documento != "obsoleto"]