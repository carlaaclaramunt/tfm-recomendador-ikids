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

IMPORTANTE — LD20: los CURSOS ESPECIALISTAS (Specialist Courses tipo
Football, Tennis, Horse Riding, etc.) NO son programas independientes,
son MODALIDADES del programa base. Aunque el documento los liste como
secciones separadas, extrae el programa base UNA sola vez y añade los
especialistas dentro del campo `cursos_especialistas` de ese programa
base. Ejemplo Millfield: NO extraigas "Millfield Summer Programme",
"Millfield Specialist Course Tennis" y "Millfield Specialist Course
Football" como tres programas — extrae UN programa "Millfield School
Summer Programme" con dos cursos_especialistas [Tennis, Football].

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

REGLA LD19 — TURNOS DISCRETOS:
Cuando el documento indique que el programa se ofrece en DOS O MÁS
turnos separados con la misma duración (típico en summer camps y
programas cerrados), extrae cada turno como una entrada en el campo
`turnos` con su fecha_inicio y fecha_fin propias.

- Ejemplo NSX Woodbridge 2026: "Turno 1: 5-18 julio; Turno 2: 19 julio
  - 1 agosto" → turnos: [
    {fecha_inicio: "2026-07-05", fecha_fin: "2026-07-18"},
    {fecha_inicio: "2026-07-19", fecha_fin: "2026-08-01"}
  ]
- El programa base MANTIENE `fecha_inicio`/`fecha_fin` como la ventana
  global (min de inicios y max de fines): 2026-07-05 y 2026-08-01.
- Si el programa se ofrece en un ÚNICO turno, deja `turnos` como
  lista vacía y usa solo fecha_inicio/fecha_fin.
- No confundir con LD5 (recurrente): "Every Monday" NO es una lista de
  turnos sino un patrón abierto; va en `fechas_inicio_recurrentes`.

