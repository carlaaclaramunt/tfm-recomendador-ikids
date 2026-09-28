"""Caso de uso: construir el catálogo de programas.

Encadena la extracción documental y las etapas de curación, y persiste
el resultado en `data/processed/programas.json`.

Flujo:

    PDFs en data/raw
        → filtrado por exclusiones documentales del asesor
        → extracción LLM (con OCR fallback) por PDF
        → evaluación de obsolescencia / origen / partnerships / costes
        → generación de evidencias
        → fusión / deduplicación cross-doc
        → filtrado de programas totalmente obsoletos
        → persistencia en data/processed/programas.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.curation import (
    evaluar_obsolescencia,
    evaluar_origen_documental,
    evaluar_partnerships,
    generar_evidencias,
    tasa_trazabilidad_literal,
)
from src.curation.merge import fusionar_programas, resumen_fusion
from src.curation.obsolescence import filtrar_no_obsoletos
from src.extraction import extract_programs
from src.models import Programa

load_dotenv(override=True)

DATA_RAW = Path(os.getenv("DATA_RAW_DIR", "data/raw"))
DATA_PROCESSED = Path(os.getenv("DATA_PROCESSED_DIR", "data/processed"))
CATALOGO_PATH = DATA_PROCESSED / "programas.json"
EXCLUSIONS_PATH = Path("data/exclusions.json")


def construir_catalogo(reextraer: bool = False) -> list[Programa]:
    """Construye el catálogo de programas a partir de los PDFs en data/raw.

    Args:
        reextraer: Si es False y existe data/processed/programas.json,
            se carga desde disco en lugar de volver a llamar al LLM.
            Si es True, fuerza la reextracción.
    """
    if not reextraer and CATALOGO_PATH.exists():
        return _cargar_catalogo()

    programas: list[Programa] = []
    pdfs = sorted(DATA_RAW.glob("**/*.pdf"))

    # Filtrar los PDFs marcados como excluidos desde el dashboard.
    # Los documentos excluidos NO se envían al extractor, ahorrando coste
    # API y evitando que su información entre en el catálogo. La decisión
    # de exclusión la toma el asesor humano desde la pestaña "Documentos".
    excluidos = _cargar_exclusiones()
    if excluidos:
        pdfs_activos = [p for p in pdfs if not _esta_excluido(p, excluidos)]
        omitidos = len(pdfs) - len(pdfs_activos)
        if omitidos:
            print(f"Omitidos {omitidos} PDF(s) por exclusion documental")
            for p in pdfs:
                if _esta_excluido(p, excluidos):
                    print(f"  · excluido: {p.relative_to(Path.cwd()) if p.is_absolute() else p}")
        pdfs = pdfs_activos

    print(f"Procesando {len(pdfs)} PDFs...")

    for i, pdf_path in enumerate(pdfs, start=1):
        empresa_hint = pdf_path.parent.name if pdf_path.parent != DATA_RAW else None
        try:
            nuevos = extract_programs(pdf_path, empresa_proveedora_hint=empresa_hint)
            programas.extend(nuevos)
            nombres = ", ".join(p.nombre for p in nuevos[:3])
            extra = "" if len(nuevos) <= 3 else f" (+{len(nuevos) - 3} más)"
            etiqueta = f"{len(nuevos)} programa(s): {nombres}{extra}" if nuevos else "sin programas"
            print(f"  [{i}/{len(pdfs)}] OK: {pdf_path.name} → {etiqueta}")
        except Exception as exc:
            print(f"  [{i}/{len(pdfs)}] ERROR en {pdf_path.name}: {exc}")

    # Enriquecimientos de curación programa a programa.
    programas = [evaluar_obsolescencia(p) for p in programas]
    programas = [evaluar_origen_documental(p) for p in programas]
    programas = [evaluar_partnerships(p) for p in programas]
    # Nota: la antigua etapa `evaluar_costes_adicionales` (heurístico sobre
    # nombre de fichero y ruta del PDF) se retiró tras detectar que su
    # entrada no contenía el texto del documento y por tanto producía
    # importes fantasma. Los costes adicionales ahora los reporta el LLM
    # como campo anidado dentro de cada Programa en la extracción (C1).
    programas = [generar_evidencias(p) for p in programas]

    # Curación cross-doc: fusión/deduplicación de programas equivalentes.
    programas_originales = programas
    programas_fusionados = fusionar_programas(programas_originales)
    print("Resumen de fusión:", resumen_fusion(programas_originales, programas_fusionados))

    # Descarta programas cuyo documento de origen esté totalmente obsoleto;
    # los parcialmente_obsoleto se conservan y el explainer avisa al asesor.
    programas_vigentes = filtrar_no_obsoletos(programas_fusionados)
    descartados = len(programas_fusionados) - len(programas_vigentes)
    if descartados:
        print(f"Filtrados por obsolescencia: {descartados} programa(s)")

    programas = programas_vigentes

    # Métrica de trazabilidad verificable (LD24): fracción de evidencias de
    # campos críticos cuya cita se ha localizado en el texto original del
    # documento. Se reporta por consola y se persiste como resultado propio
    # del sistema, complementario a H1 (extracción) y H2 (ranking).
    metrica = tasa_trazabilidad_literal(programas)
    print(
        "Trazabilidad: "
        f"{metrica['n_literales']}/{metrica['n_evidencias']} literales "
        f"({metrica['tasa_literal']:.1%}), "
        f"{metrica['n_derivadas']} derivadas, "
        f"{metrica['n_no_verificables']} no verificables, "
        f"{metrica['n_inferidas']} inferidas · "
        f"tasa verificable = {metrica['tasa_verificable']:.1%}"
    )

    _guardar_catalogo(programas)
    return programas


# ---------------------------------------------------------------------------
# Gestión de exclusiones documentales
# ---------------------------------------------------------------------------


def _cargar_exclusiones() -> set[str]:
    """Lee data/exclusions.json y devuelve el set de rutas relativas excluidas.

    Este fichero lo gestiona el dashboard Streamlit desde la pestaña
    "Documentos". Un asesor marca un PDF como excluido (documento
    caducado, duplicado o superado por una versión más nueva) y esa
    decisión se persiste aquí. El pipeline consulta esta lista al
    construir el catálogo para omitir los ficheros marcados.
    """
    if not EXCLUSIONS_PATH.exists():
        return set()
    try:
        data = json.loads(EXCLUSIONS_PATH.read_text(encoding="utf-8"))
        return set(data.get("excluidos", []))
    except (json.JSONDecodeError, KeyError):
        print(f"⚠ {EXCLUSIONS_PATH} malformado, se ignora")
        return set()


def _esta_excluido(pdf_path: Path, excluidos: set[str]) -> bool:
    """Comprueba si el PDF está en la lista de exclusiones.

    Normaliza a ruta POSIX relativa a la raíz del proyecto para que el
    match sea estable independientemente de cómo se generó la ruta.
    """
    if not excluidos:
        return False
    try:
        rel = pdf_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        rel = pdf_path.as_posix()
    return rel in excluidos or pdf_path.as_posix() in excluidos


# ---------------------------------------------------------------------------
# Persistencia del catálogo
# ---------------------------------------------------------------------------


def _guardar_catalogo(programas: list[Programa]) -> None:
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    payload = [p.model_dump(mode="json") for p in programas]
    CATALOGO_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Catálogo guardado en {CATALOGO_PATH} ({len(programas)} programas)")


def _cargar_catalogo() -> list[Programa]:
    payload = json.loads(CATALOGO_PATH.read_text(encoding="utf-8"))
    programas = [Programa.model_validate(p) for p in payload]
    print(f"Catálogo cargado desde {CATALOGO_PATH} ({len(programas)} programas)")
    return programas
