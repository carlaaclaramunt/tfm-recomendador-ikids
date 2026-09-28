"""Punto de entrada CLI del recomendador.

Este fichero es un `main` delgado: no implementa lógica de negocio,
solo orquesta la invocación de los casos de uso de `src.application`
con un perfil de cliente sintético para poder ejecutar el pipeline
completo desde línea de comandos.

Ejecución:

    python -m src.pipeline

La lógica real vive en:

    - src/application/construir_catalogo.py
    - src/application/recomendar.py

Por compatibilidad con código anterior a la refactorización a capa de
aplicación, este módulo reexporta los símbolos principales bajo el
namespace `src.pipeline`.
"""

from __future__ import annotations

from src.application.construir_catalogo import (
    CATALOGO_PATH,
    DATA_PROCESSED,
    DATA_RAW,
    EXCLUSIONS_PATH,
    _cargar_catalogo,
    _cargar_exclusiones,
    _esta_excluido,
    _guardar_catalogo,
    construir_catalogo,
)
from src.application.recomendar import recomendar
from src.models import PerfilCliente

__all__ = [
    "construir_catalogo",
    "recomendar",
    "CATALOGO_PATH",
    "DATA_PROCESSED",
    "DATA_RAW",
    "EXCLUSIONS_PATH",
    "_cargar_catalogo",
    "_cargar_exclusiones",
    "_esta_excluido",
    "_guardar_catalogo",
]


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
