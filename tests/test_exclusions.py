"""Tests para la integración de data/exclusions.json en el pipeline."""

import json
from pathlib import Path

import pytest

import importlib

# El paquete `src.application` reexporta la función `construir_catalogo` en
# su `__init__`, por lo que `src.application.construir_catalogo` como
# atributo resuelve a la función, no al módulo. `importlib.import_module`
# devuelve el módulo real, que es donde vive `EXCLUSIONS_PATH`.
_cc_mod = importlib.import_module("src.application.construir_catalogo")

from src.application.construir_catalogo import (
    _cargar_exclusiones,
    _esta_excluido,
    EXCLUSIONS_PATH,
)

# Nota: tras la refactorización a capa de aplicación, la lógica de exclusiones
# vive en `src.application.construir_catalogo`; `src.pipeline` la reexporta
# por compatibilidad, pero el atributo `EXCLUSIONS_PATH` que consulta
# `_cargar_exclusiones` está en el módulo. Como el paquete `application`
# reexporta la función `construir_catalogo` en su `__init__`, no podemos
# usar la string "src.application.construir_catalogo.EXCLUSIONS_PATH"
# (resolvería a la función); usamos la referencia directa al módulo.


def test_cargar_exclusiones_sin_fichero(tmp_path, monkeypatch):
    """Sin fichero, devuelve set vacío (comportamiento seguro por defecto)."""
    monkeypatch.setattr(_cc_mod, "EXCLUSIONS_PATH", tmp_path / "no_existe.json")
    assert _cargar_exclusiones() == set()


def test_cargar_exclusiones_fichero_valido(tmp_path, monkeypatch):
    payload = {"descripcion": "test", "excluidos": ["a.pdf", "b/c.pdf"]}
    exc_file = tmp_path / "exclusions.json"
    exc_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(_cc_mod, "EXCLUSIONS_PATH", exc_file)
    assert _cargar_exclusiones() == {"a.pdf", "b/c.pdf"}


def test_cargar_exclusiones_fichero_malformado(tmp_path, monkeypatch, capsys):
    exc_file = tmp_path / "exclusions.json"
    exc_file.write_text("no es json {{", encoding="utf-8")
    monkeypatch.setattr(_cc_mod, "EXCLUSIONS_PATH", exc_file)
    resultado = _cargar_exclusiones()
    assert resultado == set()
    assert "malformado" in capsys.readouterr().out


def test_esta_excluido_set_vacio():
    """Con exclusiones vacías, ningún PDF está excluido (short-circuit)."""
    assert _esta_excluido(Path("data/raw/foo.pdf"), set()) is False


def test_esta_excluido_match_ruta_relativa():
    excluidos = {"data/raw/Berlitz/viejo.pdf"}
    assert _esta_excluido(Path("data/raw/Berlitz/viejo.pdf"), excluidos) is True


def test_esta_excluido_no_match():
    excluidos = {"data/raw/Berlitz/viejo.pdf"}
    assert _esta_excluido(Path("data/raw/Berlitz/nuevo.pdf"), excluidos) is False
