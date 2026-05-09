# Decisiones de diseño

## Arquitectura general
### Pipeline modular en tres subsistemas
[Por qué módulos: trazabilidad académica, reemplazabilidad, hipótesis 
H1/H2/H3 cada una mapeada a un subsistema]

## Subsistema de extracción
### Uso de Anthropic Tools API en lugar de prompt JSON
[Por qué: estructura forzada por el modelo, reduce errores de parseo,
validación posterior con Pydantic actúa como red de seguridad]

### OCR como fallback, no como entrada principal
[Por qué: la mayoría de PDFs son nativos, OCR solo cuando es necesario, 
ahorra tiempo de procesamiento]

### Decisión de modelar duración y precio como rangos
[Por qué: la documentación describe rangos de elección del cliente, 
forzar un único valor introduce sesgos sistemáticos en el filtrado]

## Subsistema de recomendación
### Suma ponderada como punto de partida
[Por qué: simplicidad, transparencia, suficiente para validar el 
pipeline antes de migrar a TOPSIS o BWM]

### Función de duración con base 0.7 + bonus por cobertura
[El párrafo justificativo que te di antes]

## Subsistema de explicabilidad
### No usar LLM para generar explicaciones
[Por qué: las explicaciones se construyen a partir de la trazabilidad 
del recomendador, no se generan por un modelo. Garantiza fidelidad y 
encaja con la hipótesis H3 del proyecto]

## Lecciones del análisis manual de la iteración 03

### LD1 — Documentos multi-programa
Una proporción significativa de la documentación describe múltiples 
programas en un único PDF (caso Berlitz: 13+ cursos en un solo 
folleto). El sistema actual extrae solo uno por documento, lo que 
infrarrepresenta a algunas empresas en el catálogo. Solución prevista 
para iteraciones futuras: cambiar el extractor a `list[Programa]` 
por documento.

### LD2 — Información distribuida en páginas no contiguas
Los catálogos completos suelen separar la "ficha de programa" 
(características generales) de páginas transversales con precios, 
alojamiento y términos. El LLM, ante un texto largo, no siempre 
relaciona ambas partes. Solución posible: pasar al LLM dos pasadas, 
una para identificar programas y otra para enriquecerlos con datos 
transversales del documento.

### LD3 — Tipos de alojamiento múltiples
El esquema actual asume un único tipo de alojamiento por programa. 
La realidad es que muchos programas ofrecen varias opciones 
simultáneas (familia + apartamento + residencia). Cambio previsto: 
`tipo_alojamiento` pasa de `Optional[Literal[...]]` a `list[Literal[...]]`.

### LD4 — Edades expresadas cualitativamente
Documentos que indican "all ages", "kids, teens, adults" o "ideal 
for everyone" pierden información al codificarse como null/null. 
Cambio previsto: cuando el documento indique aptitud universal, 
fijar edad_min=0 y edad_max=99 para preservar la semántica.

### LD5 — Fechas de inicio recurrentes
Algunos cursos (típicamente los de academias permanentes) tienen 
fechas de inicio recurrentes ("Every Monday"). El esquema actual 
fuerza una única fecha de inicio. Cambio previsto: añadir un campo 
`fechas_inicio_recurrentes` o similar para capturar esta semántica.

### LD6 — Documentos B2B versus documentos para cliente final
El corpus contiene al menos dos tipos fundamentalmente distintos de 
documentos: catálogos para cliente final (ej. Berlitz ELA 2026) y 
hojas de tarifas netas para venta a grupos cerrados (ej. NET Prices). 
Tratarlos como equivalentes lleva a recomendaciones engañosas. 
Solución prevista: clasificar el documento en una primera pasada 
(folleto / tarifa B2B / lista de precios / ficha de programa) y 
gestionar cada tipo de forma diferenciada.

### LD7 — Documentos multi-estación / multi-campaña
Algunos documentos cubren varias campañas en un mismo PDF (low season + 
high season, primavera + verano, etc.). El sistema actual extrae solo 
una. Solución prevista: detectar la presencia de múltiples campañas y 
generar un Programa por cada una.

### LD8 — Multi-pricing estructurado
El precio de un programa raramente es un único número: incluye tuition, 
fees obligatorios, alojamiento elegible, comidas, actividades, descuento 
por líder, etc. El esquema (precio_min, precio_max) es una simplificación 
muy gruesa. Solución prevista a medio plazo: descomponer precio en sus 
componentes (precio_tuition, precio_alojamiento, precio_actividades, 
precio_extras) o introducir un campo `desglose_precio: dict[str, float]`.

### LD9 — Edad variable según paquete
La edad mínima/máxima puede depender de la temporada o del paquete 
concreto dentro del documento (ej. 15+ para low season, 16+ para 
summer). Una vez se capture LD7 (multi-campaña), cada Programa 
generado tendrá sus propios edad_min/edad_max correctos.

### LD10 — Distinción entre fechas de campaña y fechas de programa
"January to May 2026" indica el período de validez de unas tarifas, 
no la duración de un programa concreto. Un programa concreto dentro 
de esa ventana puede ser de 1 semana cualquiera. El esquema actual no 
distingue ambas semánticas y mezcla los dos conceptos en fecha_inicio 
y fecha_fin. Solución prevista: añadir campos separados 
`vigencia_inicio` / `vigencia_fin` (validez de tarifas) y mantener 
`fecha_inicio` / `fecha_fin` para el programa concreto, cuando 
aplique.

### LD11 — Documentos producidos por la propia agencia
Una parte del corpus puede no provenir de proveedores externos sino 
ser material propio de I-KIDS para programas que ella misma orquesta 
con varios partners. Este caso (DBS Dublin) es el primero detectado. 
El sistema actual no diferencia entre "documento de proveedor" y 
"documento propio de I-KIDS sobre programa colaborativo". Esta 
distinción es importante porque cambia la fiabilidad y el rol del 
documento en la decisión.

