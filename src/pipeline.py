"""Orquestador end-to-end del recomendador.

Encadena los tres subsistemas:

    PDFs en data/raw  →  extracción (LLM + OCR)
                      →  catálogo de Programas en data/processed/programas.json
                      →  filtrado por restricciones
                      →  puntuación MCDM
                      →  generación de explicaciones
                      →  recomendaciones finales

Ejecución:

    python -m src.pipeline

Por defecto usa un perfil de cliente sintético definido al final del fichero.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.explanation import explicar
from src.extraction import extract_programs
from src.models import PerfilCliente, Programa, Recomendacion
from src.recommendation import filtrar_candidatos, puntuar_candidatos
from src.curation.merge import fusionar_programas, resumen_fusion
from src.curation import (evaluar_obsolescencia, evaluar_origen_documental, evaluar_partnerships, generar_evidencias, evaluar_costes_adicionales)
load_dotenv()

DATA_RAW = Path(os.getenv("DATA_RAW_DIR", "data/raw"))
DATA_PROCESSED = Path(os.getenv("DATA_PROCESSED_DIR", "data/processed"))
CATALOGO_PATH = DATA_PROCESSED / "programas.json"


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------


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

    # Después de extraer todos los programas, evaluar su obsolescencia
    programas = [evaluar_obsolescencia(p) for p in programas]
    programas = [evaluar_origen_documental(p) for p in programas]
    programas = [evaluar_partnerships(p) for p in programas]
    programas = [evaluar_costes_adicionales(p) for p in programas]
    programas = [generar_evidencias(p) for p in programas]

    # Curación documental: fusión/deduplicación de programas equivalentes
    programas_originales = programas
    programas_fusionados = fusionar_programas(programas_originales)

    print("Resumen de fusión:", resumen_fusion(programas_originales, programas_fusionados))

    programas = programas_fusionados


    _guardar_catalogo(programas)
    return programas


def recomendar(
    perfil: PerfilCliente,
    programas: list[Programa],
    top_k: int = 5,
) -> list[Recomendacion]:
    """Genera las top-k recomendaciones para un perfil dado."""
    candidatos = filtrar_candidatos(perfil, programas)
    print(
        f"Tras el filtrado: {len(candidatos)} candidatos de {len(programas)} programas"
    )

    recomendaciones = puntuar_candidatos(perfil, candidatos)
    for r in recomendaciones:
        r.explicacion = explicar(r, perfil)

    return recomendaciones[:top_k]


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


# ---------------------------------------------------------------------------
# Demo: perfil sintético
# ---------------------------------------------------------------------------


def _perfil_demo() -> PerfilCliente:
    return PerfilCliente(
        idioma_deseado="inglés",
        edad_estudiante=14,
        presupuesto_max_eur=2500.0,
        duracion_min_dias=14,
        duracion_max_dias=30,
        pais_preferido=None,
        tipo_alojamiento_preferido="familia",
        pesos={
            "precio": 0.30,
            "duracion": 0.20,
            "ubicacion": 0.10,
            "alojamiento": 0.25,
            "edad_ajuste": 0.15,
        },
    )


def main() -> None:
    print("=== TFM — Recomendador I-KIDS ===\n")

    programas = construir_catalogo(reextraer=False)
    if not programas:
        print(
            "No hay programas en el catálogo. Coloca PDFs en data/raw/ y "
            "ejecuta de nuevo con reextraer=True para procesarlos."
        )
        return

    perfil = _perfil_demo()
    print(f"\nPerfil del cliente: {perfil.model_dump()}\n")

    recomendaciones = recomendar(perfil, programas, top_k=3)

    print("\n=== TOP 3 RECOMENDACIONES ===\n")
    for i, r in enumerate(recomendaciones, start=1):
        print(f"--- Recomendación #{i} ---")
        print(r.explicacion)
        print()


if __name__ == "__main__":
    main()