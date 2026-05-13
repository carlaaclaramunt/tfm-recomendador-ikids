"""Extracción estructurada de programas mediante LLM.

Utiliza la API de Anthropic (Claude) con la funcionalidad de "tools" para
forzar al modelo a producir una salida válida según el esquema de Programa.

Esta es la primera iteración del sistema. La migración a Llama 3.1 8B local
con decodificación guiada (outlines / guidance) está prevista para la fase
de validación final.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

from src.extraction.pdf_reader import read_pdf_text
from src.models import Programa

load_dotenv()

_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
_API_KEY = os.getenv("ANTHROPIC_API_KEY")

_SYSTEM_PROMPT = """\
Eres un asistente experto en extraer información estructurada sobre \
programas de inmersión lingüística a partir de documentación comercial \
heterogénea (folletos, catálogos, fichas de producto, listas de precios).

Tu tarea es leer el texto que se te proporciona y rellenar el esquema \
estructurado del programa descrito. Cuando un dato no aparezca en el \
documento, deja el campo vacío (null) en lugar de inventarlo. Es preferible \
una respuesta con campos faltantes a una respuesta con datos inventados.

EXTRACCIÓN MULTI-PROGRAMA:
Un documento puede describir uno o varios programas distintos. Extrae
TODOS los programas claramente diferenciados que aparezcan, no solo el
primero. Considera que son programas distintos cuando se diferencian en:
- el nombre del curso (ej. General English, Business English, Private Lessons),
- el centro/sede (ej. Woodbridge School, Millfield School),
- el público objetivo (ej. Youth Camps, 50+ Programmes, Family Packages),
- o el tipo de programa (ej. inmersión estándar, curso de preparación a examen).

Si el documento solo describe variaciones menores del mismo programa
(por ejemplo, distintos números de lecciones a la semana, o distintos
tipos de alojamiento elegibles), NO los duplicas; representa el programa
con un único objeto, marcando los rangos correspondientes en sus
campos de duración, precio o alojamiento.

Si el documento contiene únicamente información comercial sin describir
ningún programa concreto (por ejemplo, un documento de términos y
condiciones), devuelve una lista vacía.

Devuelve siempre la información en el campo "programas" de la tool,
incluso cuando solo haya un programa.

REGLAS DE FORMATO PARA FECHAS:
- Las fechas deben estar SIEMPRE en formato ISO 8601 completo: YYYY-MM-DD.
- Si el documento solo indica el mes (por ejemplo "January 2026"), usa el \
día 1 de ese mes (2026-01-01).
- Si solo indica el año, deja el campo en null en lugar de inventar la fecha.

REGLAS PARA DISTINGUIR FECHAS DEL PROGRAMA Y FECHAS DE VIGENCIA:
Existen dos conceptos distintos que conviene NO confundir:

