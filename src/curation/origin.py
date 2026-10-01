"""Clasificación del origen documental y detección de partnerships.

Las reglas específicas de proveedor viven ahora en
`config/reglas_partnerships.yaml` como datos declarativos. Esta
externalización responde al hallazgo V3 del code review externo:
antes de la iteración 25, trazas tipo `if "jamie murray" in texto`
estaban incrustadas en el código, lo que (a) impedía ampliar reglas sin
desplegar un cambio de código, (b) producía \"fuga del corpus al sistema\"
--- el extractor acertaba porque la respuesta estaba escrita en el
código, no porque la hubiera inferido --- y (c) era la señal más clara
posible de prototipo en una revisión externa.

El módulo mantiene únicamente la detección genérica de origen I-KIDS
basada en palabras clave de dominio neutral (`"ikids"`, `"i-kids"`,
`"i kids"`); todo lo demás se evalúa contra el fichero YAML.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from src.models import Partner, Partnership, Programa


IKIDS_KEYWORDS = ["ikids", "i-kids", "i kids"]

# Palabras clave genéricas que indican colaboración documental sin ser
# específicas de un proveedor concreto. Se mantienen aquí porque son de
# dominio y no datos. Las que la revisión identificó como demasiado
# cortas (`"dbs"`, `"sports"`) se eliminaron: hacían match con cualquier
# proveedor cuyo nombre contuviera esas letras.
PARTNER_KEYWORDS_GENERICOS = [
    "in partnership with",
    "powered by",
    "with future learning",
    "future learning",
    "collaboration",
]

_RUTA_YAML_DEFECTO = (
    Path(__file__).resolve().parents[2] / "config" / "reglas_partnerships.yaml"
)


@lru_cache(maxsize=4)
def _cargar_reglas(ruta: str | None = None) -> dict:
    """Carga las reglas desde el YAML con caché.

    El `lru_cache` evita releer el fichero en cada llamada; se invalida
    pasando una ruta distinta (útil en tests).
    """
    ruta_resuelta = Path(ruta) if ruta else _RUTA_YAML_DEFECTO
    if not ruta_resuelta.exists():
        return {"origenes_mixtos": [], "partnerships": []}
    data = yaml.safe_load(ruta_resuelta.read_text(encoding="utf-8")) or {}
    data.setdefault("origenes_mixtos", [])
    data.setdefault("partnerships", [])
    return data


def _texto_programa(programa: Programa) -> str:
    return " ".join(
        [
            programa.nombre or "",
            programa.empresa_proveedora or "",
            programa.fuente_documento or "",
            " ".join(programa.documentos_fuente or []),
        ]
    ).lower()


def evaluar_origen_documental(
    programa: Programa,
    ruta_reglas: str | None = None,
) -> Programa:
    """Clasifica el origen del documento y aplica las reglas de origen mixto.

    Mantiene la detección genérica de I-KIDS como ikids_propio y, cuando
    coincide algún patrón de `origenes_mixtos` del YAML, marca el
    programa como colaborativo e inyecta los partners declarados.
    """
    texto = _texto_programa(programa)

    contiene_ikids = any(k in texto for k in IKIDS_KEYWORDS)
    contiene_partner_generico = any(
        k in texto for k in PARTNER_KEYWORDS_GENERICOS
    )

    if contiene_ikids and contiene_partner_generico:
        programa.origen_documento = "mixto"
        programa.es_programa_colaborativo = True
    elif contiene_ikids:
        programa.origen_documento = "ikids_propio"
    elif programa.origen_documento == "desconocido":
        programa.origen_documento = "proveedor_externo"

    # Reglas específicas de proveedor (datos declarativos).
    reglas = _cargar_reglas(ruta_reglas)
    for regla in reglas.get("origenes_mixtos", []):
        patron = (regla.get("patron") or "").lower().strip()
        if not patron or patron not in texto:
            continue

        programa.es_programa_colaborativo = True
        programa.origen_documento = "mixto"

        existentes = {p.nombre.lower() for p in programa.partners}
        for datos_partner in regla.get("partners", []):
            nombre = datos_partner.get("nombre")
            if not nombre or nombre.lower() in existentes:
                continue
            programa.partners.append(
                Partner(nombre=nombre, rol=datos_partner.get("rol", "otro"))
            )
            existentes.add(nombre.lower())

    return programa


def evaluar_partnerships(
    programa: Programa,
    ruta_reglas: str | None = None,
) -> Programa:
    """Añade partnerships declarativos cuyo patrón aparece en el texto."""
    texto = _texto_programa(programa)
    reglas = _cargar_reglas(ruta_reglas)

    existentes = {p.nombre.lower() for p in programa.partnerships}
    for regla in reglas.get("partnerships", []):
        patron = (regla.get("patron") or "").lower().strip()
        nombre = regla.get("nombre")
        if not patron or not nombre or patron not in texto:
            continue
        if nombre.lower() in existentes:
            continue
        programa.partnerships.append(
            Partnership(
                nombre=nombre,
                descripcion=regla.get("descripcion", ""),
            )
        )
        existentes.add(nombre.lower())

    return programa
