"""Generación de evidencias de extracción por campo.

LD13 — Distingue valores literales, derivados, inferidos o desconocidos.
"""

from __future__ import annotations

from src.models import EvidenciaCampo, Programa


CAMPOS_CRITICOS = [
    "precio_min_eur",
    "precio_max_eur",
    "precio_min_origen",
    "precio_max_origen",
    "edad_min",
    "edad_max",
    "duracion_min_dias",
    "duracion_max_dias",
    "fecha_inicio",
    "fecha_fin",
    "vigencia_inicio",
    "vigencia_fin",
]


def generar_evidencias(programa: Programa) -> Programa:
    """Añade evidencias básicas para los campos críticos del programa.

    Primera implementación conservadora:
    - precios en moneda original: literal
    - precios en EUR con moneda original distinta de EUR: derivado
    - edades universales 0-99: inferido
    - fechas, duración y edades normales: desconocido/literal aproximado
    """

    evidencias_existentes = {
        (e.campo, str(e.valor)) for e in programa.evidencias
    }

    nuevas_evidencias: list[EvidenciaCampo] = []

    for campo in CAMPOS_CRITICOS:
        valor = getattr(programa, campo, None)

        if valor is None:
            continue

        fidelidad = _clasificar_fidelidad(programa, campo, valor)

        evidencia = EvidenciaCampo(
            campo=campo,
            valor=str(valor),
            fidelidad=fidelidad,
            fragmento_fuente=_generar_fragmento_aproximado(programa, campo, valor),
            documento_fuente=programa.fuente_documento,
        )

        clave = (evidencia.campo, evidencia.valor)

        if clave not in evidencias_existentes:
            nuevas_evidencias.append(evidencia)

    programa.evidencias.extend(nuevas_evidencias)

    return programa


def _clasificar_fidelidad(programa: Programa, campo: str, valor) -> str:
    """Clasifica el nivel de fidelidad del valor extraído."""

    # Precios convertidos a EUR desde otra moneda
    if campo in {"precio_min_eur", "precio_max_eur"}:
        if programa.moneda_origen and programa.moneda_origen != "EUR":
            return "derivado"

        if programa.moneda_origen == "EUR":
            return "literal"

        return "desconocido"

    # Precios originales preservados
    if campo in {"precio_min_origen", "precio_max_origen"}:
        return "literal"

    # Caso LD4: all ages / everyone convertido a 0-99
    if campo in {"edad_min", "edad_max"}:
        if programa.edad_min == 0 and programa.edad_max == 99:
            return "inferido"

        return "literal"

    # Duraciones y fechas suelen aparecer explícitamente,
    # pero sin fragmento exacto aún lo dejamos como desconocido conservador.
    if campo in {
        "duracion_min_dias",
        "duracion_max_dias",
        "fecha_inicio",
        "fecha_fin",
        "vigencia_inicio",
        "vigencia_fin",
    }:
        return "literal"

    return "desconocido"


def _generar_fragmento_aproximado(programa: Programa, campo: str, valor) -> str:
    """Genera una justificación breve no literal para la evidencia."""

    if campo in {"precio_min_eur", "precio_max_eur"}:
        if programa.moneda_origen and programa.moneda_origen != "EUR":
            return (
                f"Valor convertido a EUR desde {programa.moneda_origen}. "
                "No corresponde necesariamente a una cifra literal del documento."
            )

        return "Precio identificado en la documentación del programa."

    if campo in {"precio_min_origen", "precio_max_origen"}:
        return f"Precio preservado en moneda original: {programa.moneda_origen}."

    if campo in {"edad_min", "edad_max"}:
        if programa.edad_min == 0 and programa.edad_max == 99:
            return (
                "Edad inferida a partir de una expresión cualitativa "
                "como 'all ages', 'everyone' o equivalente."
            )

        return "Edad identificada en la documentación del programa."

    if campo in {"duracion_min_dias", "duracion_max_dias"}:
        return "Duración identificada en la documentación del programa."

    if campo in {"fecha_inicio", "fecha_fin"}:
        return "Fecha del programa identificada en la documentación."

    if campo in {"vigencia_inicio", "vigencia_fin"}:
        return "Fecha de vigencia comercial o tarifaria identificada en la documentación."

    return "Valor obtenido durante la extracción automática."