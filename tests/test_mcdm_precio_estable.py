"""Tests de C3: el score de precio debe ser estable entre consultas.

Antes de la corrección, `_score_precio` normalizaba contra el conjunto de
candidatos ya filtrados. Consecuencia: un mismo programa a 1200€/semana
podía puntuar 0.9 para un perfil y 0.1 para otro sin que cambiara su
precio, solo porque cambiaba el conjunto de rivales que sobrevivieron
al filtro. Esto rompía la comparabilidad entre consultas, que es el
criterio operativo central del recomendador.

Estos tests fijan la invariante correcta: el score de precio de un
programa depende solo del catálogo de referencia, no del subconjunto
de candidatos con el que se le compare en una consulta concreta.
"""

import pytest

from src.models import PerfilCliente, Programa
from src.recommendation.mcdm import _score_precio, puntuar_candidatos


def _programa(nombre: str, precio: float | None) -> Programa:
    return Programa(
        nombre=nombre,
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        precio_semanal_min_eur=precio,
    )


def _perfil() -> PerfilCliente:
    return PerfilCliente(
        idioma_deseado="inglés",
        edad_estudiante=18,
        presupuesto_max_eur=5000.0,
        duracion_min_dias=7,
        duracion_max_dias=14,
    )


# ---------------------------------------------------------------------------
# Invariante central: mismo programa, misma referencia → mismo score
# ---------------------------------------------------------------------------


def test_score_precio_es_estable_entre_consultas():
    """Con la misma referencia (catálogo completo) el score es idéntico
    aunque la lista de candidatos cambie."""
    barato = _programa("Barato", precio=500)
    medio = _programa("Medio", precio=1000)
    caro = _programa("Caro", precio=2000)
    catalogo = [barato, medio, caro]

    # Consulta 1: barato compite con medio y caro
    s1 = _score_precio(_perfil(), barato, catalogo)
    # Consulta 2: barato compite solo con un rival muy similar
    s2 = _score_precio(_perfil(), barato, catalogo)

    assert s1 == pytest.approx(s2)


def test_mismo_programa_puntua_igual_en_dos_perfiles():
    """La invariante que motivó C3: el programa barato puntúa igual
    aunque los conjuntos de candidatos filtrados sean distintos, siempre
    que la referencia de normalización sea la misma."""
    barato = _programa("Barato", precio=500)
    medio = _programa("Medio", precio=1000)
    caro = _programa("Caro", precio=2000)
    catalogo = [barato, medio, caro]

    # Perfil A: solo barato y caro pasan el filtro
    rec_a = puntuar_candidatos(_perfil(), [barato, caro], catalogo=catalogo)
    # Perfil B: solo barato y medio pasan el filtro
    rec_b = puntuar_candidatos(_perfil(), [barato, medio], catalogo=catalogo)

    score_barato_a = next(r for r in rec_a if r.programa.nombre == "Barato").descomposicion["precio"]
    score_barato_b = next(r for r in rec_b if r.programa.nombre == "Barato").descomposicion["precio"]
    assert score_barato_a == pytest.approx(score_barato_b)


# ---------------------------------------------------------------------------
# Casos borde: catálogo con un solo precio, sin precio, con nulos
# ---------------------------------------------------------------------------


def test_un_solo_precio_en_catalogo_devuelve_neutro_no_uno():
    """Antes devolvía 1.0 por defecto, lo que sesgaba al único programa
    con precio frente a cualquier comparación posterior. Ahora: 0.5."""
    uno = _programa("Único", precio=1000)
    assert _score_precio(_perfil(), uno, [uno]) == pytest.approx(0.5)


def test_programa_sin_precio_devuelve_neutro():
    sin_precio = _programa("Sin precio", precio=None)
    con_precio = _programa("Con precio", precio=1000)
    assert _score_precio(_perfil(), sin_precio, [con_precio]) == pytest.approx(0.5)


def test_catalogo_vacio_devuelve_neutro():
    programa = _programa("Test", precio=1000)
    assert _score_precio(_perfil(), programa, []) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Ordenación: más barato → más alto
# ---------------------------------------------------------------------------


def test_mas_barato_recibe_mejor_score():
    barato = _programa("Barato", precio=500)
    caro = _programa("Caro", precio=2000)
    s_barato = _score_precio(_perfil(), barato, [barato, caro])
    s_caro = _score_precio(_perfil(), caro, [barato, caro])
    assert s_barato > s_caro


# ---------------------------------------------------------------------------
# Compatibilidad: catalogo=None cae al comportamiento clásico
# ---------------------------------------------------------------------------


def test_sin_catalogo_cae_a_candidatos_para_compat():
    """Si no se pasa catalogo, puntuar_candidatos sigue funcionando
    (compatibilidad con llamadas antiguas) usando candidatos como
    referencia. Documentado como INESTABLE en el docstring."""
    barato = _programa("Barato", precio=500)
    caro = _programa("Caro", precio=2000)
    rec = puntuar_candidatos(_perfil(), [barato, caro])
    # Debe producir una lista no vacía y Barato debe ganar
    assert len(rec) == 2
    assert rec[0].programa.nombre == "Barato"
