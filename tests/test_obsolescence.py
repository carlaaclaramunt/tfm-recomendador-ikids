"""Tests del subsistema de curación documental."""

from datetime import date
from src.models import Programa
from src.curation.obsolescence import evaluar_obsolescencia


def _programa_minimo(anyo: int | None) -> Programa:
    """Crea un Programa con campos mínimos y el año indicado."""
    return Programa(
        nombre="Test",
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        anyo_documento=anyo,
    )


def test_documento_2026_es_vigente():
    p = evaluar_obsolescencia(_programa_minimo(2026), anyo_actual=2026)
    assert p.estado_documento == "vigente"
    assert p.campos_obsoletos == []


def test_documento_2025_es_parcialmente_obsoleto():
    p = evaluar_obsolescencia(_programa_minimo(2025), anyo_actual=2026)
    assert p.estado_documento == "parcialmente_obsoleto"
    assert "precio_min_eur" in p.campos_obsoletos
    assert "fecha_inicio" in p.campos_obsoletos
    assert p.razon_obsolescencia is not None


def test_documento_2024_es_obsoleto():
    p = evaluar_obsolescencia(_programa_minimo(2024), anyo_actual=2026)
    assert p.estado_documento == "obsoleto"
    assert "idioma" in p.campos_obsoletos  # también los campos estructurales
    assert "precio_min_eur" in p.campos_obsoletos


def test_documento_sin_anyo_es_vigente_por_defecto():
    p = evaluar_obsolescencia(_programa_minimo(None), anyo_actual=2026)
    assert p.estado_documento == "vigente"
    assert "no identificado" in p.razon_obsolescencia.lower()