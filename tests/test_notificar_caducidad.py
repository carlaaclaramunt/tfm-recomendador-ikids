"""Tests de la lógica de agrupación del notificador de caducidad.

Se testea solo la parte determinista (identificación y agrupación de
documentos a notificar), no el envío SMTP real. El envío es puramente
infraestructura y se verifica a mano con `--dry-run`.
"""

from __future__ import annotations

from src.models import Programa
from scripts.notificar_caducidad import (
    _documentos_a_notificar,
    _render_html,
    _render_texto,
)


def _programa(
    nombre: str,
    fuente: str,
    estado: str = "vigente",
    anyo: int | None = 2026,
    razon: str = "",
) -> Programa:
    return Programa(
        nombre=nombre,
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento=fuente,
        estado_documento=estado,
        anyo_documento=anyo,
        razon_obsolescencia=razon,
    )


# ---------------------------------------------------------------------------
# Selección de documentos
# ---------------------------------------------------------------------------


def test_no_devuelve_documentos_vigentes():
    programas = [
        _programa("A", "data/raw/x.pdf", estado="vigente"),
        _programa("B", "data/raw/y.pdf", estado="vigente"),
    ]
    assert _documentos_a_notificar(programas) == []


def test_devuelve_documento_obsoleto():
    programas = [
        _programa("A", "data/raw/viejo.pdf", estado="obsoleto", anyo=2024),
    ]
    docs = _documentos_a_notificar(programas)
    assert len(docs) == 1
    assert docs[0]["ruta"] == "data/raw/viejo.pdf"
    assert docs[0]["estado"] == "obsoleto"
    assert docs[0]["anyo"] == 2024


def test_devuelve_documento_parcialmente_obsoleto():
    programas = [
        _programa("A", "data/raw/mix.pdf", estado="parcialmente_obsoleto", anyo=2025),
    ]
    docs = _documentos_a_notificar(programas)
    assert len(docs) == 1
    assert docs[0]["estado"] == "parcialmente_obsoleto"


def test_agrupa_programas_por_documento():
    """Un mismo PDF con varios programas aparece como una sola entrada."""
    programas = [
        _programa("Dublin", "data/raw/catalogo.pdf", estado="obsoleto", anyo=2024),
        _programa("Cork",   "data/raw/catalogo.pdf", estado="obsoleto", anyo=2024),
        _programa("London", "data/raw/catalogo.pdf", estado="obsoleto", anyo=2024),
    ]
    docs = _documentos_a_notificar(programas)
    assert len(docs) == 1
    assert docs[0]["n_programas"] == 3


def test_prioriza_obsoleto_sobre_parcialmente_obsoleto():
    """Si un documento tiene programas en estados mixtos, se marca con el peor."""
    programas = [
        _programa("A", "data/raw/mix.pdf", estado="obsoleto", anyo=2024),
        _programa("B", "data/raw/mix.pdf", estado="parcialmente_obsoleto", anyo=2025),
    ]
    docs = _documentos_a_notificar(programas)
    assert len(docs) == 1
    assert docs[0]["estado"] == "obsoleto"


def test_ordena_obsoletos_primero():
    programas = [
        _programa("A", "data/raw/a.pdf", estado="parcialmente_obsoleto"),
        _programa("B", "data/raw/b.pdf", estado="obsoleto"),
        _programa("C", "data/raw/c.pdf", estado="parcialmente_obsoleto"),
    ]
    docs = _documentos_a_notificar(programas)
    assert [d["estado"] for d in docs] == [
        "obsoleto",
        "parcialmente_obsoleto",
        "parcialmente_obsoleto",
    ]


def test_programa_sin_fuente_documento_se_ignora():
    """Un programa sin ruta de origen no se puede notificar (no hay a qué
    documento apuntar). Debe omitirse con silencio."""
    # No se puede crear directamente un Programa con fuente_documento=""
    # (Pydantic lo validaría como string vacía válida); comprobamos el
    # comportamiento con una ruta en blanco:
    programas = [_programa("A", "", estado="obsoleto")]
    assert _documentos_a_notificar(programas) == []


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def test_render_html_mensaje_vacio_cuando_no_hay_documentos():
    html = _render_html([])
    assert "Enhorabuena" in html or "ningún documento" in html.lower()


def test_render_html_contiene_ruta_del_documento():
    docs = _documentos_a_notificar(
        [_programa("A", "data/raw/berlitz.pdf", estado="obsoleto", anyo=2024)]
    )
    html = _render_html(docs)
    assert "data/raw/berlitz.pdf" in html
    assert "2024" in html


def test_render_texto_contiene_ruta_del_documento():
    docs = _documentos_a_notificar(
        [_programa("A", "data/raw/berlitz.pdf", estado="obsoleto", anyo=2024)]
    )
    texto = _render_texto(docs)
    assert "data/raw/berlitz.pdf" in texto
    assert "obsoleto" in texto
