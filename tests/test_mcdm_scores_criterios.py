"""Tests T1 — cobertura unitaria de los scorers MCDM restantes.

`_score_precio` ya está cubierto en test_mcdm_precio_estable.py (invariante
C3). Este fichero completa la cobertura con los cinco scorers que faltaban:

- `_score_duracion` (solapamiento entre rangos cliente/programa)
- `_score_ubicacion` (match categórico de país)
- `_score_alojamiento` (match categórico sobre lista)
- `_score_edad_ajuste` (distancia al centro del rango de edad)
- `_score_afinidad` (keywords del perfil contra texto combinado del programa)

Cada bloque fija:
  (a) el caso neutro cuando falta información,
  (b) el caso de match,
  (c) el caso de no-match,
  (d) los bordes relevantes del rango de salida.
"""

import pytest

from src.models import CursoEspecialista, PerfilCliente, Programa
from src.recommendation.mcdm import (
    _score_afinidad,
    _score_alojamiento,
    _score_duracion,
    _score_edad_ajuste,
    _score_ubicacion,
)


# ---------------------------------------------------------------------------
# Fábricas
# ---------------------------------------------------------------------------


def _programa(**overrides) -> Programa:
    base = dict(
        nombre="Test Programme",
        empresa_proveedora="Test",
        pais="Test",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
    )
    base.update(overrides)
    return Programa(**base)


def _perfil(**overrides) -> PerfilCliente:
    base = dict(
        idioma_deseado="inglés",
        edad_estudiante=18,
        presupuesto_max_eur=5000.0,
        duracion_min_dias=7,
        duracion_max_dias=14,
    )
    base.update(overrides)
    return PerfilCliente(**base)


# ---------------------------------------------------------------------------
# _score_duracion
# ---------------------------------------------------------------------------


def test_duracion_programa_sin_rango_es_neutro():
    perfil = _perfil(duracion_min_dias=7, duracion_max_dias=14)
    programa = _programa(duracion_min_dias=None, duracion_max_dias=None)
    assert _score_duracion(perfil, programa) == pytest.approx(0.5)


def test_duracion_cliente_sin_rango_es_neutro():
    perfil = _perfil(duracion_min_dias=None, duracion_max_dias=None)
    programa = _programa(duracion_min_dias=7, duracion_max_dias=14)
    assert _score_duracion(perfil, programa) == pytest.approx(0.5)


def test_duracion_cobertura_total_puntua_maximo():
    """El programa cubre todo el rango del cliente → 1.0 (0.7 base + 0.3)."""
    perfil = _perfil(duracion_min_dias=7, duracion_max_dias=14)
    programa = _programa(duracion_min_dias=1, duracion_max_dias=84)
    assert _score_duracion(perfil, programa) == pytest.approx(1.0)


def test_duracion_cobertura_parcial_queda_entre_base_y_maximo():
    """Solapamiento parcial: el score está entre 0.7 (base) y 1.0."""
    perfil = _perfil(duracion_min_dias=7, duracion_max_dias=14)
    programa = _programa(duracion_min_dias=10, duracion_max_dias=20)
    score = _score_duracion(perfil, programa)
    assert 0.7 < score < 1.0


def test_duracion_rangos_disjuntos_puntua_cero():
    """El programa no ofrece ninguna duración dentro del rango del cliente."""
    perfil = _perfil(duracion_min_dias=7, duracion_max_dias=14)
    programa = _programa(duracion_min_dias=30, duracion_max_dias=60)
    assert _score_duracion(perfil, programa) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _score_ubicacion
# ---------------------------------------------------------------------------


def test_ubicacion_sin_preferencia_del_cliente_es_neutro():
    perfil = _perfil(pais_preferido=None)
    programa = _programa(pais="Reino Unido")
    assert _score_ubicacion(perfil, programa) == pytest.approx(0.5)


def test_ubicacion_match_puntua_maximo():
    perfil = _perfil(pais_preferido="Reino Unido")
    programa = _programa(pais="Reino Unido")
    assert _score_ubicacion(perfil, programa) == pytest.approx(1.0)


def test_ubicacion_match_insensible_a_mayusculas_y_espacios():
    """El comparador normaliza con lower() y strip(), para absorber variantes
    de capitalización y padding del extractor."""
    perfil = _perfil(pais_preferido="REINO UNIDO")
    programa = _programa(pais="  reino unido  ")
    assert _score_ubicacion(perfil, programa) == pytest.approx(1.0)


def test_ubicacion_sin_match_puntua_cero():
    perfil = _perfil(pais_preferido="Irlanda")
    programa = _programa(pais="Reino Unido")
    assert _score_ubicacion(perfil, programa) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _score_alojamiento
# ---------------------------------------------------------------------------


def test_alojamiento_sin_preferencia_del_cliente_es_neutro():
    perfil = _perfil(tipo_alojamiento_preferido=None)
    programa = _programa(tipo_alojamiento=["familia", "residencia"])
    assert _score_alojamiento(perfil, programa) == pytest.approx(0.5)


