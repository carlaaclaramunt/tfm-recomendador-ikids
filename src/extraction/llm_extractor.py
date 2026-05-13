"""Extracción estructurada de programas mediante LLM.

Pipeline en dos pasadas para manejar documentos multi-programa (LD1) y
recombinar información distribuida en secciones no contiguas (LD2):

1. Pasada 1 — ``_listar_programas``: el modelo identifica TODOS los
   programas comerciales distintos descritos en el documento. Un mismo
   programa con varias duraciones, precios o turnos NO genera entradas
   distintas (eso son variantes y se tratan dentro del Programa).

2. Pasada 2 — ``_extraer_programa_completo``: para cada programa
   identificado se hace una llamada que rellena el esquema completo,
   permitiendo al modelo combinar la "ficha de programa" con las
   secciones transversales del documento (lista de precios global,
   alojamiento, calendario, etc.).

Se usa caché de prompt (cache_control ephemeral) sobre el texto del
documento, de forma que las múltiples llamadas de pasada 2 sobre el
mismo PDF reutilicen el contexto.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import anthropic
from dotenv import load_dotenv

from src.extraction.pdf_reader import read_pdf_text
from src.models import Programa

load_dotenv()

_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
_API_KEY = os.getenv("ANTHROPIC_API_KEY")
_MAX_TEXT_CHARS = 20000


# ---------------------------------------------------------------------------
# Pasada 1: identificación de programas en el documento
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_LISTAR = """\
Eres un experto en analizar documentación comercial de programas de \
inmersión lingüística (folletos, catálogos, fichas de producto, listas \
de precios).

Tu tarea es identificar TODOS los programas distintos descritos en el \
documento que se te proporcione.

DEFINICIÓN DE "PROGRAMA":
- Un programa es una oferta comercial diferenciada con su propio nombre \
(ejemplos: "General English", "Business English", "Youth Summer Camp", \
"Total Immersion").
- Un mismo programa con varias duraciones, varios precios, varios turnos \
o varias temporadas (low season / high season) NO son programas \
distintos: son variantes del mismo y se tratarán juntos.
- Un programa con varios tipos de alojamiento simultáneos tampoco son \
programas distintos.

CRITERIOS DE GRANULARIDAD:
- Si el documento describe un único programa, devuelve una lista con un \
único elemento.
- Si el documento es un catálogo completo con varios cursos (típico de \
academias permanentes), devuelve un elemento por cada curso distinto que \
encuentres.
- Si el documento es una hoja de tarifas (B2B) de un único curso con \
varios precios por temporada o duración, devuelve un único elemento.
"""

_TOOL_LISTAR = {
    "name": "listar_programas",
    "description": (
        "Devuelve la lista de programas distintos descritos en el documento."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "programas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "nombre": {
                            "type": "string",
                            "description": (
                                "Nombre comercial exacto del programa, tal "
                                "como aparece en el documento."
                            ),
                        },
                        "descripcion_breve": {
                            "type": "string",
                            "description": (
                                "Una frase breve que distinga el programa "
                                "del resto: a quién va dirigido, "
                                "característica principal, sección del "
                                "documento donde aparece, etc."
                            ),
                        },
                    },
                    "required": ["nombre", "descripcion_breve"],
                },
            }
        },
        "required": ["programas"],
    },
}


# ---------------------------------------------------------------------------
# Pasada 2: extracción del esquema completo del programa concreto
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_EXTRAER = """\
Eres un asistente experto en extraer información estructurada sobre \
programas de inmersión lingüística a partir de documentación comercial \
heterogénea (folletos, catálogos, fichas de producto, listas de precios).

Se te indica el nombre concreto del programa que debes extraer. El \
documento puede contener varios programas y también secciones \
transversales (lista de precios global, sección de alojamiento, \
calendario común, etc.) que aplican a varios programas a la vez.

REGLA CLAVE — INFORMACIÓN DISTRIBUIDA:
Para rellenar el esquema, busca en TODO el documento. La información del \
programa indicado puede estar repartida en secciones no contiguas: una \
"ficha de programa" con descripción general, una lista de precios \
global, una sección de alojamiento transversal, un calendario, etc. NO \
te limites a la sección que menciona el programa por su nombre: combina \
lo que veas allí con la información transversal del documento. Si la \
lista de precios o el calendario aplica a varios programas, también \
aplica al que se te pide.