1) fecha_inicio / fecha_fin: fechas concretas del PROGRAMA que va a 
   hacer el estudiante. Solo se rellenan cuando el documento especifica 
   un calendario fijo del programa (ej. "Summer Camp from 29 June to 
   31 July"). Si el programa puede empezar cualquier semana dentro de 
   una ventana abierta (ej. "Every Monday", "Starts any Monday from 
   January to May"), deja AMBOS campos en null.

2) vigencia_inicio / vigencia_fin: ventana de validez COMERCIAL o 
   TARIFARIA del documento. Se rellena cuando el documento define una 
   campaña con fechas de validez de los precios o de la oferta (ej. 
   "Prices valid from January to May 2026", "Closed Groups Mini Stay 
   - low season - January to May 2026", "Gross Prices 2026 Summer 
   School"). Esto refleja CUÁNDO está disponible el programa, no 
   cuándo lo cursa el cliente.

REGLA: si el documento solo da una ventana ("January to May"), 
rellena vigencia_inicio/vigencia_fin y deja fecha_inicio/fecha_fin 
en null. Si el documento da fechas concretas y fijas del programa, 
rellena fecha_inicio/fecha_fin y deja vigencia_inicio/vigencia_fin 
en null (o también rellenadas, si el documento las especifica 
también).

REGLAS DE FORMATO PARA DURACIÓN:
- Si el programa tiene una duración fija (por ejemplo "7-day camp" o "2-week \
intensive"), usa el mismo valor para duracion_min_dias y duracion_max_dias.
- Si el programa permite elegir la duración (por ejemplo "from 1 to 12 weeks" \
o "available durations: 2, 3, 4 weeks"), marca el rango completo en días: \
para "1 a 12 semanas" sería duracion_min_dias=7 y duracion_max_dias=84.
- IMPORTANTE: cuando el documento muestre precios "por semana" o "per week", \
esa es la UNIDAD DE PRECIO, NO la duración del programa. La duración real \
del programa puede ser muy distinta. Busca por separado cuántas semanas \
dura el programa.
- Si la duración no se especifica de ninguna forma, deja ambos campos null.

REGLAS DE FORMATO PARA PRECIO:
- Si hay un único precio claro, usa el mismo valor para precio_min_eur y \
precio_max_eur.
- Si hay varios precios (por temporada, por edad, por tipo de habitación, \
por número de semanas), marca el menor en precio_min_eur y el mayor en \
precio_max_eur.
- Si el precio aparece en otra moneda (USD, GBP), conviértelo a euros con \
una tasa aproximada (1 USD = 0.92 EUR, 1 GBP = 1.17 EUR).
- Si el precio no aparece, deja ambos campos null.

REGLAS DE FORMATO PARA EDAD:
- Si el documento describe varios programas con rangos de edad distintos \
(por ejemplo niños 8-12 y adolescentes 13-17), enfócate en el programa \
juvenil (8-18 años), que es el segmento principal del sistema.
- Si el documento solo describe programas para adultos, marca edad_min=18 \
y edad_max=null para que el sistema pueda filtrarlos correctamente.
- Si el documento indica explícitamente que el programa es para "todas \
las edades" (expresiones como "all ages", "kids, teens, adults", "ideal \
for everyone", "any age", "todas las edades"), usa edad_min=0 y \
edad_max=99 para preservar esa información de forma explícita.
- Si la edad simplemente no se menciona, deja ambos campos null.

REGLAS PARA IDENTIFICAR EL AÑO DEL DOCUMENTO:
- Busca en el documento referencias explícitas al año de la campaña
  (ej. "2026 Brochure", "2026 Pricing Sheet", "Summer 2026").
- Si encuentras el año claramente, ponlo en el campo anyo_documento.
- Si el documento no indica el año, deja anyo_documento en null.
- No infieras el año a partir de fechas ambiguas si no está
  explícitamente indicado como año de la campaña.
  
REGLAS PARA CLASIFICAR EL TIPO DE DOCUMENTO:
Identifica la naturaleza funcional del documento y rellena el campo
tipo_documento con uno de estos valores:
- "folleto_cliente_final": catálogo o folleto comercial dirigido al
  estudiante o familia que va a contratar el programa. Suele tener
  fotos, descripciones largas, precios PVP.
- "tarifa_b2b": hoja de tarifas NETAS dirigida a agencias o
  intermediarios. Suele incluir comisiones, precios sin margen,
  condiciones de grupos cerrados, referencias a "agent commission",
  "gross prices", "net prices", "closed groups".
- "ficha_programa": descripción técnica del programa sin información
  comercial (sin precios). Típicamente una guía operativa.
- "lista_precios": tabla de precios sin descripción detallada del
  programa. Documento eminentemente numérico.
- "otro": cualquier otro caso que no encaje claramente.

Si el documento mezcla varios tipos, escoge el dominante.

REGLAS PARA PRESERVAR LA MONEDA ORIGINAL:
- Identifica la moneda en la que aparecen los precios en el documento
  (EUR, GBP, USD, CHF u OTRO) y rellena moneda_origen.
- Rellena también precio_min_origen y precio_max_origen con los valores
  numéricos EXACTOS que aparecen en el documento, SIN conversión.
- Independientemente, sigue rellenando precio_min_eur y precio_max_eur
  con los valores convertidos a euros según las tasas indicadas
  (1 USD = 0,92 EUR, 1 GBP = 1,17 EUR).
- Si el documento no especifica la moneda explícitamente, asume EUR.
- Si hay precios en varias monedas en el mismo documento, escoge la
  predominante o la que se aplica al programa principal.
  
COHERENCIA ENTRE PRECIO EUR Y PRECIO ORIGEN:
- Cuando moneda_origen sea "EUR", los campos precio_min_eur/precio_max_eur
  deben tener exactamente los mismos valores que precio_min_origen/precio_max_origen.
- Cuando moneda_origen sea otra (GBP, USD, CHF), aplica la tasa de conversión
  indicada y rellena ambos pares de campos.
  
REGLAS PARA COSTES ADICIONALES Y COMPLEMENTARIOS:
- Debes extraer cualquier coste económico mencionado en el documento que no sea claramente el precio principal del programa.
- Busca especialmente:
  - airport transfer, transfer, traslado, trasllat
  - unaccompanied minor service, minor service, menor no acompañado, menor no acompanyat
  - insurance, seguro, assegurança
  - deposit, damage deposit, depósito, dipòsit
  - pocket money, dinero de bolsillo
  - laundry, lavandería, bugaderia
  - excursions, extra activities, excursiones
  - material, books, registration fee, enrolment fee
- Incluye también costes recomendados aunque no sean obligatorios, por ejemplo pocket money.
- Si aparece una expresión como "95 € per trajecte", "£30-£50 per week" o "75 €", debes crear un objeto en costes_adicionales.
- Si el coste aparece como rango, usa el valor mínimo en importe y explica el rango completo en descripcion.
- Si el coste es opcional, obligatorio=false.
- Si el documento usa expresiones como mandatory, compulsory, required, obligatori, obligatorio o must be paid, obligatorio=true.
- Si el documento indica included, inclòs, incluido o included in price, incluido_en_precio=true.
- Si no hay importe explícito pero sí concepto económico, crea igualmente el coste con importe=null.
- No incluyas tuition, alojamiento principal o precio total del programa como coste adicional.
- No inventes costes.

EJEMPLOS DE EXTRACCIÓN DE COSTES:
- Texto: "Trasllat privat a l’aeroport 95 € per trajecte"
  → costes_adicionales:
    [{
      "concepto": "Traslado privado al aeropuerto",
      "tipo": "traslado",
      "importe": 95,
      "moneda": "EUR",
      "obligatorio": false,
      "incluido_en_precio": false,
      "descripcion": "Trasllat privat a l’aeroport 95 € per trajecte"
    }]

- Texto: "Servei de menor no acompanyat 75 €"
  → tipo="servicio_menores", importe=75, moneda="EUR"

- Texto: "Pocket Money £30-£50 per week"
  → tipo="pocket_money", importe=30, moneda="GBP",
    descripcion="Pocket Money £30-£50 per week"
  
"""

# Esquema interno de un único programa (extraído del actual input_schema).
_PROGRAMA_SCHEMA = {
    "type": "object",
    "properties": {
        "nombre": {"type": "string", "description": "Nombre comercial del programa"},
        "empresa_proveedora": {
            "type": "string",
            "description": "Empresa que oferta el programa",
        },
        "pais": {"type": "string", "description": "País de destino"},
        "ciudad": {"type": ["string", "null"], "description": "Ciudad de destino"},
        "idioma": {
            "type": "string",
            "enum": ["inglés", "francés", "alemán", "español", "italiano", "otro"],
        },
        "edad_min": {"type": ["integer", "null"], "minimum": 0, "maximum": 99},
        "edad_max": {"type": ["integer", "null"], "minimum": 0, "maximum": 99},
        "duracion_min_dias": {
            "type": ["integer", "null"], "minimum": 1,
            "description": "Duración mínima del programa en días",
        },
        "duracion_max_dias": {
            "type": ["integer", "null"], "minimum": 1,
            "description": "Duración máxima del programa en días",
        },
        "precio_min_eur": {
            "type": ["number", "null"], "minimum": 0,
            "description": "Precio mínimo en euros (opción más barata)",
        },
        "precio_max_eur": {
            "type": ["number", "null"], "minimum": 0,
            "description": "Precio máximo en euros (opción más cara)",
        },
        "tipo_alojamiento": {
            "type": ["array", "null"],
            "items": {
                "type": "string",
                "enum": ["familia", "residencia", "hotel", "campamento", "otro"],
            },
            "description": "Tipos de alojamiento ofrecidos (puede haber varios)",
        },
        "fecha_inicio": {
    "type": ["string", "null"],
    "description": "Fecha concreta de inicio del programa (ISO 8601). "
                   "null si el programa puede arrancar cualquier semana "
                   "dentro de una ventana abierta."
        },
        "fecha_fin": {
            "type": ["string", "null"],
            "description": "Fecha concreta de fin del programa (ISO 8601). "
                           "null si depende del cliente o de la duración elegida."
        },
        "vigencia_inicio": {
            "type": ["string", "null"],
            "description": "Inicio de la ventana de validez comercial o "
                           "tarifaria del documento (ISO 8601)"
        },
        "vigencia_fin": {
            "type": ["string", "null"],
            "description": "Fin de la ventana de validez comercial o "
                           "tarifaria del documento (ISO 8601)"
        },
        "acreditaciones": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
        "idioma_documento_origen": {
            "type": ["string", "null"],
            "enum": ["es", "en", "ca", "fr", "de", "otro", None],
        },
        "anyo_documento": {
            "type": ["integer", "null"],
            "minimum": 2000, "maximum": 2100,
        },
        "tipo_documento": {
            "type": "string",
            "enum": [
                "folleto_cliente_final", "tarifa_b2b",
                "ficha_programa", "lista_precios", "otro",
            ],
        },
        "moneda_origen": {
            "type": ["string", "null"],
            "enum": ["EUR", "GBP", "USD", "CHF", "OTRO", None],
        },
        "precio_min_origen": {"type": ["number", "null"], "minimum": 0},
        "precio_max_origen": {"type": ["number", "null"], "minimum": 0},

    },
    "required": ["nombre", "empresa_proveedora", "pais", "idioma"],
}

# La tool ahora devuelve una LISTA de programas
_EXTRACTION_TOOL = {
    "name": "extract_programas",
    "description": (
        "Devuelve la lista de TODOS los programas de inmersión "
        "lingüística descritos en el documento. Si el documento "
        "describe múltiples programas distintos, devuelve uno por cada "
        "uno. Si solo describe uno, devuelve una lista con un único "
        "elemento."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "programas": {
                "type": "array",
                "items": _PROGRAMA_SCHEMA,
                "description": "Lista de programas extraídos del documento",
            },
            "costes_adicionales": {
                "type": "array",
                "description": (
                    "Lista de costes económicos adicionales, opcionales, obligatorios o "
                    "recomendados que aparecen en el documento y que no son el precio "
                    "principal del programa. Deben incluirse traslados, seguros, depósitos, "
                    "servicios para menores no acompañados, pocket money, lavandería, "
                    "excursiones extra, material, registration fees o suplementos."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "concepto": {
                            "type": "string",
                            "description": (
                                "Nombre breve del coste adicional. Ejemplos: "
                                "'Airport transfer', 'Servei de menor no acompanyat', "
                                "'Pocket money recomendado', 'Damage deposit'."
                            ),
                        },
                        "tipo": {
                            "type": "string",
                            "enum": [
                                "traslado",
                                "seguro",
                                "deposito",
                                "excursion",
                                "lavanderia",
                                "material",
                                "servicio_menores",
                                "pocket_money",
                                "otro",
                            ],
                            "description": "Categoría del coste adicional.",
                        },
                        "importe": {
                            "type": ["number", "null"],
                            "minimum": 0,
                            "description": (
                                "Importe numérico del coste. Si aparece un rango como "
                                "'£30-£50', usa el valor mínimo y conserva el rango completo "
                                "en descripcion."
                            ),
                        },
                        "moneda": {
                            "type": ["string", "null"],
                            "enum": ["EUR", "GBP", "USD", "CHF", "OTRO", None],
                            "description": "Moneda original en la que aparece el coste.",
                        },
                        "obligatorio": {
                            "type": "boolean",
                            "description": (
                                "True si el documento indica que el coste es obligatorio, "
                                "compulsory, mandatory, required, obligatori u obligatorio."
                            ),
                        },
                        "incluido_en_precio": {
                            "type": "boolean",
                            "description": (
                                "True si el documento indica que el coste está incluido "
                                "en el precio principal."
                            ),
                        },
                        "descripcion": {
                            "type": ["string", "null"],
                            "description": (
                                "Fragmento breve o resumen del texto original donde aparece "
                                "el coste. Debe conservar expresiones como '95 € per trajecte' "
                                "o '£30-£50 per week'."
                            ),
                        },
                    },
                    "required": [
                        "concepto",
                        "tipo",
                        "importe",
                        "moneda",
                        "obligatorio",
                        "incluido_en_precio",
                        "descripcion",
                    ],
                },
                "default": [],
            },
        },
        "required": ["programas"],
    },
}


def extract_programs(
    pdf_path: Path | str,
    empresa_proveedora_hint: Optional[str] = None,
) -> list[Programa]:
    """Extrae TODOS los Programas estructurados a partir de un PDF.

    Un documento puede describir varios programas distintos. Esta función
    devuelve la lista completa. Si el documento solo describe uno, devuelve
    una lista con un único elemento. Si no describe ninguno, devuelve [].

    Args:
        pdf_path: Ruta al PDF de origen.
        empresa_proveedora_hint: Nombre de la empresa proveedora si se
            conoce (típicamente derivado del nombre de la carpeta).

    Returns:
        Lista de objetos Programa validados.
    """
    if _API_KEY is None:
        raise RuntimeError(
            "Falta la variable de entorno ANTHROPIC_API_KEY. "
            "Copia .env.example a .env y rellénala."
        )

    pdf_path = Path(pdf_path)
    texto = read_pdf_text(pdf_path)
    texto = texto[:20000]

    user_prompt = _build_user_prompt(texto, empresa_proveedora_hint)

    client = anthropic.Anthropic(api_key=_API_KEY)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=8192,             # ↑ mayor: cabe una lista de programas
        temperature=0,
        system=_SYSTEM_PROMPT,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_programas"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    payload = _extract_tool_payload(response)
    programas_data = payload.get("programas", [])

    programas: list[Programa] = []
    for prog_data in programas_data:
        prog_data["fuente_documento"] = str(pdf_path)
        if empresa_proveedora_hint and not prog_data.get("empresa_proveedora"):
            prog_data["empresa_proveedora"] = empresa_proveedora_hint
        programas.append(Programa.model_validate(prog_data))

    return programas


def _build_user_prompt(texto: str, empresa_hint: Optional[str]) -> str:
    contexto_empresa = (
        f"La empresa proveedora del documento es {empresa_hint}.\n\n"
        if empresa_hint
        else ""
    )
    return (
        f"{contexto_empresa}"
        "A continuación se incluye el texto del documento. Extrae la "
        "información del programa principal usando la tool extract_programas.\n\n"
        "=== INICIO DEL DOCUMENTO ===\n"
        f"{texto}\n"
        "=== FIN DEL DOCUMENTO ==="
    )


def _extract_tool_payload(response: anthropic.types.Message) -> dict:
    """Recupera el JSON devuelto por la tool dentro de la respuesta."""
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_programas":
            return dict(block.input)
    raise RuntimeError(
        "La respuesta del modelo no contiene la llamada esperada a "
        "extract_programas. Respuesta cruda: "
        f"{json.dumps([b.model_dump() for b in response.content], ensure_ascii=False)}"
    )