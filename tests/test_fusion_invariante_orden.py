"""Tests de V2: la fusión de programas debe ser independiente del orden.

El algoritmo anterior comparaba cada programa solo contra el representante
del grupo y rompía al primer match. Resultado: con similitud por
SequenceMatcher y umbral 0,65, agrupar [A, B, C] podía dar resultado
distinto a agrupar [C, B, A] porque A≈B y B≈C no siempre implica A≈C.
Como el orden procedía del `sorted(DATA_RAW.glob('**/*.pdf'))` del pipeline,
renombrar un PDF cambiaba el catálogo final.

El algoritmo actual (union-find) comparando TODOS los pares es transitivo
por construcción e independiente del orden. Estos tests lo fijan.
"""

import random

from src.curation.merge import agrupar_programas_equivalentes, fusionar_programas
from src.models import Programa


def _programa(nombre: str, empresa: str = "Berlitz", pais: str = "Malta") -> Programa:
    return Programa(
        nombre=nombre,
        empresa_proveedora=empresa,
        pais=pais,
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
    )


def _claves_fusion(programas: list[Programa]) -> frozenset[str]:
    """Firma canónica del resultado de fusión: conjunto de nombres finales."""
    fusionados = fusionar_programas(programas)
    return frozenset(p.nombre for p in fusionados)


# ---------------------------------------------------------------------------
# Invariante central: barajar la entrada no cambia el resultado
# ---------------------------------------------------------------------------


def test_fusion_es_independiente_del_orden_cadena_ab_bc():
    """Caso clásico: A≈B y B≈C pero A≉C.

    Antes del fix, agrupar [A, B, C] y [C, B, A] podía dar resultados
    distintos. Ahora el union-find los agrupa transitivamente igual.
    """
    a = _programa("General English Programme")
    b = _programa("General English Program")
    c = _programa("General English")

    r1 = _claves_fusion([a, b, c])
    r2 = _claves_fusion([c, b, a])
    r3 = _claves_fusion([b, a, c])
    assert r1 == r2 == r3


def test_fusion_bajo_todas_las_permutaciones():
    """Con 20 barajados aleatorios el resultado es siempre el mismo."""
    programas = [
        _programa("General Intensive English 30"),
        _programa("General Intensive English 20"),
        _programa("Intensive English 30"),
        _programa("Business English 30"),
        _programa("Business Intensive English"),
        _programa("Teacher Training CLIL"),
        _programa("Teacher Training"),
    ]
    referencia = _claves_fusion(programas)

    rng = random.Random(42)
    for _ in range(20):
        barajado = programas.copy()
        rng.shuffle(barajado)
        assert _claves_fusion(barajado) == referencia


# ---------------------------------------------------------------------------
# Transitividad del algoritmo
# ---------------------------------------------------------------------------


def test_transitividad_cuando_los_dos_pares_matchean():
    """A≈B y B≈C deben acabar en el MISMO grupo aunque A ≉ C directamente."""
    a = _programa("Intensive English Programme Standard")
    b = _programa("Intensive English Programme")
    c = _programa("Intensive English")

    grupos = agrupar_programas_equivalentes([a, b, c])
    # Todos los que están conectados vía B deben acabar en un único grupo
    assert len(grupos) == 1
    assert {p.nombre for p in grupos[0]} == {a.nombre, b.nombre, c.nombre}


def test_programas_distintos_se_separan_en_grupos_distintos():
    """La transitividad no debe colapsarlo todo en un solo grupo cuando
    hay programas realmente distintos."""
    a = _programa("General English", empresa="Berlitz")
    b = _programa("High performance football camp", empresa="DBS", pais="Irlanda")
    c = _programa("NSX at Millfield School", empresa="NSX", pais="Reino Unido")

    grupos = agrupar_programas_equivalentes([a, b, c])
    assert len(grupos) == 3


# ---------------------------------------------------------------------------
# Determinismo
# ---------------------------------------------------------------------------


def test_resultado_vacio_para_lista_vacia():
    assert agrupar_programas_equivalentes([]) == []


def test_un_solo_programa_un_solo_grupo():
    p = _programa("Único")
    grupos = agrupar_programas_equivalentes([p])
    assert grupos == [[p]]


def test_dos_programas_de_proveedores_distintos_no_se_fusionan():
    a = _programa("General English", empresa="Berlitz")
    b = _programa("General English", empresa="NSX")
    grupos = agrupar_programas_equivalentes([a, b])
    assert len(grupos) == 2
