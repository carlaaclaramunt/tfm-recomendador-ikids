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
            "duracion_dias": {"type": ["integer", "null"], "minimum": 1},
            "precio_eur": {"type": ["number", "null"], "minimum": 0},
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