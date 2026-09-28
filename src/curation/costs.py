"""Curación de costes adicionales y complementarios.

LD14 + LD22 — Detecta costes que no forman parte del precio principal.
"""

from __future__ import annotations

import re

from src.models import CosteAdicional, Programa


PATRONES_COSTES = [
    {
        "keywords": ["transfer", "airport transfer", "traslado"],
        "tipo": "traslado",
        "concepto": "Traslado de aeropuerto",
        "obligatorio": False,
    },
    {
        "keywords": ["insurance", "seguro"],
        "tipo": "seguro",
        "concepto": "Seguro",
        "obligatorio": False,
    },
    {
        "keywords": ["deposit", "damage deposit", "depósito", "deposito"],
        "tipo": "deposito",
        "concepto": "Depósito",
        "obligatorio": False,
    },
    {
        "keywords": ["excursion", "excursión", "extra excursion"],
        "tipo": "excursion",
        "concepto": "Excursión adicional",
        "obligatorio": False,
    },
    {
        "keywords": ["laundry", "lavandería", "lavanderia"],
        "tipo": "lavanderia",
        "concepto": "Lavandería",
        "obligatorio": False,
    },
    {
        "keywords": ["pocket money"],
        "tipo": "pocket_money",
        "concepto": "Dinero de bolsillo recomendado",
        "obligatorio": False,
    },
    {
        "keywords": ["minor", "under 18", "menores"],
        "tipo": "servicio_menores",
        "concepto": "Servicio o suplemento para menores",
        "obligatorio": False,
    },
]


def evaluar_costes_adicionales(programa: Programa) -> Programa:
    """Detecta costes adicionales a partir de campos disponibles.

    Esta primera versión trabaja con texto ya disponible en el objeto Programa.
    Más adelante puede enriquecerse pasando también el texto completo del PDF.
    """

    texto = _texto_programa(programa)

    costes_detectados: list[CosteAdicional] = []

    for patron in PATRONES_COSTES:
        if any(keyword in texto for keyword in patron["keywords"]):
            coste = CosteAdicional(
                concepto=patron["concepto"],
                tipo=patron["tipo"],
                importe=_extraer_importe_cercano(texto, patron["keywords"]),
                moneda=_inferir_moneda(texto),
                obligatorio=_parece_obligatorio(texto),
                incluido_en_precio=_parece_incluido(texto),
                descripcion="Coste detectado automáticamente a partir de la documentación.",
            )
            costes_detectados.append(coste)

    programa.costes_adicionales = _unir_costes(
        programa.costes_adicionales,
        costes_detectados,
    )

    return programa


def _texto_programa(programa: Programa) -> str:
    partes = [
        programa.nombre or "",
        programa.empresa_proveedora or "",
        programa.fuente_documento or "",
        " ".join(programa.documentos_fuente or []),
        programa.razon_obsolescencia or "",
    ]

    for partner in getattr(programa, "partners", []) or []:
        partes.append(partner.nombre)

    for partnership in getattr(programa, "partnerships", []) or []:
        partes.append(partnership.nombre)
        if partnership.descripcion:
            partes.append(partnership.descripcion)

    return " ".join(partes).lower()


def _extraer_importe_cercano(texto: str, keywords: list[str]) -> float | None:
    """Extrae un importe cercano si aparece en el texto disponible.

    En esta versión inicial es conservador: busca cualquier número con moneda
    cerca de las palabras clave.
    """

    for keyword in keywords:
        posicion = texto.find(keyword)

        if posicion == -1:
            continue

        ventana = texto[max(0, posicion - 80): posicion + 120]

        match = re.search(
            r"(€|eur|£|gbp|\$|usd)?\s*(\d+(?:[.,]\d{1,2})?)\s*(€|eur|£|gbp|\$|usd)?",
            ventana,
        )

        if match:
            numero = match.group(2).replace(",", ".")

            try:
                return float(numero)
            except ValueError:
                return None

    return None


def _inferir_moneda(texto: str):
    if "gbp" in texto or "£" in texto:
        return "GBP"
    if "usd" in texto or "$" in texto:
        return "USD"
    if "eur" in texto or "€" in texto:
        return "EUR"
    return None


def _parece_obligatorio(texto: str) -> bool:
    expresiones = [
        "mandatory",
        "compulsory",
        "required",
        "obligatorio",
        "obligatoria",
        "must be paid",
        "not included",
    ]

    return any(expresion in texto for expresion in expresiones)


def _parece_incluido(texto: str) -> bool:
    expresiones = [
        "included",
        "incluido",
        "incluida",
        "included in the price",
        "included in price",
    ]

    return any(expresion in texto for expresion in expresiones)


def _unir_costes(
    existentes: list[CosteAdicional],
    nuevos: list[CosteAdicional],
) -> list[CosteAdicional]:
    resultado = list(existentes or [])
    vistos = {
        (c.concepto.lower(), c.tipo)
        for c in resultado
    }

    for coste in nuevos:
        clave = (coste.concepto.lower(), coste.tipo)

        if clave not in vistos:
            resultado.append(coste)
            vistos.add(clave)

    return resultado