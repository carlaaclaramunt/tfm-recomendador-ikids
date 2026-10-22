"""Caso de uso: gestionar las categorías comerciales de los programas.

Permite al equipo asesor asignar manualmente las categorías comerciales
(campamento_verano, semestre_academico, etc.) a cada programa del catálogo.

Se persiste APARTE del catálogo extraído (``data/categorias_manuales.json``)
para que una re-extracción con el LLM no pise las asignaciones manuales.
El formato es un mapa plano ``{programa_key: [categorias]}``.

Operaciones:
    cargar_categorias()                  -> dict[str, list[CategoriaPrograma]]
    guardar_categorias(mapa)             -> None
    set_categorias(key, categorias)      -> dict[str, list[CategoriaPrograma]]
    enriquecer_programa(programa)        -> Programa  (con sus categorías)
    enriquecer_catalogo(programas)       -> list[Programa]  (todos enriquecidos)
    filtrar_por_categorias(prog, cats)   -> list[Programa]

El filtrado es OR entre categorías: un programa pasa si tiene AL MENOS UNA
de las categorías pedidas. Si ``cats`` es None o lista vacía, devuelve todo
(fail-open, mismo criterio que gestionar_seleccion).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional, get_args

from src.models import CategoriaPrograma, Programa

_DEFAULT_PATH = Path("data/categorias_manuales.json")
_CATEGORIAS_VALIDAS = set(get_args(CategoriaPrograma))


def _ruta() -> Path:
    """Resuelve la ruta actual (lee la env var en cada llamada, útil para tests)."""
    return Path(os.getenv("IKIDS_CATEGORIAS_PATH", str(_DEFAULT_PATH)))


def cargar_categorias() -> dict[str, list[CategoriaPrograma]]:
    """Devuelve el mapa {programa_key: [categorias]} persistido en disco.

    Si el fichero no existe, está vacío o es corrupto, devuelve ``{}``
    (fail-open: no bloquear la app por un fichero mal escrito).
    """
    path = _ruta()
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        texto = path.read_text(encoding="utf-8")
        if not texto.strip():
            return {}
        data = json.loads(texto)
        if not isinstance(data, dict):
            return {}
        # Sanitiza: descarta claves no-str y categorías no reconocidas.
        limpio: dict[str, list[CategoriaPrograma]] = {}
        for key, cats in data.items():
            if not isinstance(key, str) or not isinstance(cats, list):
                continue
            validas = [c for c in cats if c in _CATEGORIAS_VALIDAS]
            if validas:
                limpio[key] = sorted(set(validas))
        return limpio
    except Exception:
        return {}


def guardar_categorias(mapa: dict[str, list[CategoriaPrograma]]) -> None:
    """Persiste el mapa de forma atómica (temp + rename).

    Elimina entradas vacías para mantener el fichero compacto.
    """
    path = _ruta()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Compactar: no persistir keys con lista vacía.
    compacto = {k: sorted(set(v)) for k, v in mapa.items() if v}
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(compacto, tmp, ensure_ascii=False, indent=2, sort_keys=True)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def set_categorias(
    programa_key: str, categorias: list[CategoriaPrograma]
) -> dict[str, list[CategoriaPrograma]]:
    """Reemplaza la lista de categorías de un programa.

    Pasar lista vacía elimina la entrada del fichero. Lanza ``ValueError``
    si alguna categoría no está en el enum.
    """
    invalidas = [c for c in categorias if c not in _CATEGORIAS_VALIDAS]
    if invalidas:
        raise ValueError(
            f"Categorías no reconocidas: {invalidas}. "
            f"Válidas: {sorted(_CATEGORIAS_VALIDAS)}"
        )
    mapa = cargar_categorias()
    if categorias:
        mapa[programa_key] = sorted(set(categorias))
    else:
        mapa.pop(programa_key, None)
    guardar_categorias(mapa)
    return mapa


def enriquecer_programa(
    programa: Programa,
    mapa: Optional[dict[str, list[CategoriaPrograma]]] = None,
) -> Programa:
    """Devuelve una copia del programa con sus categorías manuales aplicadas.

    Si ``mapa`` es None, lo carga de disco (útil para enriquecer un único
    programa; para un catálogo entero, pasar el mapa cargado una vez).
    """
    if mapa is None:
        mapa = cargar_categorias()
    if not programa.programa_key:
        return programa
    cats = mapa.get(programa.programa_key, [])
    if not cats:
        return programa
    return programa.model_copy(update={"categorias": cats})


def enriquecer_catalogo(programas: list[Programa]) -> list[Programa]:
    """Aplica las categorías manuales a todo el catálogo en una pasada.

    Carga el mapa una vez y lo reutiliza, evitando un read por programa.
    """
    mapa = cargar_categorias()
    if not mapa:
        return programas
    return [enriquecer_programa(p, mapa=mapa) for p in programas]


def filtrar_por_categorias(
    programas: list[Programa],
    categorias: Optional[list[CategoriaPrograma]] = None,
) -> list[Programa]:
    """Devuelve los programas que tienen al menos una de las categorías pedidas.

    Si ``categorias`` es None o lista vacía, devuelve el catálogo entero
    (fail-open, mismo criterio que gestionar_seleccion.filtrar_catalogo).
    """
    if not categorias:
        return programas
    pedidas = set(categorias)
    return [p for p in programas if pedidas.intersection(p.categorias)]
