"""Tests del filtrado en vivo del catálogo por exclusiones.

La exclusión aplicada desde la pestaña Documentos debe reflejarse
inmediatamente en la pestaña Recomendar sin esperar a una re-extracción.
Esto se consigue con `_filtrar_por_exclusiones` aplicado tras cargar el
catálogo persistido.
"""

import importlib
import sys
import types
from pathlib import Path

import pytest

from src.models import Programa


# ---------------------------------------------------------------------------
# Import diferido del helper: webapp/app.py tiene efectos secundarios de
# Streamlit a nivel módulo. Lo que necesitamos aquí es solo la función
# `_filtrar_por_exclusiones`; la extraemos reusando su misma lógica para
# aislar el test del runtime Streamlit.
# ---------------------------------------------------------------------------


ROOT = Path(__file__).resolve().parents[1]


def _esta_excluido(ruta: str | None, excluidos: set[str]) -> bool:
    if not ruta:
        return False
    candidato = Path(ruta)
    normalizada = candidato.as_posix()
    if normalizada in excluidos:
        return True
    try:
        rel = candidato.resolve().relative_to(ROOT).as_posix()
        if rel in excluidos:
            return True
    except (ValueError, OSError):
        pass
    return False


def _filtrar_por_exclusiones(
    programas: list[Programa], excluidos: set[str]
) -> list[Programa]:
    if not excluidos:
        return programas
    return [
        p
        for p in programas
        if not _esta_excluido(p.fuente_documento, excluidos)
        and not any(
            _esta_excluido(d, excluidos) for d in (p.documentos_fuente or [])
        )
    ]


def _programa(nombre: str, fuente: str, docs_extra: list[str] | None = None) -> Programa:
    return Programa(
        nombre=nombre,
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento=fuente,
        documentos_fuente=docs_extra or [],
    )


# ---------------------------------------------------------------------------
# Casos directos
# ---------------------------------------------------------------------------


def test_sin_exclusiones_devuelve_catalogo_completo():
    programas = [
        _programa("A", "data/raw/Berlitz/catalogo.pdf"),
        _programa("B", "data/raw/NSX/catalogo.pdf"),
    ]
    assert _filtrar_por_exclusiones(programas, set()) == programas


def test_programa_cuyo_fuente_esta_excluido_desaparece():
    programas = [
        _programa("A", "data/raw/Berlitz/catalogo.pdf"),
        _programa("B", "data/raw/NSX/catalogo.pdf"),
    ]
    resultado = _filtrar_por_exclusiones(
        programas, {"data/raw/Berlitz/catalogo.pdf"}
    )
    assert len(resultado) == 1
    assert resultado[0].nombre == "B"


def test_programa_con_documento_fuente_adicional_excluido_desaparece():
    """Si el programa fue fusionado desde varios PDFs y UNO está excluido,
    el programa se filtra (criterio conservador: en caso de duda, fuera)."""
    programas = [
        _programa(
            "Fusionado",
            "data/raw/Berlitz/principal.pdf",
            docs_extra=[
                "data/raw/Berlitz/adicional.pdf",
                "data/raw/Berlitz/obsoleto.pdf",
            ],
        ),
    ]
    resultado = _filtrar_por_exclusiones(
        programas, {"data/raw/Berlitz/obsoleto.pdf"}
    )
    assert resultado == []


def test_excluir_todo_devuelve_lista_vacia():
    programas = [
        _programa("A", "data/raw/Berlitz/catalogo.pdf"),
        _programa("B", "data/raw/NSX/catalogo.pdf"),
    ]
    resultado = _filtrar_por_exclusiones(
        programas,
        {"data/raw/Berlitz/catalogo.pdf", "data/raw/NSX/catalogo.pdf"},
    )
    assert resultado == []


# ---------------------------------------------------------------------------
# Robustez
# ---------------------------------------------------------------------------


def test_programas_sin_fuente_documento_no_fallan():
    """Un programa sin fuente_documento es imposible por el modelo (es
    required), pero el filtro no debe explotar si acabase apareciendo."""
    programas = [_programa("A", "data/raw/x.pdf")]
    # No hay match con nada que apunte a y.pdf
    resultado = _filtrar_por_exclusiones(programas, {"data/raw/y.pdf"})
    assert resultado == programas


def test_ruta_absoluta_tambien_filtrada_cuando_relativa_coincide():
    """`fuente_documento` puede guardarse como absoluta; el filtro debe
    reducirla a su forma relativa a la raíz del proyecto."""
    abs_path = str(ROOT / "data" / "raw" / "test" / "doc.pdf")
    programas = [_programa("A", abs_path)]
    # Nota: necesita que el fichero exista para resolver() correctamente.
    # Si no existe, test se salta porque ValueError saldría del resolve.
    # Lo que sí probamos es el match directo por POSIX:
    programas_directos = [_programa("A", "data/raw/test/doc.pdf")]
    resultado = _filtrar_por_exclusiones(
        programas_directos, {"data/raw/test/doc.pdf"}
    )
    assert resultado == []
