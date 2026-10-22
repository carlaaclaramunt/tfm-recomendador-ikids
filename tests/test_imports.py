"""Smoke test de imports.

Si un módulo del proyecto deja de importar (por un nombre renombrado, un
fichero sin subir, una dependencia desaparecida), este test lo cazará en CI
antes del deploy a Streamlit Cloud — que fue justo lo que falló en el
incidente del 2026-10-21.

No prueba lógica: solo verifica que cada módulo público se puede cargar.
"""

from __future__ import annotations


def test_models_importables() -> None:
    from src.models import (
        PerfilCliente,
        Programa,
        Recomendacion,
        SeleccionComercial,
        TurnoPrograma,
    )

    assert all(cls is not None for cls in (
        PerfilCliente, Programa, Recomendacion, SeleccionComercial, TurnoPrograma,
    ))


def test_capa_aplicacion_importable() -> None:
    from src.application import (
        cargar_seleccion,
        construir_catalogo,
        crear_campania,
        filtrar_catalogo,
        guardar_seleccion,
        limpiar_seleccion,
        recomendar,
        toggle_programa,
    )

    assert all(fn is not None for fn in (
        cargar_seleccion, construir_catalogo, crear_campania, filtrar_catalogo,
        guardar_seleccion, limpiar_seleccion, recomendar, toggle_programa,
    ))


def test_webapp_importable() -> None:
    """Importar la webapp sin arrancar Streamlit.

    Es el import que fallaba en Streamlit Cloud. Si este test pasa en CI,
    el deploy va a arrancar bien.
    """
    import src.webapp.app  # noqa: F401


def test_subsistemas_importables() -> None:
    import src.curation  # noqa: F401
    import src.extraction  # noqa: F401
    import src.recommendation  # noqa: F401
    import src.explanation  # noqa: F401
    import src.evaluation  # noqa: F401
