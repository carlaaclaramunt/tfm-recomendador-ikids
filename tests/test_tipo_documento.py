"""Test de la clasificación funcional del documento."""

from src.models import Programa


def test_programa_default_es_folleto_cliente_final():
    p = Programa(
        nombre="Test",
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
    )
    assert p.tipo_documento == "folleto_cliente_final"


def test_programa_b2b_valida_correctamente():
    p = Programa(
        nombre="Test",
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        tipo_documento="tarifa_b2b",
    )
    assert p.tipo_documento == "tarifa_b2b"