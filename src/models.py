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

FidelidadExtraccion = Literal[
    "literal",         # cita del LLM verificada carácter a carácter en el PDF
    "derivado",        # cita similar (>0.9) al PDF: OCR, espaciado, normalización menor
    "inferido",        # valor deducido a partir de expresiones cualitativas
    "no_verificable",  # el LLM aportó cita pero no aparece en el PDF (posible alucinación)
    "desconocido",     # no hay cita o el campo no se evalúa
]

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

    # Precios NORMALIZADOS a €/semana. Los precios que aparezcan como total
    # del programa se dividen por la duración en semanas antes de rellenarse.
    # Los que ya aparecen por semana se copian tal cual. Esto permite comparar
    # programas heterogéneos sobre una unidad común y evita el bug silencioso
    # del filtro de presupuesto (LD8 parcial). El total real para el cliente
    # se calcula multiplicando por la duración concreta que elige.
    precio_semanal_min_eur: Optional[float] = Field(
        None, ge=0,
        description="Precio mínimo en euros por semana (opción más barata)"
    )
    precio_semanal_max_eur: Optional[float] = Field(
        None, ge=0,
        description="Precio máximo en euros por semana (opción más cara)"
    )

    moneda_origen: Optional[MonedaOrigen] = Field(
        None,
        description="Moneda en la que aparece el precio en el documento original"
    )
    precio_semanal_min_origen: Optional[float] = Field(
        None, ge=0,
        description="Precio mínimo por semana en la moneda original, sin conversión"
    )
    precio_semanal_max_origen: Optional[float] = Field(
        None, ge=0,
        description="Precio máximo por semana en la moneda original, sin conversión"
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

    # LD5 — Fechas de inicio recurrentes ("Every Monday", "Cualquier lunes",
    # "Starts weekly from January to May"). El schema tradicional forzaba una
    # fecha única y perdía la semántica de recurrencia. Este campo captura el
    # patrón textual tal como aparece en el documento.
    fechas_inicio_recurrentes: Optional[str] = Field(
        None,
        description="Patrón textual de inicio recurrente si el programa admite arranques repetidos (ej. 'Every Monday')"
    )

    # LD20 — Cursos especialistas como modificadores del programa base.
    # Antes generaban entradas duplicadas en el catálogo (Millfield Summer +
    # Millfield Tennis + Millfield Football). Ahora se representan como
    # modalidades del programa base sin duplicar la entrada.
    cursos_especialistas: list[CursoEspecialista] = Field(
        default_factory=list,
        description="Modalidades o cursos especialistas ofrecidos dentro del programa base"
    )

    # LD19 — Turnos discretos del mismo programa. Cuando el programa se
    # ofrece en varios turnos separados con misma duración (típicamente los
    # summer camps con 2-3 sesiones), fecha_inicio/fecha_fin representan la
    # ventana global y `turnos` contiene el detalle de cada sesión.
    turnos: list[TurnoPrograma] = Field(
        default_factory=list,
        description="Turnos discretos del programa (fecha_inicio/fecha_fin de cada sesión)"
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

    # Intereses tematicos del perfil. Se usan para el criterio de afinidad:
    # match textual entre estos keywords y el nombre/partnerships/cursos
    # especialistas del programa. Ejemplos: ["football", "tennis"], ["business",
    # "professional"], ["cambridge", "ielts"], ["50+"], ["clil"].
    # Lista vacia -> afinidad neutra (0.5) en todos los programas.
    intereses: list[str] = Field(
        default_factory=list,
        description="Intereses tematicos del perfil para el criterio de afinidad"
    )

    # Pesos relativos de los criterios sobre los que si hay preferencia.
    # Suma esperada = 1.0; el sistema normaliza si no se cumple.
    pesos: dict[str, float] = Field(
        default_factory=lambda: {
            "precio": 0.25,
            "duracion": 0.15,
            "ubicacion": 0.15,
            "alojamiento": 0.15,
            "edad_ajuste": 0.15,
            "afinidad": 0.15,
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


class CursoEspecialista(BaseModel):
    """LD20 + LD18 — Modalidad especialista dentro del programa base.

    Los cursos especialistas (Tennis, Football, Horse Riding, etc.) NO son
    programas independientes, sino modalidades del programa base que
    reemplazan parcialmente las horas del componente estándar (típicamente
    las sesiones de inglés). Algunas modalidades conllevan un suplemento
    de precio sobre la tarifa base (LD18), que se captura en los campos
    precio_adicional_semanal_*.
    """

    nombre: str = Field(..., description="Nombre del curso especialista (ej. 'Specialist Course Football')")
    actividad: str = Field(..., description="Actividad principal (ej. 'football', 'tennis', 'horse riding')")
    horas_dedicadas: Optional[int] = Field(
        None, ge=0,
        description="Horas semanales dedicadas a la actividad especialista"
    )
    partnership: Optional[str] = Field(
        None,
        description="Colaboración o partnership asociado (ej. 'Active Away | Jamie Murray')"
    )
    descripcion: Optional[str] = Field(
        None,
        description="Descripción breve extra si aporta información relevante"
    )

    # LD18 — suplemento de precio de la variante sobre la tarifa base
    precio_adicional_semanal_eur: Optional[float] = Field(
        None, ge=0,
        description="Suplemento semanal en euros que añade esta modalidad sobre el precio base del programa"
    )
    precio_adicional_semanal_origen: Optional[float] = Field(
        None, ge=0,
        description="Suplemento semanal en la moneda original del documento, sin conversión"
    )


class TurnoPrograma(BaseModel):
    """LD19 — Turno discreto de un programa que se ofrece varias veces.

    Algunos programas (típicamente los summer camps) se ofrecen en dos o más
    turnos separados con la misma duración (ej. NSX Woodbridge: turno 1 del
    5 al 18 de julio, turno 2 del 19 de julio al 1 de agosto). Cada turno se
    representa como una entrada en la lista `turnos` del programa base.
    """

    fecha_inicio: date = Field(..., description="Fecha de inicio del turno (ISO 8601)")
    fecha_fin: date = Field(..., description="Fecha de fin del turno (ISO 8601)")
    nombre: Optional[str] = Field(
        None,
        description="Etiqueta opcional del turno si el documento la especifica (ej. 'Session A')"
    )