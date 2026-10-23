"""Tests del caso de uso src.application.gestionar_categorias.

Cubre:
    - persistencia atómica del mapa {programa_key: [categorias]}
    - sanitización ante fichero inexistente / vacío / corrupto / tipo erróneo
    - set_categorias: añadir, reemplazar, borrar (lista vacía), rechazar inválidas
    - enriquecer_programa / enriquecer_catalogo: aplican categorías al modelo
    - filtrar_por_categorias: OR, fail-open, programas sin categorías
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.gestionar_categorias import (
    cargar_categorias,
    enriquecer_catalogo,
    enriquecer_programa,
    filtrar_por_categorias,
    guardar_categorias,
    set_categorias,
)
from src.models import Programa


# ---------------------------------------------------------------------------
# Fixtures y helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def categorias_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Aisla cada test en su propio fichero temporal."""
    path = tmp_path / "categorias_test.json"
    monkeypatch.setenv("IKIDS_CATEGORIAS_PATH", str(path))
    return path


def _programa(key: str, categorias: list[str] | None = None) -> Programa:
    return Programa(
        nombre=f"Programa {key}",
        empresa_proveedora="Proveedor Test",
        pais="Irlanda",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        programa_key=key,
        categorias=categorias or [],
    )


# ---------------------------------------------------------------------------
# cargar_categorias
# ---------------------------------------------------------------------------


def test_cargar_sin_fichero_devuelve_dict_vacio(categorias_path: Path) -> None:
    assert not categorias_path.exists()
    assert cargar_categorias() == {}


def test_cargar_con_fichero_vacio_devuelve_dict_vacio(categorias_path: Path) -> None:
    categorias_path.write_text("")
    assert cargar_categorias() == {}


def test_cargar_con_fichero_corrupto_devuelve_dict_vacio(categorias_path: Path) -> None:
    categorias_path.write_text("{esto no es json}")
    assert cargar_categorias() == {}


def test_cargar_con_tipo_erroneo_devuelve_dict_vacio(categorias_path: Path) -> None:
    """Si alguien escribe una lista en vez de un dict, no debe romper."""
    categorias_path.write_text('["mini_stay_verano"]')
    assert cargar_categorias() == {}


def test_cargar_filtra_categorias_desconocidas(categorias_path: Path) -> None:
    """Una categoría que ya no existe en el enum se descarta silenciosamente."""
    categorias_path.write_text(
        '{"prog_a": ["mini_stay_verano", "categoria_inventada"]}'
    )
    assert cargar_categorias() == {"prog_a": ["mini_stay_verano"]}


def test_cargar_migra_nombres_antiguos(categorias_path: Path) -> None:
    """campamento_verano (nombre antiguo) se migra a mini_stay_verano al leer."""
    categorias_path.write_text('{"prog_a": ["campamento_verano", "gap_year"]}')
    assert cargar_categorias() == {"prog_a": ["gap_year", "mini_stay_verano"]}


def test_cargar_descarta_entradas_sin_categorias_validas(categorias_path: Path) -> None:
    categorias_path.write_text('{"prog_a": ["invalida"]}')
    assert cargar_categorias() == {}


# ---------------------------------------------------------------------------
# guardar_categorias
# ---------------------------------------------------------------------------


def test_guardar_round_trip(categorias_path: Path) -> None:
    mapa = {"prog_a": ["inmersion_familiar", "mini_stay_verano"]}
    guardar_categorias(mapa)
    assert cargar_categorias() == {
        "prog_a": ["inmersion_familiar", "mini_stay_verano"]
    }


def test_guardar_compacta_entradas_vacias(categorias_path: Path) -> None:
    """No persistir keys con lista vacía (mantiene el fichero compacto)."""
    guardar_categorias({"prog_a": ["mini_stay_verano"], "prog_b": []})
    assert cargar_categorias() == {"prog_a": ["mini_stay_verano"]}


def test_guardar_es_atomica_no_deja_tmp(categorias_path: Path) -> None:
    guardar_categorias({"prog_a": ["gap_year"]})
    residuos = list(categorias_path.parent.glob("*.tmp"))
    assert residuos == []