Cuando un dato no aparezca en NINGUNA parte del documento, deja el \
campo en null en lugar de inventarlo. Es preferible una respuesta con \
campos faltantes a una respuesta con datos inventados.

REGLAS DE FORMATO PARA FECHAS:
- Las fechas deben estar SIEMPRE en formato ISO 8601: YYYY-MM-DD.
- Si el documento solo indica el mes ("January 2026"), usa el día 1.
- Si solo indica el año, deja el campo en null.

REGLAS DE FORMATO PARA DURACIÓN:
- Duración fija ("7-day camp", "2-week intensive"): mismo valor para \
duracion_min_dias y duracion_max_dias.
- Duración configurable ("from 1 to 12 weeks"): rango completo en días \
(min=7, max=84 en ese ejemplo).
- IMPORTANTE: cuando el documento muestre precios "por semana" / \
"per week", esa es la UNIDAD DE PRECIO, NO la duración del programa.
- Si la duración no se especifica de ninguna forma, ambos campos en null.

REGLAS DE FORMATO PARA PRECIO:
- Único precio claro: mismo valor para precio_min_eur y precio_max_eur.
- Varios precios (por temporada, edad, habitación, semanas): el menor en \
precio_min_eur y el mayor en precio_max_eur.
- Otras monedas: convierte a euros con tasa aproximada \
(1 USD = 0.92 EUR, 1 GBP = 1.17 EUR).
- Si no aparece, ambos campos en null.

