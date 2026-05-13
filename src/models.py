"""Esquemas de datos del sistema.

Define los modelos Pydantic que utilizan todos los subsistemas:
extracción, recomendación y explicación.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from datetime import date


# ---------------------------------------------------------------------------
# Programa de inmersión lingüística
# ---------------------------------------------------------------------------

TipoAlojamiento = Literal["familia", "residencia", "hotel", "campamento", "otro"]
Idioma = Literal["inglés", "francés", "alemán", "español", "italiano", "otro"]
IdiomaDocumento = Literal["es", "en", "ca", "fr", "de", "otro"]
EstadoDocumento = Literal["vigente", "parcialmente_obsoleto", "obsoleto"]
TipoDocumento = Literal["folleto_cliente_final", "tarifa_b2b", "ficha_programa", "lista_precios", "otro",]
MonedaOrigen = Literal["EUR", "GBP", "USD", "CHF", "OTRO"]

OrigenDocumento = Literal[
    "proveedor_externo",
    "ikids_propio",
    "mixto",
    "desconocido",
]

RolPartner = Literal[
    "organizador",
    "escuela",
    "alojamiento",
    "actividades",
    "intermediario",
    "otro",
]

FidelidadExtraccion = Literal["literal", "derivado", "inferido", "desconocido"]

TipoCoste = Literal[
    "traslado",
    "seguro",
    "deposito",
    "excursion",
    "lavanderia",
    "material",
    "servicio_menores",
    "pocket_money",
    "otro",
]

class Programa(BaseModel):
    """Representación estructurada de un programa de inmersión lingüística.

    Campos extraídos automáticamente desde la documentación de las empresas
    asociadas a I-KIDS. Los campos opcionales pueden ser None cuando la
    información no aparece en el documento de origen.
    """

    nombre: str = Field(..., description="Nombre comercial del programa")
    empresa_proveedora: str = Field(..., description="Empresa que oferta el programa")

    programa_key: Optional[str] = Field(
        None,
        description="Identificador lógico usado para fusionar programas equivalentes"
    )
    documentos_fuente: list[str] = Field(
        default_factory=list,
        description="Lista de documentos que aportan información a este programa"
    )

    pais: str = Field(..., description="País de destino")
    ciudad: Optional[str] = Field(None, description="Ciudad de destino, si se especifica")

    idioma: Idioma = Field(..., description="Idioma principal del programa")

    edad_min: Optional[int] = Field(None, ge=0, le=99, description="Edad mínima admitida")
    edad_max: Optional[int] = Field(None, ge=0, le=99, description="Edad máxima admitida")

    duracion_min_dias: Optional[int] = Field(None, ge=1, description="Duración mínima del programa en días")
    duracion_max_dias: Optional[int] = Field(None, ge=1, description="Duración máxima del programa en días")

    precio_min_eur: Optional[float] = Field(None, ge=0, description="Precio mínimo en euros")
    precio_max_eur: Optional[float] = Field(None, ge=0, description="Precio máximo en euros")

    moneda_origen: Optional[MonedaOrigen] = Field(
        None,
        description="Moneda en la que aparece el precio en el documento original"
    )
    precio_min_origen: Optional[float] = Field(
        None, ge=0,
        description="Precio mínimo en la moneda original del documento, sin conversión"
    )
    precio_max_origen: Optional[float] = Field(
        None, ge=0,
        description="Precio máximo en la moneda original del documento, sin conversión"
    )

    costes_adicionales: list[CosteAdicional] = Field(
        default_factory=list,
        description="Costes adicionales o complementarios no capturados por el precio principal"
    )

    tipo_alojamiento: list[TipoAlojamiento] = Field(
        default_factory=list,
        description="Tipos de alojamiento ofrecidos"
    )

    @field_validator("tipo_alojamiento", mode="before")
    @classmethod
    def normalizar_tipo_alojamiento(cls, value):
        if value is None:
            return []

        if isinstance(value, list):
            return value

        if isinstance(value, str):
            return [value]

        return value

    fecha_inicio: Optional[date] = Field(None, description="Fecha de inicio (ISO 8601)")
    fecha_fin: Optional[date] = Field(None, description="Fecha de fin (ISO 8601)")

    vigencia_inicio: Optional[date] = Field(
        None,
        description="Inicio de validez comercial o tarifaria del documento"
    )

    vigencia_fin: Optional[date] = Field(
        None,
        description="Fin de validez comercial o tarifaria del documento"
    )

    acreditaciones: list[str] = Field(
        default_factory=list,
        description="Acreditaciones del centro (BC, EAQUALS, etc.)",
    )

    # Trazabilidad: información necesaria para la explicabilidad
    idioma_documento_origen: Optional[IdiomaDocumento] = Field(
        None, description="Idioma del documento del que se extrajo el programa"
    )
    fuente_documento: str = Field(..., description="Ruta del documento de origen")

    # ----- Curación documental (RF6) -----

    anyo_documento: Optional[int] = Field(
        None, ge=2000, le=2100,
        description="Año del documento de origen, si se ha podido identificar"
    )
    estado_documento: EstadoDocumento = Field(
        "vigente",
        description="Estado del documento respecto a su vigencia"
    )
    campos_obsoletos: list[str] = Field(
        default_factory=list,
        description="Lista de campos del Programa que se consideran "
                    "obsoletos, aunque el resto de la información siga siendo útil"
    )
    razon_obsolescencia: Optional[str] = Field(
        None,
        description="Explicación textual del motivo de la obsolescencia"
    )
    tipo_documento: TipoDocumento = Field(
        "folleto_cliente_final",
        description="Naturaleza funcional del documento de origen: "
                    "folleto para cliente final, tarifa B2B para agentes, "
                    "ficha técnica del programa, lista de precios, u otro"
    )
    origen_documento: OrigenDocumento = Field(
        "desconocido",
        description="Indica si el documento procede de un proveedor externo, de I-KIDS o es mixto"
    )

    es_programa_colaborativo: bool = Field(
        False,
        description="Indica si el programa se organiza mediante colaboración entre varias entidades"
    )

    partners: list[Partner] = Field(
        default_factory=list,
        description="Entidades implicadas en el programa y su rol"
    )
    partnerships: list[Partnership] = Field(
        default_factory=list,
        description="Colaboraciones con marcas, instituciones o figuras reconocidas"
    )
    evidencias: list[EvidenciaCampo] = Field(
        default_factory=list,
        description="Trazabilidad de campos extraídos y nivel de fidelidad"
    )

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

class Partner(BaseModel):
    nombre: str = Field(..., description="Nombre de la entidad colaboradora")
    rol: RolPartner = Field("otro", description="Rol de la entidad en el programa")

class Partnership(BaseModel):
    nombre: str = Field(..., description="Nombre de la marca o colaboración reconocida")
    descripcion: Optional[str] = Field(
        None,
        description="Descripción breve de la colaboración"
    )

class EvidenciaCampo(BaseModel):
    campo: str
    valor: str
    fidelidad: FidelidadExtraccion = "desconocido"
    fragmento_fuente: Optional[str] = None
    documento_fuente: Optional[str] = None

class CosteAdicional(BaseModel):
    concepto: str = Field(..., description="Concepto del coste adicional")

    tipo: TipoCoste = Field(
        "otro",
        description="Categoría del coste adicional"
    )

    importe: Optional[float] = Field(
        None,
        ge=0,
        description="Importe del coste, si aparece especificado"
    )

    moneda: Optional[MonedaOrigen] = Field(
        None,
        description="Moneda original del coste"
    )

    obligatorio: bool = Field(
        False,
        description="Indica si el coste parece obligatorio"
    )

    incluido_en_precio: bool = Field(
        False,
        description="Indica si el coste está incluido en el precio principal"
    )

    descripcion: Optional[str] = Field(
        None,
        description="Descripción textual del coste"
    )