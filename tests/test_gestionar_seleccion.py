"""Tests del caso de uso src.application.gestionar_seleccion.

Cubre la gestión de la campaña comercial activa:
    - persistencia atómica (crear, cargar, guardar, limpiar)
    - toggle de programas (añadir, quitar, idempotencia, errores)
    - filtrado del catálogo según campaña (fail-open sin campaña)
    - tolerancia a fichero inexistente, vacío o corrupto
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from src.application.gestionar_seleccion import (
    cargar_seleccion,
    crear_campania,
    filtrar_catalogo,
    guardar_seleccion,
    limpiar_seleccion,
    toggle_programa,
)
from src.models import Programa, SeleccionComercial


# ---------------------------------------------------------------------------
# Fixtures y helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def seleccion_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Aisla cada test en su propio fichero temporal.

    Sobrescribe la variable de entorno IKIDS_SELECCION_PATH que el módulo
    gestionar_seleccion lee en cada llamada para resolver la ruta.
    """
    path = tmp_path / "seleccion_test.json"
    monkeypatch.setenv("IKIDS_SELECCION_PATH", str(path))
    return path


def _programa(key: str, nombre: str = "Programa X") -> Programa:
    """Factoría mínima de Programa para los tests de filtrado."""
    return Programa(
        nombre=nombre,
        empresa_proveedora="Proveedor Test",
        pais="Irlanda",
        idioma="inglés",
        fuente_documento="data/raw/test.pdf",
        programa_key=key,
    )


# ---------------------------------------------------------------------------
# cargar_seleccion
# ---------------------------------------------------------------------------


def test_cargar_sin_fichero_devuelve_none(seleccion_path: Path) -> None:
    assert not seleccion_path.exists()
    assert cargar_seleccion() is None


def test_cargar_con_fichero_vacio_devuelve_none(seleccion_path: Path) -> None:
    seleccion_path.write_text("")
    assert cargar_seleccion() is None


def test_cargar_con_fichero_corrupto_devuelve_none(seleccion_path: Path) -> None:
    """Fail-open: un JSON corrupto no debe bloquear la app."""
    seleccion_path.write_text("{esto no es json válido")
    assert cargar_seleccion() is None


def test_cargar_devuelve_campania_persistida(seleccion_path: Path) -> None:
    original = SeleccionComercial(
        nombre="Campaña test",
        fecha_inicio=date(2026, 10, 1),
        programas_seleccionados=["prog_a", "prog_b"],
    )
    guardar_seleccion(original)
    loaded = cargar_seleccion()
    assert loaded == original


# ---------------------------------------------------------------------------
# guardar_seleccion
# ---------------------------------------------------------------------------


def test_guardar_crea_fichero_y_directorio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """guardar_seleccion debe crear el directorio padre si no existe."""
    path = tmp_path / "subdir_inexistente" / "seleccion.json"
    monkeypatch.setenv("IKIDS_SELECCION_PATH", str(path))

    guardar_seleccion(SeleccionComercial(nombre="X"))
    assert path.exists()
    assert path.parent.exists()


def test_guardar_es_atomica_no_deja_tmp(seleccion_path: Path) -> None:
    """Tras guardar, no debe quedar ningún fichero .tmp residual."""
    guardar_seleccion(SeleccionComercial(nombre="Campaña"))
    residuos = list(seleccion_path.parent.glob("*.tmp"))
    assert residuos == []


def test_round_trip_json_preserva_igualdad(seleccion_path: Path) -> None:
    """Guardar + cargar debe devolver un objeto idéntico al original."""
    original = SeleccionComercial(
        nombre="Campaña año académico 2027",
        fecha_inicio=date(2026, 10, 15),
        fecha_fin=date(2027, 6, 30),
        programas_seleccionados=["sls_academic_year", "jlh_immersion"],
        notas="Foco en Irlanda post-feria",
    )
    guardar_seleccion(original)
    loaded = cargar_seleccion()
    assert loaded == original


# ---------------------------------------------------------------------------
# crear_campania
# ---------------------------------------------------------------------------


def test_crear_campania_persiste_el_nombre(seleccion_path: Path) -> None:
    s = crear_campania("Campaña verano 2027")
    assert s.nombre == "Campaña verano 2027"
    assert cargar_seleccion() == s


def test_crear_campania_sobrescribe_la_anterior(seleccion_path: Path) -> None:
    """Hay una única campaña activa a la vez por diseño."""
    crear_campania("Primera", notas="original")
    nueva = crear_campania("Segunda")

    cargada = cargar_seleccion()
    assert cargada is not None
    assert cargada.nombre == "Segunda"
    assert cargada.notas is None
    assert cargada == nueva


def test_crear_campania_rechaza_nombre_vacio(seleccion_path: Path) -> None:
    with pytest.raises(ValueError):
        crear_campania("")