REGLAS DE FORMATO PARA EDAD:
- Si el documento describe varios públicos, céntrate en el rango de edad \
asociado AL PROGRAMA INDICADO específicamente.
- "Adults only" / "for adults": edad_min=18, edad_max=null.
- "All ages" / "kids, teens, adults" / "ideal for everyone": edad_min=0, \
edad_max=99 (preservar la semántica de aptitud universal).
"""

_TOOL_EXTRAER = {
    "name": "extract_programa",
    "description": (
        "Devuelve la representación estructurada del programa indicado, "
        "combinando información de toda el documento."
    ),
    "input_schema": {
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
                "type": ["integer", "null"],
                "minimum": 1,
                "description": "Duración mínima del programa en días",
            },
            "duracion_max_dias": {
                "type": ["integer", "null"],
                "minimum": 1,
                "description": "Duración máxima del programa en días",
            },
            "precio_min_eur": {
                "type": ["number", "null"],
                "minimum": 0,
                "description": "Precio mínimo en euros (opción más barata)",
            },
            "precio_max_eur": {
                "type": ["number", "null"],
                "minimum": 0,
                "description": "Precio máximo en euros (opción más cara)",
            },
            "tipo_alojamiento": {
                "type": ["string", "null"],
                "enum": [
                    "familia",
                    "residencia",
                    "hotel",
                    "campamento",
                    "otro",
                    None,
                ],
            },
            "fecha_inicio": {"type": ["string", "null"]},
            "fecha_fin": {"type": ["string", "null"]},
            "acreditaciones": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
            },
            "idioma_documento_origen": {
                "type": ["string", "null"],
                "enum": ["es", "en", "ca", "fr", "de", "otro", None],
            },
        },
        "required": ["nombre", "empresa_proveedora", "pais", "idioma"],
    },
}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def extract_programs(
    pdf_path: Path | str,
    empresa_proveedora_hint: Optional[str] = None,
) -> list[Programa]:
    """Extrae todos los programas descritos en un PDF.

    Un mismo PDF puede contener varios programas (caso típico de un
    catálogo completo). Se ejecuta en dos pasadas: primero se identifican
    los programas presentes y después se extrae el esquema de cada uno
    combinando la ficha específica con las secciones transversales del
    documento.

    Args:
        pdf_path: Ruta al PDF de origen.
        empresa_proveedora_hint: Nombre de la empresa proveedora si se
            conoce (por ejemplo, derivado del nombre de la carpeta).

    Returns:
        Lista de objetos Programa validados. Vacía si el modelo no
        identifica ningún programa en el documento.
    """
    if _API_KEY is None:
        raise RuntimeError(
            "Falta la variable de entorno ANTHROPIC_API_KEY. "
            "Copia .env.example a .env y rellénala."
        )

    pdf_path = Path(pdf_path)
    texto = read_pdf_text(pdf_path)[:_MAX_TEXT_CHARS]

    client = anthropic.Anthropic(api_key=_API_KEY)

    identificados = _listar_programas(client, texto, empresa_proveedora_hint)
    if not identificados:
        return []

    programas: list[Programa] = []
    for info in identificados:
        payload = _extraer_programa_completo(
            client, texto, info, empresa_proveedora_hint
        )
        payload["fuente_documento"] = str(pdf_path)
        if empresa_proveedora_hint and not payload.get("empresa_proveedora"):
            payload["empresa_proveedora"] = empresa_proveedora_hint
        programas.append(Programa.model_validate(payload))

    return programas


# ---------------------------------------------------------------------------
# Pasada 1
# ---------------------------------------------------------------------------


def _listar_programas(
    client: anthropic.Anthropic,
    texto: str,
    empresa_hint: Optional[str],
) -> list[dict[str, str]]:
    contexto_empresa = (
        f"La empresa proveedora del documento es {empresa_hint}.\n\n"
        if empresa_hint
        else ""
    )
    user_prompt = (
        f"{contexto_empresa}"
        "A continuación se incluye el texto del documento. Identifica TODOS "
        "los programas distintos descritos en él usando la tool "
        "listar_programas.\n\n"
        "=== INICIO DEL DOCUMENTO ===\n"
        f"{texto}\n"
        "=== FIN DEL DOCUMENTO ==="
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        temperature=0,
        system=_SYSTEM_PROMPT_LISTAR,
        tools=[_TOOL_LISTAR],
        tool_choice={"type": "tool", "name": "listar_programas"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    payload = _extract_tool_payload(response, "listar_programas")
    return list(payload.get("programas", []))


# ---------------------------------------------------------------------------
# Pasada 2
# ---------------------------------------------------------------------------


def _extraer_programa_completo(
    client: anthropic.Anthropic,
    texto: str,
    info: dict[str, str],
    empresa_hint: Optional[str],
) -> dict[str, Any]:
    contexto_empresa = (
        f"La empresa proveedora del documento es {empresa_hint}.\n\n"
        if empresa_hint
        else ""
    )

    # El prefijo (contexto + texto del documento) es idéntico en todas las
    # llamadas de pasada 2 sobre este PDF: lo marcamos como cacheable para
    # abaratar el caso multi-programa (caso Berlitz: 13 programas → un solo
    # coste de prompt).
    prefijo_cacheable = (
        f"{contexto_empresa}"
        "A continuación tienes el texto íntegro del documento. Al final se "
        "te indica qué programa concreto debes extraer.\n\n"
        "=== INICIO DEL DOCUMENTO ===\n"
        f"{texto}\n"
        "=== FIN DEL DOCUMENTO ==="
    )

    instruccion_programa = (
        "Extrae el siguiente programa del documento, combinando la "
        "información de su ficha específica con las secciones "
        "transversales (precios globales, alojamiento, calendario, etc.) "
        "que apliquen.\n\n"
        f"Nombre del programa: {info.get('nombre', '')}\n"
        f"Descripción breve: {info.get('descripcion_breve', '')}"
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        temperature=0,
        system=_SYSTEM_PROMPT_EXTRAER,
        tools=[_TOOL_EXTRAER],
        tool_choice={"type": "tool", "name": "extract_programa"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prefijo_cacheable,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": instruccion_programa},
                ],
            }
        ],
    )

    return _extract_tool_payload(response, "extract_programa")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _extract_tool_payload(
    response: anthropic.types.Message,
    tool_name: str,
) -> dict[str, Any]:
    """Recupera el JSON devuelto por la tool dentro de la respuesta."""
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return dict(block.input)
    raise RuntimeError(
        f"La respuesta del modelo no contiene la llamada esperada a "
        f"{tool_name}. Respuesta cruda: "
        f"{json.dumps([b.model_dump() for b in response.content], ensure_ascii=False)}"
    )
