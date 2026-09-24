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
from src.curation.obsolescence import filtrar_no_obsoletos
from src.curation import (evaluar_obsolescencia, evaluar_origen_documental, evaluar_partnerships, generar_evidencias, evaluar_costes_adicionales)
load_dotenv(override=True)

DATA_RAW = Path(os.getenv("DATA_RAW_DIR", "data/raw"))
DATA_PROCESSED = Path(os.getenv("DATA_PROCESSED_DIR", "data/processed"))
CATALOGO_PATH = DATA_PROCESSED / "programas.json"
EXCLUSIONS_PATH = Path("data/exclusions.json")


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

    # Descartar programas cuyo documento de origen está totalmente obsoleto
    # (los parcialmente_obsoleto se conservan; el explainer ya avisa al asesor)
    programas_vigentes = filtrar_no_obsoletos(programas_fusionados)
    descartados = len(programas_fusionados) - len(programas_vigentes)
    if descartados:
        print(f"Filtrados por obsolescencia: {descartados} programa(s)")

    programas = programas_vigentes

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
# Gestión de exclusiones documentales
# ---------------------------------------------------------------------------


def _cargar_exclusiones() -> set[str]:
    """Lee data/exclusions.json y devuelve el set de rutas relativas excluidas.

    Este fichero lo gestiona el dashboard Streamlit desde la pestaña
    "Documentos". Un asesor marca un PDF como excluido (documento
    caducado, duplicado o superado por una versión más nueva) y esa
    decisión se persiste aquí. El pipeline consulta esta lista al
    construir el catálogo para omitir los ficheros marcados.

    Formato del fichero:

        {
          "descripcion": "...",
          "excluidos": ["data/raw/Berlitz/viejo_2024.pdf", ...]
        }

    Si el fichero no existe, devuelve un set vacío (comportamiento
    equivalente a "ningún documento excluido").
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
    match sea estable independientemente de cómo se generó la ruta
    (absoluta desde el dashboard, relativa desde el CLI).
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