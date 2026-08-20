"""Comparadores campo a campo entre valor extraído y ground truth.

Cada función recibe (esperado, extraido) y devuelve un Veredicto:

- TP: el campo tiene valor en el GT y la extracción acierta.
- FN: el campo tiene valor en el GT y la extracción es null (omisión).
- FP: la extracción difiere del GT (valor incorrecto o alucinación).
- TN: el campo es null en el GT (ausente_doc) y la extracción también es null.

El veredicto se calcula por campo. La métrica agregada (precisión, recall, F1)
se computa en extraction_metrics.py.

Modo "estricto" acordado en iteración 7: cualquier desviación cuenta como FP.
La tolerancia del 5% aplicada a los precios cubre, entre otras cosas, las
variaciones por la conversión GBP→EUR / USD→EUR que realiza el LLM con tasas
estáticas. Sin esa tolerancia, cualquier cambio del tipo de cambio prompteado
contaría como error de extracción aunque la cifra original sea correcta.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Optional


class Veredicto(str, Enum):
    TP = "TP"
    FP = "FP"
    FN = "FN"
    TN = "TN"


@dataclass(frozen=True)
class Comparacion:
    veredicto: Veredicto
    detalle: str


# ---------------------------------------------------------------------------
# Configuración por campo: cómo se compara cada uno
# ---------------------------------------------------------------------------

# Cada entrada es (kind, **kwargs). kind selecciona la función comparadora.
FIELD_COMPARATORS: dict[str, tuple] = {
    # Comparador específico para `nombre`: cuenta como TP si el nombre del GT
    # es substring del extraído. Razón: tras la extracción multi-programa
    # (iteraciones 5-8) el extractor produce nombres más específicos que el
    # GT (ej. GT "NSX at Woodbridge School" vs extraído "NSX at Woodbridge
    # School - English+ Horse Riding"). Eso es información adicional válida,
    # no error. Si la similitud cae por debajo del umbral se hace fallback
    # a SequenceMatcher para tolerar variaciones menores.
    "nombre": ("string_contains_or_loose", {"umbral": 0.7}),
    "empresa_proveedora": ("string_loose", {"umbral": 0.6}),
    "pais": ("string_exact", {}),
    "ciudad": ("string_loose", {"umbral": 0.75}),
    "idioma": ("enum_exact", {}),
    "edad_min": ("numeric_exact", {}),
    "edad_max": ("numeric_exact", {}),
    "duracion_min_dias": ("numeric_exact", {}),
    "duracion_max_dias": ("numeric_exact", {}),
    "precio_semanal_min_eur": ("numeric_tolerance", {"pct": 0.05}),
    "precio_semanal_max_eur": ("numeric_tolerance", {"pct": 0.05}),
    "tipo_alojamiento": ("set_strings", {}),
    "fecha_inicio": ("date_exact", {}),
    "fecha_fin": ("date_exact", {}),
    "acreditaciones": ("set_strings", {}),
    "idioma_documento_origen": ("enum_exact", {}),
}


def es_nulo(valor: Any) -> bool:
    """True si el valor representa ausencia (null, lista vacía, str vacío)."""
    if valor is None:
        return True
    if isinstance(valor, (list, str)) and len(valor) == 0:
        return True
    return False


def comparar_campo(
    campo: str,
    esperado: Any,
    extraido: Any,
) -> Comparacion:
    """Devuelve un veredicto TP/FP/FN/TN para un campo."""
    esperado_nulo = es_nulo(esperado)
    extraido_nulo = es_nulo(extraido)

    if esperado_nulo and extraido_nulo:
        return Comparacion(Veredicto.TN, "ambos vacíos (campo ausente en doc)")
    if esperado_nulo and not extraido_nulo:
        return Comparacion(
            Veredicto.FP,
            f"alucinación: GT vacío, extraído={extraido!r}",
        )
    if not esperado_nulo and extraido_nulo:
        return Comparacion(
            Veredicto.FN,
            f"omisión: GT={esperado!r}, extraído vacío",
        )

    # Ambos tienen valor → aplicar el comparador correspondiente
    kind, kwargs = FIELD_COMPARATORS.get(campo, ("string_exact", {}))
    iguales, detalle = _aplicar_comparador(kind, esperado, extraido, **kwargs)
    if iguales:
        return Comparacion(Veredicto.TP, detalle)
    return Comparacion(
        Veredicto.FP,
        f"divergencia ({detalle}): GT={esperado!r}, extraído={extraido!r}",
    )


# ---------------------------------------------------------------------------
# Comparadores
# ---------------------------------------------------------------------------


def _aplicar_comparador(kind: str, esperado: Any, extraido: Any, **kwargs) -> tuple[bool, str]:
    if kind == "string_exact":
        return _string_exact(esperado, extraido)
    if kind == "string_loose":
        return _string_loose(esperado, extraido, umbral=kwargs.get("umbral", 0.7))
    if kind == "string_contains_or_loose":
        return _string_contains_or_loose(esperado, extraido, umbral=kwargs.get("umbral", 0.7))
    if kind == "enum_exact":
        return _enum_exact(esperado, extraido)
    if kind == "numeric_exact":
        return _numeric_exact(esperado, extraido)
    if kind == "numeric_tolerance":
        return _numeric_tolerance(esperado, extraido, pct=kwargs.get("pct", 0.05))
    if kind == "date_exact":
        return _date_exact(esperado, extraido)
    if kind == "set_strings":
        return _set_strings(esperado, extraido)
    raise ValueError(f"Comparador desconocido: {kind}")


def _normalizar(s: Any) -> str:
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def _string_exact(a: Any, b: Any) -> tuple[bool, str]:
    if _normalizar(a) == _normalizar(b):
        return True, "string exact"
    return False, "string exact"


def _string_loose(a: Any, b: Any, umbral: float) -> tuple[bool, str]:
    ratio = SequenceMatcher(None, _normalizar(a), _normalizar(b)).ratio()
    if ratio >= umbral:
        return True, f"similitud {ratio:.2f} ≥ {umbral}"
    return False, f"similitud {ratio:.2f} < {umbral}"


def _string_contains_or_loose(a: Any, b: Any, umbral: float) -> tuple[bool, str]:
    """TP si normalize(esperado) es substring de normalize(extraído).

    Asimétrico a propósito: solo aceptamos extracciones MÁS específicas que
    el GT (ej. GT="Millfield School" + extraído="Millfield School Summer
    Programme"). NO aceptamos el caso inverso: si el GT es más específico
    que la extracción, eso significa que el extractor perdió información y
    debe contar como FP.
    """
    na = _normalizar(a)
    nb = _normalizar(b)
    if na and nb and na in nb:
        return True, f"GT contenido en extraído (asimétrico)"
    ratio = SequenceMatcher(None, na, nb).ratio()
    if ratio >= umbral:
        return True, f"similitud {ratio:.2f} ≥ {umbral}"
    return False, f"similitud {ratio:.2f} < {umbral}, GT no contenido"


def _enum_exact(a: Any, b: Any) -> tuple[bool, str]:
    return _string_exact(a, b)


def _numeric_exact(a: Any, b: Any) -> tuple[bool, str]:
    try:
        if float(a) == float(b):
            return True, "numérico exacto"
    except (TypeError, ValueError):
        pass
    return False, "numérico exacto"


def _numeric_tolerance(a: Any, b: Any, pct: float) -> tuple[bool, str]:
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return False, "no convertible a número"
    if fa == 0 and fb == 0:
        return True, "ambos cero"
    base = max(abs(fa), abs(fb))
    if base == 0:
        return False, "base cero con uno no nulo"
    diff_pct = abs(fa - fb) / base
    if diff_pct <= pct:
        return True, f"diferencia {diff_pct * 100:.1f}% ≤ {pct * 100:.0f}%"
    return False, f"diferencia {diff_pct * 100:.1f}% > {pct * 100:.0f}%"


def _date_exact(a: Any, b: Any) -> tuple[bool, str]:
    da = a if isinstance(a, date) else _parse_date(a)
    db = b if isinstance(b, date) else _parse_date(b)
    if da is None or db is None:
        return False, "fecha no parseable"
    if da == db:
        return True, "fecha exacta"
    return False, "fecha distinta"


def _parse_date(s: Any) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _set_strings(a: Any, b: Any) -> tuple[bool, str]:
    sa = _to_set(a)
    sb = _to_set(b)
    if sa == sb:
        return True, "conjuntos iguales"
    return False, f"GT={sorted(sa)} vs extraído={sorted(sb)}"


def _to_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {_normalizar(value)} if value else set()
    if isinstance(value, (list, tuple, set)):
        return {_normalizar(x) for x in value if x is not None and x != ""}
    return {_normalizar(value)}
