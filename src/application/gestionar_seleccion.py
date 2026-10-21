"""Caso de uso: gestionar la selección comercial activa.

Permite al equipo asesor crear, consultar, modificar y limpiar la campaña
comercial activa — el subconjunto de programas que I-KIDS está empujando
en un periodo concreto.

Operaciones:
    cargar_seleccion()            -> SeleccionComercial | None
    guardar_seleccion(seleccion)  -> None
    crear_campania(nombre, ...)   -> SeleccionComercial
    toggle_programa(key, incluir) -> SeleccionComercial
    limpiar_seleccion()           -> None
    filtrar_catalogo(programas)   -> list[Programa]

Persistencia atómica en ``data/seleccion_comercial.json``:

- escritura: temp file + ``os.replace`` para evitar ficheros a medias si el
  proceso cae a mitad de guardado;
- lectura: si el fichero no existe o está vacío, devuelve ``None``, que se
  interpreta como "no hay campaña activa" (fail-open sobre el catálogo
  completo).
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from src.models import Programa, SeleccionComercial

# Permite override por tests o configuración de entorno
_DEFAULT_PATH = Path("data/seleccion_comercial.json")


def _ruta() -> Path:
    """Resuelve la ruta actual (lee la env var en cada llamada, útil para tests)."""
    return Path(os.getenv("IKIDS_SELECCION_PATH", str(_DEFAULT_PATH)))


def cargar_seleccion() -> Optional[SeleccionComercial]:
    """Devuelve la campaña activa, o ``None`` si no hay ninguna configurada."""
    path = _ruta()
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        texto = path.read_text(encoding="utf-8")
        if not texto.strip():
            return None
        return SeleccionComercial.model_validate_json(texto)
    except Exception:
        # Fichero corrupto: lo tratamos como ausente para no bloquear la app.
        return None


def guardar_seleccion(seleccion: SeleccionComercial) -> None:
    """Persiste la campaña activa de forma atómica (temp + rename)."""
    path = _ruta()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        suffix=".tmp",
    ) as tmp:
        tmp.write(seleccion.model_dump_json(indent=2))
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def crear_campania(
    nombre: str,
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    notas: Optional[str] = None,
) -> SeleccionComercial:
    """Crea una campaña activa nueva. Sobrescribe la anterior si existe.

    Hay una única campaña activa a la vez por diseño. Si se quiere lanzar
    una nueva, reemplaza la existente. El modelo soporta ampliar a múltiples
    simultáneas si en el futuro I-KIDS lo necesita.
    """
    campos: dict = {"nombre": nombre}
    if fecha_inicio is not None:
        campos["fecha_inicio"] = fecha_inicio
    if fecha_fin is not None:
        campos["fecha_fin"] = fecha_fin
    if notas is not None:
        campos["notas"] = notas
    seleccion = SeleccionComercial(**campos)
    guardar_seleccion(seleccion)
    return seleccion


def toggle_programa(programa_key: str, incluir: bool) -> SeleccionComercial:
    """Añade o quita un programa de la campaña activa.

    Lanza ``RuntimeError`` si no hay campaña activa — el asesor debe crear
    primero una campaña antes de poder añadir programas.
    """
    seleccion = cargar_seleccion()
    if seleccion is None:
        raise RuntimeError(
            "No hay campaña activa. Crea una con crear_campania() antes de "
            "añadir o quitar programas."
        )
    programas = set(seleccion.programas_seleccionados)
    if incluir:
        programas.add(programa_key)
    else:
        programas.discard(programa_key)
    seleccion.programas_seleccionados = sorted(programas)
    guardar_seleccion(seleccion)
    return seleccion


def limpiar_seleccion() -> None:
    """Elimina la campaña activa (borra el fichero de persistencia)."""
    path = _ruta()
    if path.exists():
        path.unlink()


def filtrar_catalogo(
    programas: list[Programa],
    seleccion: Optional[SeleccionComercial] = None,
) -> list[Programa]:
    """Devuelve el subconjunto del catálogo que está en la campaña activa.

    Si ``seleccion`` es None, carga la campaña activa de disco. Si no hay
    campaña o la lista de programas seleccionados está vacía, devuelve el
    catálogo entero sin modificar (fail-open: no romper la recomendación
    por una selección inexistente o vacía).

    La usa el toggle del Recomendador cuando el asesor marca
    "Solo entre seleccionados" en la pestaña Recomendar (S1.7).
    """
    if seleccion is None:
        seleccion = cargar_seleccion()
    if seleccion is None or not seleccion.programas_seleccionados:
        return programas
    keys = set(seleccion.programas_seleccionados)
    return [p for p in programas if p.programa_key in keys]
