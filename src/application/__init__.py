"""Capa de aplicación: casos de uso del sistema.

Cada módulo de este paquete implementa uno de los casos de uso que
orquestan los subsistemas de dominio (extracción, curación,
recomendación, explicación). La capa de aplicación es la única que
combina varios subsistemas y define el orden en que se invocan.

Casos de uso disponibles:

    - construir_catalogo: extrae los PDFs del corpus, cura los
      resultados y persiste el catálogo procesado.
    - recomendar: dado un perfil de cliente y el catálogo, produce
      las top-k recomendaciones con su explicación en lenguaje natural.
    - gestionar_seleccion: crea, consulta y modifica la campaña
      comercial activa (subconjunto de programas que I-KIDS empuja).
"""

from src.application.construir_catalogo import construir_catalogo
from src.application.gestionar_categorias import (
    cargar_categorias,
    enriquecer_catalogo,
    enriquecer_programa,
    filtrar_por_categorias,
    guardar_categorias,
    set_categorias,
)
from src.application.gestionar_seleccion import (
    cargar_seleccion,
    crear_campania,
    filtrar_catalogo,
    guardar_seleccion,
    limpiar_seleccion,
    toggle_programa,
)
from src.application.recomendar import recomendar

__all__ = [
    "construir_catalogo",
    "recomendar",
    "cargar_seleccion",
    "crear_campania",
    "filtrar_catalogo",
    "guardar_seleccion",
    "limpiar_seleccion",
    "toggle_programa",
    "cargar_categorias",
    "enriquecer_catalogo",
    "enriquecer_programa",
    "filtrar_por_categorias",
    "guardar_categorias",
    "set_categorias",
]
