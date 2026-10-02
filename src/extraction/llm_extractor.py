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

load_dotenv(override=True)

_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Prompt externalizado para permitir A/B de versiones y diffs legibles en git.
# La versión se usa como etiqueta en los informes de evaluación: p.ej.
# "F1 = 0,875 con prompt v3" es un par reproducible mientras no se cambie
# el fichero apuntado por PROMPT_PATH.
PROMPT_VERSION = os.getenv("IKIDS_PROMPT_VERSION", "v3")
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROMPT_PATH = _PROMPTS_DIR / f"extraccion_{PROMPT_VERSION}.md"


def _cargar_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"No se encontró el prompt de extracción en {PROMPT_PATH}. "
            f"Verifica que exista el fichero o ajusta IKIDS_PROMPT_VERSION."
        ) from e


_SYSTEM_PROMPT = _cargar_system_prompt()

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
        "precio_semanal_min_eur": {
            "type": ["number", "null"], "minimum": 0,
            "description": (
                "Precio POR SEMANA en euros (opción más barata). "
                "Si el documento da un total, DIVIDE por el número de semanas."
            ),
        },
        "precio_semanal_max_eur": {
            "type": ["number", "null"], "minimum": 0,
            "description": (
                "Precio POR SEMANA en euros (opción más cara). "
                "Si el documento da un total, DIVIDE por el número de semanas."
            ),
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
        "precio_semanal_min_origen": {
            "type": ["number", "null"], "minimum": 0,
            "description": "Precio por semana en la moneda original, sin conversión",
        },
        "precio_semanal_max_origen": {
            "type": ["number", "null"], "minimum": 0,
            "description": "Precio por semana en la moneda original, sin conversión",
        },
        "fechas_inicio_recurrentes": {
            "type": ["string", "null"],
            "description": (
                "LD5 — patrón textual de recurrencia si el programa admite "
                "arranques repetidos (ej. 'Every Monday'). Null si el "
                "programa tiene fechas concretas o si no se especifica."
            ),
        },
        "cursos_especialistas": {
            "type": "array",
            "description": (
                "LD20 — modalidades especialistas del programa base "
                "(Tennis, Football, Horse Riding, etc.). NO son programas "
                "aparte; van como sub-elementos aquí."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre del curso especialista tal como aparece en el documento",
                    },
                    "actividad": {
                        "type": "string",
                        "description": "Actividad normalizada en minúsculas (tennis, football, horse riding, etc.)",
                    },
                    "horas_dedicadas": {
                        "type": ["integer", "null"], "minimum": 0,
                        "description": "Horas semanales dedicadas a la actividad, si el documento lo especifica",
                    },
                    "partnership": {
                        "type": ["string", "null"],
                        "description": "Colaboración de marca si aplica (ej. 'Active Away | Jamie Murray')",
                    },
                    "descripcion": {
                        "type": ["string", "null"],
                        "description": "Descripción breve extra si aporta información relevante",
                    },
                    "precio_adicional_semanal_eur": {
                        "type": ["number", "null"], "minimum": 0,
                        "description": (
                            "LD18 — suplemento semanal en euros que añade "
                            "esta modalidad sobre el precio base del programa. "
                            "Si el suplemento aparece como TOTAL en el doc, "
                            "divide por semanas antes de rellenar."
                        ),
                    },
                    "precio_adicional_semanal_origen": {
                        "type": ["number", "null"], "minimum": 0,
                        "description": "Suplemento semanal en la moneda original del documento",
                    },
                },
                "required": ["nombre", "actividad"],
            },
            "default": [],
        },
        "turnos": {
            "type": "array",
            "description": (
                "LD19 — turnos discretos del programa cuando se ofrece en "
                "varias sesiones separadas con misma duración. Lista vacía "
                "si el programa se ofrece en un único turno o si se puede "
                "empezar cualquier día."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "fecha_inicio": {
                        "type": "string",
                        "description": "Fecha de inicio del turno en ISO 8601 (YYYY-MM-DD)",
                    },
                    "fecha_fin": {
                        "type": "string",
                        "description": "Fecha de fin del turno en ISO 8601",
                    },
                    "nombre": {
                        "type": ["string", "null"],
                        "description": "Etiqueta del turno si el documento la especifica",
                    },
                },
                "required": ["fecha_inicio", "fecha_fin"],
            },
            "default": [],
        },
    },
    "required": ["nombre", "empresa_proveedora", "pais", "idioma"],
}

