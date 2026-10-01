"""Tests de V3: reglas de partnerships externalizadas a YAML.

Antes de la iteración 25 las reglas específicas de proveedor estaban
incrustadas en el código (`if "jamie murray" in texto`, bloque DBS,
PARTNER_KEYWORDS con cadenas de 3 letras tipo \"dbs\" o \"sports\"). Esto
producía fuga del corpus al sistema, impedía ampliar reglas sin
desplegar código y era la señal más clara posible de prototipo.

Estos tests fijan que (a) el YAML dicta el comportamiento, (b) añadir
una regla es un cambio exclusivamente de datos, y (c) las palabras
clave genéricas no vuelven a incluir cadenas cortas peligrosas.
"""

from pathlib import Path

import pytest

from src.curation import origin
from src.curation.origin import (
    PARTNER_KEYWORDS_GENERICOS,
    evaluar_origen_documental,
    evaluar_partnerships,
)
from src.models import Programa


def _programa(nombre: str = "Test", empresa: str = "Berlitz") -> Programa:
    return Programa(
        nombre=nombre,
        empresa_proveedora=empresa,
        pais="Malta",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
    )


@pytest.fixture(autouse=True)
def _limpiar_cache():
    """La caché de reglas se invalida entre tests para que los YAML
    temporales no contaminen tests posteriores."""
    origin._cargar_reglas.cache_clear()
    yield
    origin._cargar_reglas.cache_clear()


def _escribir_yaml(tmp_path: Path, contenido: str) -> str:
    ruta = tmp_path / "reglas.yaml"
    ruta.write_text(contenido, encoding="utf-8")
    return str(ruta)


# ---------------------------------------------------------------------------
# Reglas declarativas se aplican desde el YAML
# ---------------------------------------------------------------------------


def test_regla_partnership_desde_yaml_detecta_match(tmp_path):
    ruta = _escribir_yaml(
        tmp_path,
        """
partnerships:
  - patron: "jamie murray"
    nombre: "Jamie Murray"
    descripcion: "Colaboración deportiva"
""",
    )
    p = _programa(nombre="Tennis Camp with Jamie Murray")
    resultado = evaluar_partnerships(p, ruta_reglas=ruta)
    assert len(resultado.partnerships) == 1
    assert resultado.partnerships[0].nombre == "Jamie Murray"


def test_regla_partnership_no_dispara_sin_match(tmp_path):
    ruta = _escribir_yaml(
        tmp_path,
        """
partnerships:
  - patron: "jamie murray"
    nombre: "Jamie Murray"
    descripcion: "Colaboración deportiva"
""",
    )
    p = _programa(nombre="General English")
    resultado = evaluar_partnerships(p, ruta_reglas=ruta)
    assert resultado.partnerships == []


def test_regla_origen_mixto_inyecta_partners(tmp_path):
    ruta = _escribir_yaml(
        tmp_path,
        """
origenes_mixtos:
  - patron: "dublin elite soccer"
    descripcion: "Colaboración DBS"
    partners:
      - { nombre: "I-KIDS", rol: "intermediario" }
      - { nombre: "DBS Sports", rol: "actividades" }
      - { nombre: "Future Learning", rol: "escuela" }
""",
    )
    p = _programa(
        nombre="Dublin Elite Soccer and English learning Summer Camp",
        empresa="DBS",
    )
    resultado = evaluar_origen_documental(p, ruta_reglas=ruta)
    assert resultado.es_programa_colaborativo is True
    assert resultado.origen_documento == "mixto"
    nombres = {p.nombre for p in resultado.partners}
    assert nombres == {"I-KIDS", "DBS Sports", "Future Learning"}


