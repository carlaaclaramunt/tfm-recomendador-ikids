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

Si el documento describe varios programas, extrae únicamente el programa \
principal o el primero que aparezca. Para procesar varios programas se \
realizarán llamadas separadas.

REGLAS DE FORMATO PARA FECHAS:
- Las fechas deben estar SIEMPRE en formato ISO 8601 completo: YYYY-MM-DD.
- Si el documento solo indica el mes (por ejemplo "January 2026"), usa el \
día 1 de ese mes (2026-01-01).
- Si solo indica el año, deja el campo en null en lugar de inventar la fecha.

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
"""

# Esquema JSON que se pasa a la API de Anthropic como tool definition.
# Lo derivamos manualmente del modelo Pydantic para tener control fino sobre
# las descripciones que ve el LLM.
_EXTRACTION_TOOL = {
    "name": "extract_programa",
    "description": (
        "Devuelve la representación estructurada de un programa de "
        "inmersión lingüística a partir del texto del documento."
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


def extract_program(
    pdf_path: Path | str,
    empresa_proveedora_hint: Optional[str] = None,
) -> Programa:
    """Extrae un Programa estructurado a partir de un PDF.

    Args:
        pdf_path: Ruta al PDF de origen.
        empresa_proveedora_hint: Nombre de la empresa proveedora si se
            conoce (por ejemplo, derivado del nombre de la carpeta).
            Se pasa al prompt para mejorar la precisión.

    Returns:
        Un objeto Programa validado.
    """
    if _API_KEY is None:
        raise RuntimeError(
            "Falta la variable de entorno ANTHROPIC_API_KEY. "
            "Copia .env.example a .env y rellénala."
        )

    pdf_path = Path(pdf_path)
    texto = read_pdf_text(pdf_path)

    # Truncamos el texto si es excesivamente largo (margen para folletos extensos)
    texto = texto[:20000]

    user_prompt = _build_user_prompt(texto, empresa_proveedora_hint)

    client = anthropic.Anthropic(api_key=_API_KEY)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        temperature=0,
        system=_SYSTEM_PROMPT,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_programa"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    payload = _extract_tool_payload(response)
    payload["fuente_documento"] = str(pdf_path)
    if empresa_proveedora_hint and not payload.get("empresa_proveedora"):
        payload["empresa_proveedora"] = empresa_proveedora_hint

    return Programa.model_validate(payload)


def _build_user_prompt(texto: str, empresa_hint: Optional[str]) -> str:
    contexto_empresa = (
        f"La empresa proveedora del documento es {empresa_hint}.\n\n"
        if empresa_hint
        else ""
    )
    return (
        f"{contexto_empresa}"
        "A continuación se incluye el texto del documento. Extrae la "
        "información del programa principal usando la tool extract_programa.\n\n"
        "=== INICIO DEL DOCUMENTO ===\n"
        f"{texto}\n"
        "=== FIN DEL DOCUMENTO ==="
    )


def _extract_tool_payload(response: anthropic.types.Message) -> dict:
    """Recupera el JSON devuelto por la tool dentro de la respuesta."""
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_programa":
            return dict(block.input)
    raise RuntimeError(
        "La respuesta del modelo no contiene la llamada esperada a "
        "extract_programa. Respuesta cruda: "
        f"{json.dumps([b.model_dump() for b in response.content], ensure_ascii=False)}"
    )