def test_alojamiento_programa_sin_tipos_es_neutro():
    """Si el extractor no capturó alojamiento, no penaliza al programa."""
    perfil = _perfil(tipo_alojamiento_preferido="familia")
    programa = _programa(tipo_alojamiento=[])
    assert _score_alojamiento(perfil, programa) == pytest.approx(0.5)


def test_alojamiento_match_exacto_puntua_maximo():
    perfil = _perfil(tipo_alojamiento_preferido="familia")
    programa = _programa(tipo_alojamiento=["familia", "residencia"])
    assert _score_alojamiento(perfil, programa) == pytest.approx(1.0)


def test_alojamiento_sin_match_puntua_cero():
    perfil = _perfil(tipo_alojamiento_preferido="hotel")
    programa = _programa(tipo_alojamiento=["familia", "residencia"])
    assert _score_alojamiento(perfil, programa) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _score_edad_ajuste
# ---------------------------------------------------------------------------


def test_edad_ajuste_sin_rango_declarado_es_neutro():
    """Programa sin edad_min/max: no castiga, score 0.5."""
    perfil = _perfil(edad_estudiante=14)
    programa = _programa(edad_min=None, edad_max=None)
    assert _score_edad_ajuste(perfil, programa) == pytest.approx(0.5)


def test_edad_ajuste_estudiante_en_centro_del_rango_puntua_maximo():
    perfil = _perfil(edad_estudiante=15)
    programa = _programa(edad_min=10, edad_max=20)  # centro = 15
    assert _score_edad_ajuste(perfil, programa) == pytest.approx(1.0)


def test_edad_ajuste_estudiante_en_extremo_del_rango_puntua_medio():
    """En los extremos del rango (edad_min o edad_max), la distancia al
    centro iguala a la mitad de la amplitud, por lo que
    distancia_normalizada = 0.5 y el score cae a 0.5."""
    perfil = _perfil(edad_estudiante=10)  # borde inferior
    programa = _programa(edad_min=10, edad_max=20)  # centro=15, amplitud=10
    assert _score_edad_ajuste(perfil, programa) == pytest.approx(0.5)


def test_edad_ajuste_estudiante_muy_fuera_de_rango_satura_en_cero():
    """La función hace clamp a 0 y no devuelve valores negativos."""
    perfil = _perfil(edad_estudiante=50)
    programa = _programa(edad_min=10, edad_max=14)
    assert _score_edad_ajuste(perfil, programa) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _score_afinidad
# ---------------------------------------------------------------------------


def test_afinidad_sin_intereses_declarados_es_neutro():
    """El criterio no castiga a un perfil que no declara intereses."""
    perfil = _perfil(intereses=[])
    programa = _programa(nombre="Football Academy")
    assert _score_afinidad(perfil, programa) == pytest.approx(0.5)


def test_afinidad_match_en_nombre_del_programa():
    perfil = _perfil(intereses=["football"])
    programa = _programa(nombre="Summer Football Camp")
    # 1 hit → 0.5 + 0.25 = 0.75
    assert _score_afinidad(perfil, programa) == pytest.approx(0.75)


def test_afinidad_dos_hits_suben_a_uno():
    perfil = _perfil(intereses=["tennis", "cambridge"])
    programa = _programa(
        nombre="Tennis Academy",
        acreditaciones=["Cambridge English"],
    )
    # 2 hits → 0.5 + 0.5 = 1.0
    assert _score_afinidad(perfil, programa) == pytest.approx(1.0)


def test_afinidad_match_dentro_de_curso_especialista():
    """El texto combinado incluye los cursos especialistas (LD20)."""
    perfil = _perfil(intereses=["horse riding"])
    programa = _programa(
        nombre="Millfield Summer Programme",
        cursos_especialistas=[
            CursoEspecialista(nombre="Specialist Course Horse Riding",
                              actividad="horse riding"),
        ],
    )
    assert _score_afinidad(perfil, programa) == pytest.approx(0.75)


def test_afinidad_sin_match_puntua_cero():
    """El perfil declara intereses pero el programa no los satisface:
    cero, no neutro — este es el caso que motivó añadir el criterio."""
    perfil = _perfil(intereses=["football", "tennis"])
    programa = _programa(nombre="General English Course")
    assert _score_afinidad(perfil, programa) == pytest.approx(0.0)


def test_afinidad_match_insensible_a_mayusculas():
    perfil = _perfil(intereses=["FOOTBALL"])
    programa = _programa(nombre="summer football camp")
    assert _score_afinidad(perfil, programa) == pytest.approx(0.75)


def test_afinidad_satura_en_uno_con_muchos_hits():
    """Tres o más hits no superan 1.0 (clamp)."""
    perfil = _perfil(intereses=["tennis", "football", "cambridge", "ielts"])
    programa = _programa(
        nombre="Tennis & Football Academy",
        acreditaciones=["Cambridge English", "IELTS Preparation Centre"],
    )
    assert _score_afinidad(perfil, programa) == pytest.approx(1.0)