def test_regla_origen_mixto_no_duplica_partners(tmp_path):
    ruta = _escribir_yaml(
        tmp_path,
        """
origenes_mixtos:
  - patron: "dublin elite soccer"
    descripcion: "Colaboración DBS"
    partners:
      - { nombre: "I-KIDS", rol: "intermediario" }
""",
    )
    p = _programa(nombre="Dublin Elite Soccer Camp")
    # Primera pasada añade I-KIDS; segunda pasada no debe duplicar
    evaluar_origen_documental(p, ruta_reglas=ruta)
    evaluar_origen_documental(p, ruta_reglas=ruta)
    assert len([x for x in p.partners if x.nombre == "I-KIDS"]) == 1


# ---------------------------------------------------------------------------
# Palabras cortas peligrosas no vuelven
# ---------------------------------------------------------------------------


def test_palabras_cortas_eliminadas_de_keywords_genericos():
    """'dbs' y 'sports' hacían match con cualquier proveedor cuyo
    nombre contuviera esas letras. Deben estar fuera del catálogo
    genérico — las reglas específicas van en el YAML."""
    assert "dbs" not in PARTNER_KEYWORDS_GENERICOS
    assert "sports" not in PARTNER_KEYWORDS_GENERICOS


def test_todas_las_keywords_genericas_son_distintivas():
    """Todas las keywords genéricas tienen al menos 6 caracteres o
    contienen espacios: evita falsos positivos por substring en
    nombres cortos del catálogo."""
    for kw in PARTNER_KEYWORDS_GENERICOS:
        assert len(kw) >= 6 or " " in kw, (
            f"keyword demasiado corta y sin espacio: {kw!r}"
        )


# ---------------------------------------------------------------------------
# Robustez: fichero inexistente y YAML vacío
# ---------------------------------------------------------------------------


def test_sin_fichero_yaml_no_falla(tmp_path):
    """Si el fichero no existe, el sistema sigue funcionando con las
    reglas genéricas (I-KIDS, keywords de partnership) sin aplicar
    reglas específicas."""
    inexistente = str(tmp_path / "no_existe.yaml")
    p = _programa()
    # No debe lanzar excepción
    r1 = evaluar_origen_documental(p, ruta_reglas=inexistente)
    r2 = evaluar_partnerships(r1, ruta_reglas=inexistente)
    assert r2.partnerships == []


def test_yaml_vacio_no_falla(tmp_path):
    ruta = _escribir_yaml(tmp_path, "")
    p = _programa()
    r = evaluar_partnerships(p, ruta_reglas=ruta)
    assert r.partnerships == []


# ---------------------------------------------------------------------------
# Integración: deteccion ikids_propio y mixto siguen funcionando
# ---------------------------------------------------------------------------


def test_ikids_propio_se_detecta_sin_reglas(tmp_path):
    ruta = _escribir_yaml(tmp_path, "")
    p = _programa(nombre="Programa I-KIDS propio")
    r = evaluar_origen_documental(p, ruta_reglas=ruta)
    assert r.origen_documento == "ikids_propio"


def test_proveedor_externo_por_defecto(tmp_path):
    ruta = _escribir_yaml(tmp_path, "")
    p = _programa(nombre="General English")
    r = evaluar_origen_documental(p, ruta_reglas=ruta)
    assert r.origen_documento == "proveedor_externo"


def test_fichero_yaml_real_del_proyecto_carga_sin_errores():
    """El fichero config/reglas_partnerships.yaml debe parsearse OK."""
    from src.curation.origin import _cargar_reglas

    _cargar_reglas.cache_clear()
    reglas = _cargar_reglas()
    assert "origenes_mixtos" in reglas
    assert "partnerships" in reglas
    # Las reglas DBS y Jamie Murray del proyecto deben estar presentes
    patrones_mixtos = [r["patron"] for r in reglas["origenes_mixtos"]]
    patrones_partnerships = [r["patron"] for r in reglas["partnerships"]]
    assert "dublin elite soccer" in patrones_mixtos
    assert "jamie murray" in patrones_partnerships
    assert "fifa" in patrones_partnerships