def test_crear_campania_rechaza_fecha_fin_anterior(seleccion_path: Path) -> None:
    with pytest.raises(ValueError):
        crear_campania(
            "Mal",
            fecha_inicio=date(2027, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )


# ---------------------------------------------------------------------------
# toggle_programa
# ---------------------------------------------------------------------------


def test_toggle_sin_campania_activa_lanza_error(seleccion_path: Path) -> None:
    with pytest.raises(RuntimeError, match="No hay campaña activa"):
        toggle_programa("prog_x", incluir=True)


def test_toggle_anade_programa_a_la_campania(seleccion_path: Path) -> None:
    crear_campania("Campaña")
    s = toggle_programa("prog_a", incluir=True)
    assert s.programas_seleccionados == ["prog_a"]


def test_toggle_quita_programa_de_la_campania(seleccion_path: Path) -> None:
    crear_campania("Campaña")
    toggle_programa("prog_a", incluir=True)
    toggle_programa("prog_b", incluir=True)
    s = toggle_programa("prog_a", incluir=False)
    assert s.programas_seleccionados == ["prog_b"]


def test_toggle_es_idempotente_al_anadir_existente(seleccion_path: Path) -> None:
    """Añadir dos veces el mismo programa no lo duplica."""
    crear_campania("Campaña")
    toggle_programa("prog_a", incluir=True)
    s = toggle_programa("prog_a", incluir=True)
    assert s.programas_seleccionados == ["prog_a"]


def test_toggle_es_idempotente_al_quitar_inexistente(seleccion_path: Path) -> None:
    """Quitar un programa que no está no falla ni rompe el estado."""
    crear_campania("Campaña")
    toggle_programa("prog_a", incluir=True)
    s = toggle_programa("prog_inexistente", incluir=False)
    assert s.programas_seleccionados == ["prog_a"]


def test_toggle_ordena_alfabeticamente(seleccion_path: Path) -> None:
    """La lista persiste siempre ordenada para que los diffs sean estables."""
    crear_campania("Campaña")
    toggle_programa("zzz", incluir=True)
    toggle_programa("aaa", incluir=True)
    s = toggle_programa("mmm", incluir=True)
    assert s.programas_seleccionados == ["aaa", "mmm", "zzz"]


# ---------------------------------------------------------------------------
# limpiar_seleccion
# ---------------------------------------------------------------------------


def test_limpiar_borra_la_campania(seleccion_path: Path) -> None:
    crear_campania("Campaña")
    assert seleccion_path.exists()
    limpiar_seleccion()
    assert not seleccion_path.exists()
    assert cargar_seleccion() is None


def test_limpiar_no_falla_si_no_hay_campania(seleccion_path: Path) -> None:
    """Limpiar sin campaña activa es un no-op silencioso, no un error."""
    assert not seleccion_path.exists()
    limpiar_seleccion()  # no debe lanzar


# ---------------------------------------------------------------------------
# filtrar_catalogo
# ---------------------------------------------------------------------------


def test_filtrar_sin_campania_devuelve_todo(seleccion_path: Path) -> None:
    """Fail-open: sin campaña activa, el filtrado NO debe reducir el catálogo."""
    programas = [_programa("a"), _programa("b"), _programa("c")]
    resultado = filtrar_catalogo(programas)
    assert resultado == programas


def test_filtrar_con_campania_vacia_devuelve_todo(seleccion_path: Path) -> None:
    """Fail-open: una campaña activa pero sin programas no debe vaciar el catálogo."""
    crear_campania("Vacía")
    programas = [_programa("a"), _programa("b")]
    resultado = filtrar_catalogo(programas)
    assert resultado == programas


def test_filtrar_devuelve_solo_seleccionados(seleccion_path: Path) -> None:
    crear_campania("Campaña")
    toggle_programa("b", incluir=True)
    toggle_programa("d", incluir=True)
    programas = [
        _programa("a"), _programa("b"), _programa("c"), _programa("d")
    ]
    resultado = filtrar_catalogo(programas)
    assert [p.programa_key for p in resultado] == ["b", "d"]


def test_filtrar_acepta_seleccion_explicita(seleccion_path: Path) -> None:
    """Si se pasa una selección como argumento, no debe cargar la de disco."""
    # Dejo una campaña en disco con unos programas distintos a los pasados
    crear_campania("Disco")
    toggle_programa("x", incluir=True)
    # ... pero paso una selección distinta explícita
    explicita = SeleccionComercial(
        nombre="Explícita",
        programas_seleccionados=["a"],
    )
    programas = [_programa("a"), _programa("x")]
    resultado = filtrar_catalogo(programas, seleccion=explicita)
    assert [p.programa_key for p in resultado] == ["a"]


def test_filtrar_ignora_programas_sin_key(seleccion_path: Path) -> None:
    crear_campania("Campaña")
    toggle_programa("a", incluir=True)
    programas = [
        _programa("a"),
        Programa(  # sin programa_key
            nombre="Huérfano",
            empresa_proveedora="X",
            pais="Y",
            idioma="inglés",
            fuente_documento="data/raw/x.pdf",
        ),
    ]
    resultado = filtrar_catalogo(programas)
    assert len(resultado) == 1
    assert resultado[0].programa_key == "a"
