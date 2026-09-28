"""Clasificación del origen documental y detección de programas colaborativos."""

from __future__ import annotations

from src.models import Partner, Partnership, Programa

IKIDS_KEYWORDS = [
    "ikids",
    "i-kids",
    "i kids",
]

PARTNER_KEYWORDS = [
    "in partnership with",
    "partner",
    "collaboration",
    "powered by",
    "with future learning",
    "future learning",
    "dbs",
    "sports",
]


def evaluar_origen_documental(programa: Programa) -> Programa:
    """Clasifica el origen del documento y detecta colaboraciones simples.

    Es una primera versión heurística pensada para documentar LD11/LD12.
    """

    texto = " ".join(
        [
            programa.nombre or "",
            programa.empresa_proveedora or "",
            programa.fuente_documento or "",
            " ".join(programa.documentos_fuente or []),
        ]
    ).lower()

    contiene_ikids = any(keyword in texto for keyword in IKIDS_KEYWORDS)
    contiene_partner = any(keyword in texto for keyword in PARTNER_KEYWORDS)

    if contiene_ikids and contiene_partner:
        programa.origen_documento = "mixto"
        programa.es_programa_colaborativo = True

    elif contiene_ikids:
        programa.origen_documento = "ikids_propio"

    elif programa.origen_documento == "desconocido":
        programa.origen_documento = "proveedor_externo"

    # Caso específico detectado: DBS Dublin
    if "dbs" in texto or "dublin elite soccer" in texto:
        programa.es_programa_colaborativo = True
        programa.origen_documento = "mixto"

        partners_detectados = [
            Partner(nombre="I-KIDS", rol="intermediario"),
            Partner(nombre="DBS Sports", rol="actividades"),
            Partner(nombre="Future Learning", rol="escuela"),
        ]

        existentes = {p.nombre.lower() for p in programa.partners}

        for partner in partners_detectados:
            if partner.nombre.lower() not in existentes:
                programa.partners.append(partner)

    return programa

def evaluar_partnerships(programa: Programa) -> Programa:
    """Detecta colaboraciones de marca relevantes a partir de texto disponible."""

    texto = " ".join(
        [
            programa.nombre or "",
            programa.empresa_proveedora or "",
            programa.fuente_documento or "",
            " ".join(programa.documentos_fuente or []),
        ]
    ).lower()

    partnerships_detectados = []

    if "jamie murray" in texto:
        partnerships_detectados.append(
            Partnership(
                nombre="Jamie Murray",
                descripcion="Colaboración o referencia deportiva asociada al programa"
            )
        )

    if "fifa" in texto:
        partnerships_detectados.append(
            Partnership(
                nombre="FIFA",
                descripcion="Colaboración o referencia de marca deportiva reconocida"
            )
        )

    existentes = {p.nombre.lower() for p in programa.partnerships}

    for partnership in partnerships_detectados:
        if partnership.nombre.lower() not in existentes:
            programa.partnerships.append(partnership)

    return programa