### LD12 — Programas con múltiples proveedores
Algunos programas son alianzas entre varias entidades (DBS Sports + 
Future Learning + i-kids). El esquema actual con un único 
`empresa_proveedora` simplifica esta realidad y pierde información 
sobre la cadena de valor del programa. Solución prevista: 
`empresa_proveedora: list[str]` o un campo adicional 
`partners: list[Partner]` con rol de cada uno.

### LD13 — Inferencias numéricas vs extracción literal
El LLM no siempre se limita a extraer valores literales: a veces 
infiere o calcula valores a partir de tablas estructuradas (precios 
por semana × duración, ofertas combinadas, etc.). Para fines de 
validación de H1 conviene distinguir tres niveles de fidelidad:
- LITERAL: el valor aparece tal cual en el documento.
- DERIVADO: el valor se calcula a partir de información del documento 
  con una regla simple (ej: total = base + adicional × n).
- INFERIDO: el valor se deduce sin operaciones explícitas (ej: 
  edad_min=18 cuando el doc habla de "adults").

### LD14 — Costes adicionales no capturados
El esquema actual no recoge costes opcionales u obligatorios que se 
pagan por separado del precio principal: traslados, seguros, 
servicios para menores, etc. Para una recomendación realista, estos 
extras pueden ser determinantes del precio total. Solución prevista: 
añadir `costes_adicionales: list[Coste]` con descripción y cuantía.

### LD15 — Programas con múltiples sedes
Algunos programas operan en varias ubicaciones físicas distintas 
(entrenamiento en una sede, clases y alojamiento en otra). El campo 
`ciudad` actual no captura esta multiplicidad. Solución prevista: 
permitir varias `sedes` con tipo (entrenamiento, clases, 
alojamiento, social).

### LD16 — Información cruzada entre documentos del mismo proveedor
Un mismo proveedor (NSX) puede repartir información sobre el mismo 
programa entre varios documentos: una hoja de precios general (NSX 
Gross Prices) y guías por escuela específica (Millfield School Guide). 
El sistema actual no relaciona ambos documentos: la información 
extraída de un PDF se queda en su Programa correspondiente, sin 
mecanismo para enriquecerse con datos del otro. Esto puede llevar a 
catálogos donde el mismo programa aparece dos veces con información 
parcial complementaria. Solución prevista: añadir una etapa de 
deduplicación / fusión post-extracción que detecte programas 
equivalentes (mismo proveedor + misma sede + mismo año) y combine 
sus campos.

### LD17 — Conversión automática de moneda por el LLM
Los precios originales pueden estar en moneda distinta al euro (GBP, 
USD, etc.). El prompt del proyecto instruye al LLM a convertir a 
euros con una tasa aproximada. Esto introduce dos limitaciones 
metodológicas que conviene documentar en la validación:
- La conversión NO es información literal del documento.
- La tasa usada es estática y se desfasa con la realidad del mercado.

Solución prevista: añadir un campo opcional `moneda_origen` que 
preserve la moneda original y `precio_min_origen` / `precio_max_origen` 
con los valores literales no convertidos. La conversión a euros se 
mantiene como campo derivado para la comparación interna.

### LD18 — Variantes de un mismo programa
Un programa puede tener varias variantes (English+, English+ Tennis, 
English+ Horse Riding, etc.) que se diferencian por la actividad 
complementaria. Capturar solo el rango precio_min/precio_max pierde 
la identidad de cada variante y la actividad asociada. Para usuarios 
con preferencias específicas (ej. quiero tenis), esta granularidad 
es relevante. Solución prevista: añadir un campo 
`variantes: list[Variante]` donde cada variante tiene nombre, 
actividad y precio adicional.

### LD19 — Múltiples turnos / sesiones del mismo programa
Un programa puede ofrecerse en varios turnos diferenciados con misma 
duración (ej. dos turnos de 2 semanas en julio). El esquema actual 
mezcla las fechas de los turnos en un único rango fecha_inicio - 
fecha_fin, lo que sugiere erróneamente una continuidad. Solución 
prevista: convertir fechas en una lista 
`turnos: list[tuple[date, date]]` con cada turno por separado.

### LD20 — Cursos especialistas como modificadores del programa
Algunos programas ofrecen cursos especialistas (Football, Tennis, 
Horse Riding, etc.) que reemplazan parcialmente la actividad estándar 
del programa. No son simplemente add-ons de precio: cambian las 
horas dedicadas a cada bloque. Solución prevista: campo 
`cursos_especialistas: list[CursoEspecialista]` con nombre, 
descripción, horas dedicadas y partnership.

### LD21 — Partnerships de marca relevantes
Programas que mencionan colaboraciones con marcas reconocidas (Jamie 
Murray, FIFA, etc.) pueden ser argumento de venta clave. El esquema 
actual no captura estas colaboraciones. Solución prevista: campo 
`partnerships: list[Partnership]`.

### LD22 — Información económica complementaria
Pocket money, costes de excursiones extra, depósitos, lavandería, 
etc. son costes implícitos relevantes para la planificación 
presupuestaria del cliente, pero quedan fuera del rango precio_min / 
precio_max. Solución prevista: campo `costes_complementarios` con 
descripción y estimación.

### LD23 — La calidad de la presentación documental condiciona la extracción
Documentos con información tabular y estructurada (Millfield Guide) 
producen mejores extracciones que documentos con información en 
prosa o párrafos largos (Gross Prices, Berlitz). Esta correlación 
empírica tiene implicaciones para el corpus de evaluación de H1: 
sería interesante reportar la métrica de F1 desglosada por tipo de 
estructura documental.