REGLA LD5 — FECHAS DE INICIO RECURRENTES:
Cuando el documento indique que el programa admite arranques repetidos
periódicos (ej. "Every Monday", "Starts weekly", "Cualquier lunes de
enero a mayo", "Sessions begin every second Sunday"), rellena el campo
`fechas_inicio_recurrentes` con el patrón textual EN LA FORMA MÁS
COMPACTA POSIBLE, preservando la información:
- "Every Monday" → fechas_inicio_recurrentes: "Every Monday"
- "Cualquier lunes de enero a mayo" → fechas_inicio_recurrentes: "Cualquier lunes (enero-mayo)"
- Si además el documento indica una ventana de vigencia, rellena también
  vigencia_inicio/vigencia_fin, pero fecha_inicio/fecha_fin quedan null.
Si no hay recurrencia explícita, deja `fechas_inicio_recurrentes` null.

REGLAS DE FORMATO PARA CURSOS ESPECIALISTAS (LD20):
El campo `cursos_especialistas` recoge modalidades específicas del
programa base. Cada modalidad tiene nombre, actividad principal, horas
semanales dedicadas si aparecen, y partnership si el documento lo cita.

- Extrae SIEMPRE los cursos especialistas del programa base cuando el
  documento los liste, incluso si son secciones separadas del PDF.
- NO crees un programa aparte para cada especialista. Solo el programa
  base va como entrada en `programas`.
- Nombre: texto tal cual del documento (ej. "Specialist Course Tennis").
- Actividad: palabra clave normalizada en minúsculas (ej. "tennis",
  "football", "horse riding", "surf").
- Horas dedicadas: número entero de horas semanales si aparece en el
  doc (ej. "20 hours of tennis coaching" → 20). Si no aparece, null.
- Partnership: si el documento cita colaboración con marca externa
  (ej. "Active Away | Jamie Murray Tennis Programme"), captúrala.
  Si no, null.
- Precio adicional semanal (LD18): si la modalidad conlleva un
  suplemento sobre la tarifa base del programa (ej. "English+ Horse
  Riding: base + £565", "English+ Tennis: base + £600"), calcula el
  suplemento POR SEMANA y rellena `precio_adicional_semanal_eur` en
  euros y `precio_adicional_semanal_origen` en la moneda original.
  Cuando el suplemento aparece como TOTAL (£565 para el programa
  entero de 2 semanas), divide entre las semanas del programa:
  £565/2 = £282.5/sem, en EUR £282.5 × 1.17 = 330.5 €/sem.
  Si la modalidad no tiene suplemento, deja los dos campos null.

IMPORTANTE — cuando existen variantes con suplemento, la tarifa
`precio_semanal_max_eur` del programa BASE debe reflejar el máximo
efectivo posible: precio semanal base + suplemento más caro. Si el
base son 1720 €/sem y la variante Tennis añade +351 €/sem,
precio_semanal_max_eur del programa debe ser 2071 €/sem, no 1720.
Esto asegura que el rango de precios del programa cubre todas las
opciones que el cliente puede elegir.

Ejemplo Millfield: el documento describe Summer Programme como programa
base y luego dedica secciones a "Specialist Course Tennis (Active Away
| Jamie Murray) — 20 hours/week" y "Specialist Course Football — 30
hours/week". Extracción esperada: 1 programa base con
cursos_especialistas=[
  {nombre: "Specialist Course Tennis", actividad: "tennis",
   horas_dedicadas: 20, partnership: "Active Away | Jamie Murray"},
  {nombre: "Specialist Course Football", actividad: "football",
   horas_dedicadas: 30, partnership: null}
].

Si no hay cursos especialistas, deja la lista vacía.

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

REGLAS DE FORMATO PARA PRECIO (NORMALIZADO A €/SEMANA):
Los campos precio_semanal_min_eur y precio_semanal_max_eur representan
SIEMPRE el precio POR SEMANA en euros. Nunca el precio total del programa.
Debes hacer la conversión necesaria antes de rellenar los campos:

- Si el documento da el precio POR SEMANA (por ejemplo "€232 per week",
  "£450/week", "por semana 300€"), úsalo directamente como precio_semanal.
- Si el documento da el precio TOTAL del programa completo (por ejemplo
  "€1992 for 1 week", "€3701 for 2 weeks", "£2940 for the 2-week programme"),
  DIVIDE entre el número de semanas del programa: 1992/1 = 1992€/sem,
  3701/2 = 1850,50€/sem, £2940/2 = £1470/sem.
- Si hay varias opciones (temporadas, duraciones, variantes, alojamientos)
  con distinto precio por semana, marca el MENOR en precio_semanal_min y el
  MAYOR en precio_semanal_max. Ejemplo DBS: opciones 1992€/sem (1 semana),
  1850,5€/sem (2 semanas), 1878,4€/sem (5 semanas) → min=1850,5, max=1992.
- Si el precio total viene con desglose base + suplementos (ej. "1992€ para
  la primera semana + 1850€ cada semana adicional"), calcula el mínimo
  €/semana usando la opción MÁS LARGA (donde el marginal domina) y el
  máximo €/semana usando la opción MÁS CORTA (donde la base domina).
- Si el precio aparece en otra moneda (USD, GBP), primero calcula el
  €/semana en la moneda original, luego conviértelo a euros con tasa
  aproximada (1 USD = 0.92 EUR, 1 GBP = 1.17 EUR).
- Si el precio no aparece, deja ambos campos null.

PRESERVACIÓN DEL VALOR ORIGINAL:
- Rellena también precio_semanal_min_origen y precio_semanal_max_origen con
  los valores POR SEMANA en la moneda original antes de convertir a EUR.
- Si moneda_origen es EUR, precio_semanal_*_origen == precio_semanal_*_eur.

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

REGLAS DE FORMATO PARA ACREDITACIONES:
El campo acreditaciones recoge certificaciones, licencias y sellos de
calidad mencionados en el documento (sea del centro, del profesorado o
de las instalaciones). Busca ACTIVAMENTE las acreditaciones, no asumas
que si no se mencionan no existen — suelen aparecer en pies de página,
secciones "About us", "Quality", "Certifications" o junto a fotos del
personal y de las instalaciones.

Ejemplos de acreditaciones que pueden aparecer en este corpus:
- Acreditaciones de profesorado: TEFL, TESOL, CELTA, DELTA, UEFA A,
  UEFA Pro, UEFA B.
- Acreditaciones de centro y escuelas de idiomas: British Council (BC),
  EAQUALS, IALC, English UK, Quality English, ALTO, Bildungsurlaub.
- Acreditaciones de examen y preparación: IELTS, Cambridge (FCE, CAE,
  CPE), TOEFL iBT, TOEIC, Trinity, Pearson PTE.
- Acreditaciones de instalaciones deportivas: FIFA, FAI (Football
  Association of Ireland), LTA (Lawn Tennis Association).
- Acreditaciones propias del proveedor: Berlitz Certificate.

Reglas:
- Extrae cada acreditación como un string corto y reconocible (ej.
  "TEFL", "UEFA Pro", "IELTS"). NO incluyas la descripción larga.
- Si el documento menciona "TEFL certified teachers", basta con "TEFL".
- Si encuentras varias, lístalas todas, sin duplicar.
- Si el documento no menciona ninguna acreditación, deja la lista vacía.
- No inventes acreditaciones que no estén en el documento.

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
- Identifica la moneda de los precios (EUR, GBP, USD, CHF u OTRO) y rellena
  moneda_origen.
- Rellena precio_semanal_min_origen y precio_semanal_max_origen con los
  valores POR SEMANA en la moneda del documento (aplicando la normalización
  a semana descrita arriba, pero SIN conversión de moneda).
- Rellena precio_semanal_min_eur y precio_semanal_max_eur con los mismos
  valores por semana ya CONVERTIDOS a euros (1 USD = 0,92 EUR, 1 GBP = 1,17 EUR).
- Si el documento no especifica moneda, asume EUR.

COHERENCIA ENTRE EUR Y ORIGEN:
- Si moneda_origen == "EUR", precio_semanal_*_origen y precio_semanal_*_eur
  tienen exactamente los mismos valores.
- Si moneda_origen es otra, aplica la tasa de conversión indicada.
  
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

## EVIDENCIAS DE TRAZABILIDAD (obligatorio para campos numéricos)

Para CADA campo numérico o de fecha que rellenes en un programa (precios,
edades, duraciones, fechas de programa y fechas de vigencia), añade una
entrada al array `evidencias` con la CITA LITERAL del documento de la que
sale ese valor. Reglas estrictas:

1. Copia la cita CARÁCTER A CARÁCTER, tal como aparece en el documento.
   No parafrasees, no traduzcas, no normalices puntuación, no añadas
   espacios ni los quites. La cita debe poder encontrarse por búsqueda
   textual exacta en el documento original.

2. Escoge el fragmento MÁS CORTO que contiene el dato. Por ejemplo, si
   el precio es 950 £/semana y el documento dice "Standard tuition:
   £950 per week including all materials", copia solo "£950 per week".

3. Si el valor está DEDUCIDO de una expresión cualitativa (ej. "all
   ages" → edad_min=0, edad_max=99) copia la expresión de la que lo
   deduces y marca fidelidad="inferido". Si el valor aparece
   explícitamente marca fidelidad="literal".

4. Si un campo queda a null en el programa, NO añadas evidencia para él.

5. Para precios normalizados a €/semana desde otra moneda o desde un
   total del programa, copia la cita ORIGINAL (ej. "$3,600 for 4 weeks")
   y marca fidelidad="literal". La conversión posterior se documenta en
   otro lugar del sistema.

Ejemplo completo:

  Documento contiene: "Age: 13-17 · £950/week · from 07/04 to 25/08 2026"
  Programa extraído: edad_min=13, edad_max=17,
                     precio_semanal_min_eur=1112 (950 GBP × 1.17),
                     fecha_inicio=2026-04-07, fecha_fin=2026-08-25

  evidencias = [
    {"campo": "edad_min", "valor": "13",
     "fragmento_fuente": "Age: 13-17", "fidelidad": "literal"},
    {"campo": "edad_max", "valor": "17",
     "fragmento_fuente": "Age: 13-17", "fidelidad": "literal"},
    {"campo": "precio_semanal_min_eur", "valor": "1112",
     "fragmento_fuente": "£950/week", "fidelidad": "literal"},
    {"campo": "fecha_inicio", "valor": "2026-04-07",
     "fragmento_fuente": "from 07/04 to 25/08 2026", "fidelidad": "literal"},
    {"campo": "fecha_fin", "valor": "2026-08-25",
     "fragmento_fuente": "from 07/04 to 25/08 2026", "fidelidad": "literal"},
  ]

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