# Ampliación del esquema con la lista de evidencias por campo crítico.
# El LLM debe devolver, para cada dato numérico o de fecha que rellene, una
# CITA LITERAL del documento (fragmento_fuente), copiada carácter a carácter.
# Estas citas se verifican después contra el texto del PDF en la etapa de
# curación (`src/curation/evidence.py::verificar_evidencias`). Las citas que
# aparecen literalmente pasan a fidelidad="literal"; las que difieren
# ligeramente (OCR, espaciado) pasan a "derivado"; las que no se encuentran
# se marcan "no_verificable" y actúan como señal de posible alucinación.
_EVIDENCIA_SCHEMA = {
    "type": "object",
    "properties": {
        "campo": {
            "type": "string",
            "description": (
                "Nombre EXACTO del campo del programa al que corresponde la cita. "
                "Solo se aceptan: precio_semanal_min_eur, precio_semanal_max_eur, "
                "precio_semanal_min_origen, precio_semanal_max_origen, "
                "edad_min, edad_max, duracion_min_dias, duracion_max_dias, "
                "fecha_inicio, fecha_fin, vigencia_inicio, vigencia_fin."
            ),
        },
        "valor": {
            "type": "string",
            "description": "Valor extraído para ese campo, como cadena.",
        },
        "fragmento_fuente": {
            "type": "string",
            "description": (
                "CITA LITERAL del documento de la que sale el valor. Copia "
                "carácter a carácter la frase o expresión más corta que "
                "contiene el dato. NO parafrasees, NO traduzcas, NO añadas "
                "puntuación. Ejemplos válidos: '£950 per week', "
                "'Age range: 13 to 17', 'from 07/04 to 25/08 2026'. "
                "Si el valor no aparece literalmente sino que lo has deducido, "
                "copia la frase de la que lo deduces y marca fidelidad='inferido'."
            ),
        },
        "fidelidad": {
            "type": "string",
            "enum": ["literal", "inferido"],
            "description": (
                "'literal' si el valor aparece explícitamente en el fragmento. "
                "'inferido' si has deducido el valor a partir de una expresión "
                "cualitativa (por ejemplo 'all ages' → edad_min=0, edad_max=99)."
            ),
        },
    },
    "required": ["campo", "valor", "fragmento_fuente", "fidelidad"],
}

_PROGRAMA_SCHEMA["properties"]["evidencias"] = {
    "type": "array",
    "items": _EVIDENCIA_SCHEMA,
    "description": (
        "Para CADA campo numérico o de fecha que rellenes en el programa, "
        "añade una entrada con la cita literal del documento. Campos "
        "cubiertos: precios, edades, duraciones y fechas. Si dejas un campo "
        "a null, no añadas entrada para él. La cita debe ser verificable "
        "carácter a carácter en el texto del documento."
    ),
    "default": [],
}

# Esquema de coste adicional. Se anida DENTRO del programa (no como hermano
# de `programas` en la tool) para que el sistema lea los costes por
# programa: previamente el campo vivía como hermano y nunca se consumía,
# de modo que los ~40 líneas del system prompt dedicadas a costes se
# perdían y `Programa.costes_adicionales` llegaba siempre vacío.
_COSTE_SCHEMA = {
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
}

_PROGRAMA_SCHEMA["properties"]["costes_adicionales"] = {
    "type": "array",
    "items": _COSTE_SCHEMA,
    "description": (
        "Lista de costes adicionales asociados a ESTE programa: "
        "traslados, seguros, depósitos, servicios para menores no "
        "acompañados, pocket money, lavandería, excursiones extra, "
        "material, registration fees o suplementos. Deja lista vacía "
        "si el programa no tiene costes adicionales identificables "
        "en el documento."
    ),
    "default": [],
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
    # Truncamiento generoso para que catálogos largos (ej. Berlitz ELA 2026,
    # ~30 páginas) mantengan sus tablas de precios y anexos de alojamiento
    # dentro del contexto. 80k chars ≈ 20-25k tokens, muy dentro de límites.
    texto = texto[:80000]

    user_prompt = _build_user_prompt(texto, empresa_proveedora_hint)

    client = anthropic.Anthropic(api_key=_API_KEY)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=16384,            # cabe una lista larga (Berlitz: 12+ programas)
        temperature=0,
        system=_SYSTEM_PROMPT,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_programas"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    payload = _extract_tool_payload(response)
    programas_data = payload.get("programas", [])

    # Fallback defensivo: ocasionalmente el LLM devuelve `programas` como
    # string JSON en vez de como array directo (comportamiento observado con
    # documentos largos y schemas anidados). Lo parseamos si hace falta.
    if isinstance(programas_data, str):
        try:
            programas_data = json.loads(programas_data)
        except json.JSONDecodeError:
            programas_data = []

    # Se importa localmente para evitar el ciclo extraction ↔ curation en
    # tiempo de import: curation ya importa src.models, y models no depende
    # de curation, pero mantener la importación diferida deja claro que la
    # verificación es una etapa opcional adyacente a la extracción.
    from src.curation.evidence import verificar_evidencias

    programas: list[Programa] = []
    for prog_data in programas_data:
        # Validación defensiva: si el LLM devuelve algo que no es un dict
        # (respuesta truncada, alucinación de esquema), saltamos ese elemento
        # en vez de romper todo el PDF.
        if not isinstance(prog_data, dict):
            continue
        prog_data["fuente_documento"] = str(pdf_path)
        if empresa_proveedora_hint and not prog_data.get("empresa_proveedora"):
            prog_data["empresa_proveedora"] = empresa_proveedora_hint
        try:
            programa = Programa.model_validate(prog_data)
        except Exception as exc:  # noqa: BLE001 — mejor perder 1 programa que el PDF entero
            print(f"    ⚠ programa descartado por validación: {exc}")
            continue
        # Verificamos las evidencias del LLM contra el texto real del PDF
        # antes de anexar el programa al catálogo. Esto convierte la fidelidad
        # declarada por el modelo en fidelidad medida: literal / derivado /
        # no_verificable, según si la cita aparece en el texto (LD24).
        programa = verificar_evidencias(programa, texto)
        programas.append(programa)

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