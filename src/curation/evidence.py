"""Trazabilidad verificable de la extracción (LD24).

Este módulo gestiona el pilar de explicabilidad basada en trazabilidad
del sistema. Distingue dos etapas:

1. `verificar_evidencias(programa, texto_pdf)`: toma las citas literales
   que el LLM ha declarado en el campo `evidencias` del programa y
   comprueba, para cada una, si aparece REALMENTE en el texto del
   documento. La fidelidad declarada por el modelo se reemplaza por
   una fidelidad medida:

     - "literal"        → la cita aparece carácter a carácter
     - "derivado"       → la cita es aproximada (similitud > 0.9)
     - "no_verificable" → la cita no se encuentra (posible alucinación)
     - "inferido"       → el LLM declaró inferido y la cita aparece
                          en el texto (se preserva su semántica)

2. `completar_evidencias_derivadas(programa)`: añade evidencias
   sintéticas para campos calculados por el propio sistema (edades
   universales 0-99, precios convertidos a EUR desde otra moneda) que
   no vienen del LLM sino de reglas de curación. Se marcan como
   "inferido" o "derivado" explícitamente.

La métrica agregable `tasa_trazabilidad_literal(programas)` calcula
el porcentaje de evidencias de campos críticos con fidelidad "literal"
sobre el total. Es la métrica reportable en la memoria como resultado
propio del sistema, complementaria a H1 y H2.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable

from src.models import EvidenciaCampo, FidelidadExtraccion, Programa


CAMPOS_CRITICOS = [
    "precio_semanal_min_eur",
    "precio_semanal_max_eur",
    "precio_semanal_min_origen",
    "precio_semanal_max_origen",
    "edad_min",
    "edad_max",
    "duracion_min_dias",
    "duracion_max_dias",
    "fecha_inicio",
    "fecha_fin",
    "vigencia_inicio",
    "vigencia_fin",
]

# Umbral de similitud por encima del cual una cita no exacta se acepta como
# "derivado". Cubre diferencias menores por OCR, saltos de línea, espaciado
# de tablas o normalización de puntuación introducida por pdfplumber.
UMBRAL_DERIVADO = 0.90


# ---------------------------------------------------------------------------
# Verificación de citas contra el texto del documento
# ---------------------------------------------------------------------------


def verificar_evidencias(programa: Programa, texto_pdf: str) -> Programa:
    """Verifica cada evidencia del programa contra el texto del PDF.

    Sustituye la fidelidad declarada por el LLM por la fidelidad medida:
    la cita se busca en el texto, y en función de si aparece literal,
    aproximada o inexistente se le asigna un valor de FidelidadExtraccion.

    Args:
        programa: Programa recién extraído por el LLM, con `evidencias`
            rellenadas por el propio modelo (cada una con `fragmento_fuente`
            supuestamente literal).
        texto_pdf: Texto crudo del documento tal como lo devolvió el
            lector de PDF (misma fuente que se envió al LLM).

    Returns:
        El programa con las evidencias actualizadas. La lista puede
        contener menos elementos si alguna cita venía vacía.
    """
    texto_norm = _normalizar(texto_pdf)
    evidencias_verificadas: list[EvidenciaCampo] = []

    for ev in programa.evidencias:
        cita = (ev.fragmento_fuente or "").strip()
        if not cita:
            # Sin cita no hay nada que verificar; el LLM no cumplió el
            # contrato del prompt. Se preserva la evidencia pero con
            # fidelidad no_verificable para que sea auditable.
            evidencias_verificadas.append(
                ev.model_copy(update={"fidelidad": "no_verificable"})
            )
            continue

        cita_norm = _normalizar(cita)
        fidelidad = _clasificar_cita(cita_norm, texto_norm, ev.fidelidad)

        evidencias_verificadas.append(
            ev.model_copy(
                update={
                    "fidelidad": fidelidad,
                    "documento_fuente": ev.documento_fuente or programa.fuente_documento,
                }
            )
        )

    return programa.model_copy(update={"evidencias": evidencias_verificadas})


def _clasificar_cita(
    cita_norm: str,
    texto_norm: str,
    fidelidad_declarada: FidelidadExtraccion,
) -> FidelidadExtraccion:
    """Determina la fidelidad de una cita comparándola con el texto."""
    if not cita_norm:
        return "no_verificable"

    if cita_norm in texto_norm:
        # Preservamos "inferido" cuando el LLM lo declaró y la cita
        # aparece: el valor no es literal aunque la frase lo sea (por
        # ejemplo "all ages" → edad_min=0).
        if fidelidad_declarada == "inferido":
            return "inferido"
        return "literal"

    # Búsqueda por ventana deslizante: se busca la ventana del texto de
    # longitud parecida a la cita que maximiza la similitud. Es O(n) sobre
    # el número de posiciones candidatas, que es aceptable para PDFs de
    # hasta 80k caracteres (~50ms).
    similitud = _mejor_similitud(cita_norm, texto_norm)
    if similitud >= UMBRAL_DERIVADO:
        return "derivado"

    return "no_verificable"


def _normalizar(texto: str) -> str:
    """Normaliza un texto para comparación robusta.

    Colapsa espacios en blanco y baja a minúsculas. Mantiene la
    puntuación y los símbolos de moneda intactos porque son
    discriminantes reales (£950 no es lo mismo que 950).
    """
    return " ".join(texto.lower().split())


def _mejor_similitud(cita: str, texto: str) -> float:
    """Busca la ventana del texto más parecida a `cita` y devuelve el ratio.

    Estrategia: extrae ventanas del texto de longitud ±20% respecto a la
    cita en los alrededores de cada aparición de la primera palabra de la
    cita. Si la cita no comparte ninguna palabra con el texto, devuelve 0.
    """
    if len(cita) < 4:
        return 0.0

    palabras = cita.split()
    if not palabras:
        return 0.0

    pivote = max(palabras, key=len)
    if len(pivote) < 3:
        return 0.0

    # Ancho de ventana ≈ longitud de la cita: comparamos como si la cita se
    # correspondiera con un segmento del texto de tamaño similar, no con un
    # bloque grande de contexto.
    ancho = len(cita)
    mejor = 0.0
    start = 0
    while True:
        pos = texto.find(pivote, start)
        if pos < 0:
            break
        # Deslizamos la ventana en varios offsets alrededor del pivote para
        # cubrir los casos en que la cita empieza antes o después del pivote.
        for offset in range(-ancho, len(pivote) + 1, max(1, ancho // 4)):
            ini = max(0, pos + offset)
            fin = min(len(texto), ini + ancho)
            ventana = texto[ini:fin]
            ratio = SequenceMatcher(None, cita, ventana).ratio()
            if ratio > mejor:
                mejor = ratio
                if mejor >= 0.99:
                    return mejor
        start = pos + len(pivote)

    return mejor


# ---------------------------------------------------------------------------
# Complemento: evidencias derivadas del sistema (no del LLM)
# ---------------------------------------------------------------------------


def generar_evidencias(programa: Programa) -> Programa:
    """Añade evidencias derivadas del propio sistema, no del LLM.

    Cubre los casos en que un valor del programa NO procede literalmente
    del documento sino de una regla de curación posterior a la extracción:

    - Edades 0-99 provenientes de expresiones cualitativas ("all ages").
    - Precios convertidos a EUR desde otra moneda (aplicando tasas fijas).

    Estas evidencias se añaden solo si el LLM no ha aportado ya una
    evidencia para ese campo. En ese caso se marca fidelidad="inferido"
    o "derivado" con un fragmento_fuente descriptivo (no una cita).
    """
    evidencias_existentes = {ev.campo for ev in programa.evidencias}
    nuevas: list[EvidenciaCampo] = []

    if (
        programa.edad_min == 0
        and programa.edad_max == 99
        and "edad_min" not in evidencias_existentes
    ):
        for campo, valor in (("edad_min", 0), ("edad_max", 99)):
            nuevas.append(
                EvidenciaCampo(
                    campo=campo,
                    valor=str(valor),
                    fidelidad="inferido",
                    fragmento_fuente=(
                        "Edad inferida a partir de una expresión cualitativa "
                        "como 'all ages' o equivalente."
                    ),
                    documento_fuente=programa.fuente_documento,
                )
            )

    if (
        programa.moneda_origen
        and programa.moneda_origen != "EUR"
        and "precio_semanal_min_eur" not in evidencias_existentes
        and programa.precio_semanal_min_eur is not None
    ):
        nuevas.append(
            EvidenciaCampo(
                campo="precio_semanal_min_eur",
                valor=str(programa.precio_semanal_min_eur),
                fidelidad="derivado",
                fragmento_fuente=(
                    f"Valor convertido a EUR desde {programa.moneda_origen} "
                    "aplicando tasa fija del sistema."
                ),
                documento_fuente=programa.fuente_documento,
            )
        )

    if nuevas:
        return programa.model_copy(
            update={"evidencias": [*programa.evidencias, *nuevas]}
        )
    return programa


# ---------------------------------------------------------------------------
# Métrica agregada de trazabilidad
# ---------------------------------------------------------------------------


def tasa_trazabilidad_literal(programas: Iterable[Programa]) -> dict[str, float | int]:
    """Calcula el % de evidencias de campos críticos con fidelidad 'literal'.

    Reporta:
      - `n_evidencias`: total de evidencias de campos críticos en el catálogo.
      - `n_literales`: cuántas están verificadas carácter a carácter.
      - `n_derivadas`: cuántas coinciden aproximadamente (>0.9).
      - `n_no_verificables`: cuántas no aparecen en el texto (posibles
        alucinaciones o fragmentos mal declarados por el LLM).
      - `n_inferidas`: cuántas son deducciones explícitas del modelo.
      - `tasa_literal`: proporción de evidencias literales sobre el total.
      - `tasa_verificable`: proporción literal + derivado sobre el total.

    La `tasa_verificable` es la métrica reportable como resultado propio
    del sistema junto a H1 y H2: mide qué fracción del catálogo tiene una
    justificación textual localizable en el documento origen.
    """
    n = 0
    literales = 0
    derivadas = 0
    no_verificables = 0
    inferidas = 0

    for programa in programas:
        for ev in programa.evidencias:
            if ev.campo not in CAMPOS_CRITICOS:
                continue
            n += 1
            if ev.fidelidad == "literal":
                literales += 1
            elif ev.fidelidad == "derivado":
                derivadas += 1
            elif ev.fidelidad == "no_verificable":
                no_verificables += 1
            elif ev.fidelidad == "inferido":
                inferidas += 1

    return {
        "n_evidencias": n,
        "n_literales": literales,
        "n_derivadas": derivadas,
        "n_no_verificables": no_verificables,
        "n_inferidas": inferidas,
        "tasa_literal": (literales / n) if n else 0.0,
        "tasa_verificable": ((literales + derivadas) / n) if n else 0.0,
    }
