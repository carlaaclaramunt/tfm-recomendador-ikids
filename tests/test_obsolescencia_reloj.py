"""Tests de V4: la obsolescencia no usa un año fijo en el código.

Antes de la iteración 25 `evaluar_obsolescencia` tenía `anyo_actual=2026`
como default literal, de forma que en 2027 todo documento de 2026 seguiría
marcándose como vigente. Ahora el default es `date.today().year`.

El parámetro explícito sigue disponible para hacer la función
determinista en tests.
"""

from datetime import date

from src.curation.obsolescence import evaluar_obsolescencia
from src.models import Programa


def _programa(anyo: int | None) -> Programa:
    return Programa(
        nombre="Test",
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        anyo_documento=anyo,
    )


def test_default_usa_anyo_actual_del_sistema():
    """Sin pasar anyo_actual, se usa date.today().year. Un documento del
    año actual del sistema debe ser vigente."""
    programa = _programa(anyo=date.today().year)
    resultado = evaluar_obsolescencia(programa)
    assert resultado.estado_documento == "vigente"


def test_default_marca_documento_de_hace_dos_anyos_como_obsoleto():
    programa = _programa(anyo=date.today().year - 2)
    resultado = evaluar_obsolescencia(programa)
    assert resultado.estado_documento == "obsoleto"


def test_default_marca_documento_del_anyo_pasado_parcialmente_obsoleto():
    programa = _programa(anyo=date.today().year - 1)
    resultado = evaluar_obsolescencia(programa)
    assert resultado.estado_documento == "parcialmente_obsoleto"


def test_parametro_explicito_permite_tests_deterministas():
    """La parametrización explícita bypassa el reloj del sistema."""
    programa = _programa(anyo=2028)
    # Con anyo_actual=2030, un documento de 2028 es obsoleto (-2)
    resultado = evaluar_obsolescencia(programa, anyo_actual=2030)
    assert resultado.estado_documento == "obsoleto"
    # Con anyo_actual=2029, es parcialmente obsoleto (-1)
    resultado = evaluar_obsolescencia(programa, anyo_actual=2029)
    assert resultado.estado_documento == "parcialmente_obsoleto"
    # Con anyo_actual=2028, es vigente
    resultado = evaluar_obsolescencia(programa, anyo_actual=2028)
    assert resultado.estado_documento == "vigente"


def test_sin_anyo_documento_se_asume_vigente_por_precaucion():
    programa = _programa(anyo=None)
    resultado = evaluar_obsolescencia(programa)
    assert resultado.estado_documento == "vigente"
    assert "no identificado" in (resultado.razon_obsolescencia or "")
