"""Tests del esquema Programa, en particular de la preservación de moneda."""

from src.models import Programa


def test_precio_origen_se_preserva_correctamente():
    p = Programa(
        nombre="Test",
        empresa_proveedora="Test",
        pais="Reino Unido",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        precio_semanal_min_eur=3402.6,
        precio_semanal_max_eur=4095.9,
        moneda_origen="GBP",
        precio_semanal_min_origen=2940.0,
        precio_semanal_max_origen=3540.0,
    )
    assert p.moneda_origen == "GBP"
    assert p.precio_semanal_min_origen == 2940.0
    assert p.precio_semanal_max_origen == 3540.0


def test_precio_origen_acepta_null():
    p = Programa(
        nombre="Test",
        empresa_proveedora="Test",
        pais="España",
        idioma="español",
        fuente_documento="data/raw/test.pdf",
    )
    assert p.moneda_origen is None
    assert p.precio_semanal_min_origen is None