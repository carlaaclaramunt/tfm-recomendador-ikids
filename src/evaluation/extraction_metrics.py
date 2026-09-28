"""Cálculo de precisión, recall y F1 sobre la extracción.

Para cada campo del esquema evaluado:
- TP: el GT tiene valor y la extracción coincide (según el comparador).
- FP: la extracción difiere del GT o alucina un valor donde el GT lo marca ausente.
- FN: el GT tiene valor y la extracción es null.
- TN: ambos vacíos. NO entra en precision/recall pero se reporta para auditoría.

Métricas por campo:
    precision = TP / (TP + FP)
    recall    = TP / (TP + FN)
    F1        = 2·P·R / (P + R)

Macro F1 = media aritmética de F1 entre los campos que tienen al menos
una muestra positiva (TP + FN > 0). Campos sin muestras positivas se
excluyen del macro para no inflarlo con TN triviales.

El emparejamiento de programas GT ↔ extraídos se hace por:
  1. PDF de origen (filtra los candidatos del mismo documento),
  2. Similitud del nombre (mayor ratio gana, mínimo 0.5 para evitar matches absurdos).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from src.evaluation.comparators import (
    Comparacion,
    Veredicto,
    comparar_campo,
    es_nulo,
)


@dataclass
class ResultadoCampo:
    campo: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    detalles: list[dict] = field(default_factory=list)

    @property
    def precision(self) -> Optional[float]:
        # Convención: si no hay positivos esperados Y no hay predicciones,
        # precision no tiene sentido (n/a). Si hay positivos esperados pero
        # cero predicciones correctas (TP+FP=0), tratamos precision=0 para
        # que F1=0 y el campo penalice el macro.
        if not self.tiene_positivos:
            return None
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> Optional[float]:
        if not self.tiene_positivos:
            return None
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> Optional[float]:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)

    @property
    def tiene_positivos(self) -> bool:
        return (self.tp + self.fn) > 0


@dataclass
class ResultadoCatalogo:
    fecha: str
    version_gt: str
    n_programas_gt: int
    n_programas_emparejados: int
    por_campo: dict[str, ResultadoCampo]
    macro_f1: Optional[float]
    programas_sin_match: list[str]

    def to_dict(self) -> dict:
        return {
            "fecha": self.fecha,
            "version_gt": self.version_gt,
            "n_programas_gt": self.n_programas_gt,
            "n_programas_emparejados": self.n_programas_emparejados,
            "macro_f1": _round(self.macro_f1),
            "programas_sin_match": self.programas_sin_match,
            "por_campo": {
                nombre: {
                    "tp": r.tp,
                    "fp": r.fp,
                    "fn": r.fn,
                    "tn": r.tn,
                    "precision": _round(r.precision),
                    "recall": _round(r.recall),
                    "f1": _round(r.f1),
                    "detalles": r.detalles,
                }
                for nombre, r in self.por_campo.items()
            },
        }


def _round(x: Optional[float]) -> Optional[float]:
    return round(x, 4) if x is not None else None


# ---------------------------------------------------------------------------
# Emparejamiento GT ↔ catálogo
# ---------------------------------------------------------------------------


def _normalizar(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _match_programa(gt_entry: dict, programas: list[dict]) -> Optional[dict]:
    """Encuentra el programa extraído que mejor empareja con la entrada de GT."""
    pdf_gt = gt_entry["pdf"]
    nombre_target = _normalizar(gt_entry.get("match_nombre") or "")

    candidatos = [
        p for p in programas
        if pdf_gt in (p.get("documentos_fuente") or []) or p.get("fuente_documento") == pdf_gt
    ]
    if not candidatos:
        return None

    if len(candidatos) == 1:
        return candidatos[0]

    mejor: Optional[dict] = None
    mejor_ratio = 0.0
    for c in candidatos:
        ratio = SequenceMatcher(
            None, nombre_target, _normalizar(c.get("nombre"))
        ).ratio()
        if ratio > mejor_ratio:
            mejor = c
            mejor_ratio = ratio
    if mejor_ratio < 0.5:
        return None
    return mejor


# ---------------------------------------------------------------------------
# Evaluación
# ---------------------------------------------------------------------------


def evaluar_extraccion(
    gt: dict,
    programas: list[dict],
) -> ResultadoCatalogo:
    """Calcula F1 macro y métricas por campo comparando programas extraídos vs GT."""
    campos = gt["campos_evaluados"]
    resultados: dict[str, ResultadoCampo] = {c: ResultadoCampo(campo=c) for c in campos}
    sin_match: list[str] = []
    emparejados = 0

    for gt_entry in gt["programas"]:
        match = _match_programa(gt_entry, programas)
        if match is None:
            sin_match.append(gt_entry["id"])
            # Cuentan como FN para todos los campos con valor esperado no nulo
            for campo in campos:
                spec = gt_entry["campos"].get(campo)
                if spec is None:
                    continue
                if not es_nulo(spec.get("esperado")):
                    resultados[campo].fn += 1
                    resultados[campo].detalles.append({
                        "programa": gt_entry["id"],
                        "veredicto": Veredicto.FN.value,
                        "razon": "sin emparejamiento con el catálogo",
                        "esperado": spec.get("esperado"),
                        "extraido": None,
                    })
            continue

        emparejados += 1
        for campo in campos:
            spec = gt_entry["campos"].get(campo)
            if spec is None:
                continue  # campo no anotado para este programa
            esperado = spec.get("esperado")
            extraido = match.get(campo)
            comp = comparar_campo(campo, esperado, extraido)
            _acumular(resultados[campo], comp, gt_entry["id"], esperado, extraido)

    f1s = [r.f1 for r in resultados.values() if r.tiene_positivos and r.f1 is not None]
    macro = sum(f1s) / len(f1s) if f1s else None

    return ResultadoCatalogo(
        fecha=datetime.now().isoformat(timespec="seconds"),
        version_gt=gt.get("version", "?"),
        n_programas_gt=len(gt["programas"]),
        n_programas_emparejados=emparejados,
        por_campo=resultados,
        macro_f1=macro,
        programas_sin_match=sin_match,
    )


def _acumular(
    resultado: ResultadoCampo,
    comp: Comparacion,
    programa_id: str,
    esperado: Any,
    extraido: Any,
) -> None:
    if comp.veredicto == Veredicto.TP:
        resultado.tp += 1
    elif comp.veredicto == Veredicto.FP:
        resultado.fp += 1
    elif comp.veredicto == Veredicto.FN:
        resultado.fn += 1
    elif comp.veredicto == Veredicto.TN:
        resultado.tn += 1
    resultado.detalles.append({
        "programa": programa_id,
        "veredicto": comp.veredicto.value,
        "razon": comp.detalle,
        "esperado": _serializable(esperado),
        "extraido": _serializable(extraido),
    })


def _serializable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)