def test_guardar_crea_directorio_padre(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "subdir" / "categorias.json"
    monkeypatch.setenv("IKIDS_CATEGORIAS_PATH", str(path))
    guardar_categorias({"prog_a": ["gap_year"]})
    assert path.exists()


# ---------------------------------------------------------------------------
# set_categorias
# ---------------------------------------------------------------------------


def test_set_categorias_crea_entrada_nueva(categorias_path: Path) -> None:
    mapa = set_categorias("prog_a", ["mini_stay_verano"])
    assert mapa == {"prog_a": ["mini_stay_verano"]}
    assert cargar_categorias() == {"prog_a": ["mini_stay_verano"]}


def test_set_categorias_reemplaza_la_lista(categorias_path: Path) -> None:
    set_categorias("prog_a", ["mini_stay_verano"])
    mapa = set_categorias("prog_a", ["gap_year", "ano_academico"])
    assert mapa["prog_a"] == ["ano_academico", "gap_year"]


def test_set_categorias_vacia_borra_la_entrada(categorias_path: Path) -> None:
    set_categorias("prog_a", ["mini_stay_verano"])
    mapa = set_categorias("prog_a", [])
    assert "prog_a" not in mapa
    assert cargar_categorias() == {}


def test_set_categorias_rechaza_valor_invalido(categorias_path: Path) -> None:
    with pytest.raises(ValueError, match="Categorías no reconocidas"):
        set_categorias("prog_a", ["categoria_inventada"])


def test_set_categorias_no_afecta_a_otros_programas(categorias_path: Path) -> None:
    set_categorias("prog_a", ["mini_stay_verano"])
    set_categorias("prog_b", ["gap_year"])
    mapa = cargar_categorias()
    assert mapa == {
        "prog_a": ["mini_stay_verano"],
        "prog_b": ["gap_year"],
    }


# ---------------------------------------------------------------------------
# enriquecer_programa / enriquecer_catalogo
# ---------------------------------------------------------------------------


def test_enriquecer_programa_aplica_categorias_persistidas(
    categorias_path: Path,
) -> None:
    set_categorias("prog_a", ["inmersion_familiar", "mini_stay_verano"])
    programa = _programa("prog_a")
    enriquecido = enriquecer_programa(programa)
    assert enriquecido.categorias == ["inmersion_familiar", "mini_stay_verano"]


def test_enriquecer_programa_sin_key_devuelve_original(categorias_path: Path) -> None:
    """Un programa sin programa_key no se puede mapear: se devuelve tal cual."""
    programa = Programa(
        nombre="X",
        empresa_proveedora="Y",
        pais="Z",
        idioma="inglés",
        fuente_documento="x.pdf",
    )
    assert enriquecer_programa(programa).categorias == []


def test_enriquecer_programa_sin_entrada_en_mapa_devuelve_original(
    categorias_path: Path,
) -> None:
    programa = _programa("prog_sin_cat")
    assert enriquecer_programa(programa).categorias == []


def test_enriquecer_catalogo_aplica_a_todos(categorias_path: Path) -> None:
    set_categorias("prog_a", ["mini_stay_verano"])
    set_categorias("prog_b", ["gap_year"])
    programas = [_programa("prog_a"), _programa("prog_b"), _programa("prog_c")]
    enriquecidos = enriquecer_catalogo(programas)
    assert [p.categorias for p in enriquecidos] == [
        ["mini_stay_verano"],
        ["gap_year"],
        [],
    ]


def test_enriquecer_catalogo_sin_mapa_devuelve_igual(categorias_path: Path) -> None:
    programas = [_programa("prog_a"), _programa("prog_b")]
    assert enriquecer_catalogo(programas) == programas


# ---------------------------------------------------------------------------
# filtrar_por_categorias
# ---------------------------------------------------------------------------


def test_filtrar_sin_categorias_devuelve_todo() -> None:
    programas = [_programa("a"), _programa("b")]
    assert filtrar_por_categorias(programas, categorias=None) == programas
    assert filtrar_por_categorias(programas, categorias=[]) == programas


def test_filtrar_devuelve_los_que_matchean_al_menos_una(
    categorias_path: Path,
) -> None:
    programas = [
        _programa("a", ["mini_stay_verano"]),
        _programa("b", ["gap_year"]),
        _programa("c", ["semestre_academico", "ano_academico"]),
        _programa("d", []),
    ]
    resultado = filtrar_por_categorias(programas, ["mini_stay_verano", "gap_year"])
    assert [p.programa_key for p in resultado] == ["a", "b"]


def test_filtrar_programa_con_varias_categorias_cuenta_si_una_coincide(
    categorias_path: Path,
) -> None:
    programas = [_programa("a", ["semestre_academico", "ano_academico"])]
    resultado = filtrar_por_categorias(programas, ["ano_academico"])
    assert len(resultado) == 1
