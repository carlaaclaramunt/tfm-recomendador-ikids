"""Esquemas de datos del sistema.

Define los modelos Pydantic que utilizan todos los subsistemas:
extracción, recomendación y explicación.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from datetime import date


# ---------------------------------------------------------------------------
# Programa de inmersión lingüística
# ---------------------------------------------------------------------------

TipoAlojamiento = Literal["familia", "residencia", "hotel", "campamento", "otro"]
Idioma = Literal["inglés", "francés", "alemán", "español", "italiano", "otro"]
IdiomaDocumento = Literal["es", "en", "ca", "fr", "de", "otro"]


class Programa(BaseModel):
    """Representación estructurada de un programa de inmersión lingüística.

    Campos extraídos automáticamente desde la documentación de las empresas
    asociadas a I-KIDS. Los campos opcionales pueden ser None cuando la
    información no aparece en el documento de origen.
    """

    nombre: str = Field(..., description="Nombre comercial del programa")
    empresa_proveedora: str = Field(..., description="Empresa que oferta el programa")

    pais: str = Field(..., description="País de destino")
    ciudad: Optional[str] = Field(None, description="Ciudad de destino, si se especifica")

    idioma: Idioma = Field(..., description="Idioma principal del programa")

    edad_min: Optional[int] = Field(None, ge=0, le=99, description="Edad mínima admitida")
    edad_max: Optional[int] = Field(None, ge=0, le=99, description="Edad máxima admitida")

    duracion_min_dias: Optional[int] = Field(None, ge=1, description="Duración mínima del programa en días")
    duracion_max_dias: Optional[int] = Field(None, ge=1, description="Duración máxima del programa en días")
    precio_min_eur: Optional[float] = Field(None, ge=0, description="Precio mínimo en euros")
    precio_max_eur: Optional[float] = Field(None, ge=0, description="Precio máximo en euros")

    tipo_alojamiento: Optional[TipoAlojamiento] = Field(
        None, description="Tipo de alojamiento ofrecido"
    )

    fecha_inicio: Optional[date] = Field(None, description="Fecha de inicio (ISO 8601)")
    fecha_fin: Optional[str] = Field(None, description="Fecha de fin (ISO 8601)")

    acreditaciones: list[str] = Field(
        default_factory=list,
        description="Acreditaciones del centro (BC, EAQUALS, etc.)",
    )

    # Trazabilidad: información necesaria para la explicabilidad
    idioma_documento_origen: Optional[IdiomaDocumento] = Field(
        None, description="Idioma del documento del que se extrajo el programa"
    )
    fuente_documento: str = Field(..., description="Ruta del documento de origen")


# ---------------------------------------------------------------------------
# Perfil del cliente
# ---------------------------------------------------------------------------


class PerfilCliente(BaseModel):
    """Perfil del cliente que solicita asesoramiento.

    Las preferencias pueden ser parciales. Los campos None se interpretan como
    "el cliente no ha expresado preferencia sobre este criterio".
    """

    idioma_deseado: Idioma
    edad_estudiante: int = Field(..., ge=0, le=99)

    presupuesto_max_eur: Optional[float] = Field(None, ge=0)
    duracion_min_dias: Optional[int] = Field(None, ge=1)
    duracion_max_dias: Optional[int] = Field(None, ge=1)
    pais_preferido: Optional[str] = None
    tipo_alojamiento_preferido: Optional[TipoAlojamiento] = None

    # Pesos relativos de los criterios sobre los que sí hay preferencia
    # Suma esperada = 1.0; el sistema normaliza si no se cumple
    pesos: dict[str, float] = Field(
        default_factory=lambda: {
            "precio": 0.30,
            "duracion": 0.20,
            "ubicacion": 0.20,
            "alojamiento": 0.15,
            "edad_ajuste": 0.15,
        }
    )


# ---------------------------------------------------------------------------
# Salida de recomendación
# ---------------------------------------------------------------------------


class Recomendacion(BaseModel):
    """Recomendación individual con su puntuación y descomposición por criterio."""

    programa: Programa
    puntuacion: float = Field(..., ge=0.0, le=1.0)
    descomposicion: dict[str, float] = Field(
        default_factory=dict,
        description="Contribución de cada criterio a la puntuación total",
    )
    explicacion: str = Field(
        "", description="Explicación textual generada para el usuario"
    )