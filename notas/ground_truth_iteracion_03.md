# Ground truth iteración 03

## 1. Berlitz ELA 2026.pdf

| Campo               | Extraído por LLM        | Valor real en el doc                        | Estado |
|---------------------|-------------------------|---------------------------------------------|--------|
| nombre              | "General English"       | General English                             | ✅     |
| empresa_proveedora  | "Berlitz"               | Berlitz \| ELA (English Language Academy)   | ✅     |
| pais                | "Malta"                 | Malta                                       | ✅     |
| ciudad              | "St. Julians"           | St. Julians                                 | ✅     |
| idioma              | "inglés"                | inglés                                      | ✅     |
| edad_min            | null                    | "Ideal for all ages (kids, teens, adults)"  | 🟡     |
| edad_max            | null                    | "Ideal for all ages"                        | 🟡     |
| duracion_min_dias   | 7                       | "Minimum 1 Week" → 7 días                   | ✅     |
| duracion_max_dias   | null                    | No especificado (curso abierto)             | ⬜     |
| precio_min_eur      | null                    | 280€ (en PRICE LIST 2026, pág. 31)          | ❌     |
| precio_max_eur      | null                    | 825€ (en PRICE LIST 2026, pág. 31)          | ❌     |
| tipo_alojamiento    | null                    | Familia y apartamento (pág. ACCOMMODATION)  | ❌     |
| fecha_inicio        | "2026-01-01"            | "Every Monday" (no fecha fija)              | 🟡     |
| fecha_fin           | null                    | No aplica (oferta continua todo el año)     | ⬜     |

**Estado**: ✅ correcto / ❌ incorrecto / 🟡 parcial / ⬜ no aparece en doc

**Notas adicionales**:

1. **Documento multi-programa**: el folleto contiene la cartera completa
   de cursos de Berlitz, no un único programa. Programas presentes:
   - MAIN: General English, Business English, Private Lessons 1-to-1
   - OPTIONAL: Conversation 10, Private Electives 10
   - SPECIALS: Exam Preparation, Teacher Training (CLIL), Specialised Programmes, Total Immersion, 50+ Programmes, Family Packages
   - YOUTH: Youth Camps, Closed Groups (Tailor made)
   
   El sistema actual solo extrae uno (el primero/principal). El resto 
   queda fuera. Esto provoca que la oferta de Berlitz quede 
   infrarrepresentada en el catálogo.

2. **Información distribuida en páginas no contiguas**: los precios 
   están en una página separada (PRICE LIST 2026, pág. 31), y la 
   información de alojamiento en otra (ACCOMMODATION, pág. 28). El 
   LLM no relaciona los datos de la "ficha de programa" con los datos 
   de las páginas globales del catálogo, por lo que campos como precio 
   y tipo de alojamiento quedan en null aunque la información esté 
   en el documento.

3. **Múltiples tipos de alojamiento simultáneos**: el documento ofrece 
   familia y apartamento. El esquema actual solo admite un único 
   valor de tipo_alojamiento, lo que obliga a perder información o a 
   inventar una jerarquía artificial. La oferta real es un conjunto 
   de opciones, no una opción única.

4. **"All ages" como rango sin números**: el doc dice "Ideal for all 
   ages (kids, teens, adults)" sin proporcionar valores numéricos. 
   El LLM ha optado por null/null. Funcionalmente acepta cualquier 
   edad en el filtrado, pero pierde la información explícita de que 
   el programa es universal.

5. **Fechas de inicio flexibles**: el doc dice "Every Monday" como 
   fecha de inicio. El LLM lo ha traducido incorrectamente a 
   "2026-01-01". El esquema actual no contempla la noción de "inicio 
   recurrente".

## 2. NET Prices for Closed Groups 2026 - Sample of a group 15 students + 1 leader.pdf

| Campo               | Extraído por LLM           | Valor real en el doc                                        | Estado |
|---------------------|----------------------------|-------------------------------------------------------------|--------|
| nombre              | "English Language Course Malta" | Doc titulado "Closed Groups Mini Stay - low season" (B2B) | 🟡     |
| empresa_proveedora  | "Berlitz"                  | Berlitz \| ELA Malta                                        | ✅     |
| pais                | "Malta"                    | Malta                                                       | ✅     |
| ciudad              | null                       | No se menciona explícitamente (es Berlitz Malta = St. Julians, pero implícito) | ⬜ |
| idioma              | "inglés"                   | inglés                                                      | ✅     |
| edad_min            | 15                         | "Good for students over 15 years old" (low season) / "over 16" (high season) | ✅ |
| edad_max            | null                       | No especificado                                             | ⬜     |
| duracion_min_dias   | 7                          | Sample dice "1 week (7 nights)", pero las tarifas son flexibles por semana | 🟡 |
| duracion_max_dias   | 7                          | El doc no fija máximo, las tarifas son por semana modulares | 🟡     |
| precio_min_eur      | 517.05                     | €517,05 es UNO de los muchos precios; el más bajo es €232 (solo tuition); con líder y completo €569,25 (low) o €580 (high) | 🟡 |
| precio_max_eur      | 517.05                     | Hay precios bastante más altos en el doc (≥€580 high season per student; €8538.75 group total; etc.) | ❌ |
| tipo_alojamiento    | "familia"                  | OFRECE Homestay (familia) + Hotel Canifor + Hotel Plaza Sliema | 🟡 |
| fecha_inicio        | "2026-01-01"               | "January to May 2026" → enero como inicio de validez. Pero el doc TAMBIÉN cubre julio 2026 | 🟡 |
| fecha_fin           | "2026-05-31"               | El doc cubre "January to May" Y "Summer high season July 2026" → la fecha fin debería ir hasta julio o más | ❌ |

**Observaciones sobre NET Prices for Closed Groups 2026.pdf:**

1. **NATURALEZA B2B del documento**: este PDF NO es un folleto de programa
   para cliente final, sino una hoja de tarifas netas para venta a grupos
   cerrados (mínimo 15 estudiantes + 1 líder). Berlitz lo envía a I-KIDS
   para que I-KIDS lo use al organizar grupos cerrados que viajan juntos
   (típicamente colegios o academias enviando un curso entero). El precio
   final que paga el estudiante individual NO es el que aparece aquí; es
   el precio neto del proveedor sobre el que I-KIDS aplica su margen.
   
   El sistema actual no distingue entre documentos B2B y documentos para
   cliente final. Esto puede llevar a recomendaciones engañosas si un
   asesor consulta el sistema para un cliente individual y le aparecen
   precios "netos" como si fueran precios reales.

2. **Documento dual estacional**: el PDF cubre dos campañas distintas en
   un único documento — Low Season (enero-mayo 2026) Y Summer High Season
   (julio 2026). El LLM ha capturado solo la primera. Esto deja fuera del
   catálogo todo lo relativo al verano, que es justamente la temporada
   más importante para una academia de idiomas.

3. **Multiplicidad de precios**: el documento contiene al menos siete
   estructuras de precio distintas:
   - Tuition pura (€155 General English 20, €179 Business English 20)
   - Compulsory fees (€30 + €35 + €12 = €77)
   - Total mínimo (€232/student)
   - Con homestay (€517,05 low season sample)
   - Con líder incluido (€569,25 low season, €580 high season)
   - Total grupo (€3.480, €8.538,75, €8.700)
   - Hotel options (€286,65 a €728 según tipo y temporada)
   
   El esquema actual (precio_min/precio_max) no captura esta granularidad.
   El LLM ha optado por uno solo, perdiendo el resto.

4. **Tres tipos de alojamiento simultáneos**: Homestay (familia), Hotel
   Canifor, Hotel Plaza Sliema. El esquema actual permite uno solo.
   Lección LD3 (de la iteración con PDF 1) se confirma con este caso.

5. **Cuatro packs de actividades**: Pack 1 a Pack 4 con precios de €65 a
   €165, más School Activities Pack a €45. El esquema actual no captura
   la dimensión "actividades incluidas".

6. **Edad mínima dependiente del paquete**: low season 15+, high season
   16+. La edad varía según la versión del programa, no es un único valor
   para todo el documento. El esquema actual no permite expresar esta
   variación.

7. **Fechas de campaña, no de programa**: "January to May 2026" y "July
   2026" son ventanas de validez de tarifas, no fechas en las que el
   programa empieza o termina. Un grupo puede empezar cualquier semana
   dentro de esa ventana. El campo fecha_inicio/fecha_fin actual mezcla
   ambos conceptos.

## 3. IKIDS DBS Dublin Elite Soccer and English-canva-040326.pdf

| Campo               | Extraído por LLM                              | Valor real en el doc                                 | Estado |
|---------------------|-----------------------------------------------|------------------------------------------------------|--------|
| nombre              | "High performance football & English learning Summer Camp Experience in Ireland" | "High performance football & English learning - Summer Camp Experience in Ireland" | ✅ |
| empresa_proveedora  | "DBS"                                         | Alianza tripartita: DBS Sports + Future Learning + i-kids (la propia academia) | 🟡 |
| pais                | "Irlanda"                                     | Irlanda                                              | ✅ |
| ciudad              | "Dublín"                                      | Dublín                                               | ✅ |
| idioma              | "inglés"                                      | inglés                                               | ✅ |
| edad_min            | 12                                            | "Nois i noies de 12 a 17 anys"                       | ✅ |
| edad_max            | 17                                            | "Nois i noies de 12 a 17 anys"                       | ✅ |
| duracion_min_dias   | 7                                             | "1 setmana" (1 semana)                               | ✅ |
| duracion_max_dias   | 35                                            | "fins a 5 setmanes" (5 semanas × 7 = 35 días)        | ✅ |
| precio_min_eur      | 1992.0                                        | 1.992 € (1 semana, explícito en tabla)               | ✅ |
| precio_max_eur      | 9392.0                                        | Calculado: 1.992 + 4×1.850 = 9.392 €. La tabla NO lo indica directamente. | 🟡 |
| tipo_alojamiento    | "residencia"                                  | "Allotjament residencial (en-suite)" en Belvedere College | ✅ |
| fecha_inicio        | "2026-06-29"                                  | "29 de juny" (29 junio 2026)                         | ✅ |
| fecha_fin           | "2026-07-31"                                  | "31 de juliol" (31 julio 2026)                       | ✅ |
| acreditaciones      | ["UEFA A", "UEFA Pro"]                        | "Entrenadors amb llicència UEFA (A i Pro)" + FIFA + FAI | 🟡 |
| idioma_documento_origen | "ca"                                      | catalán confirmado                                   | ✅ |

**Observaciones sobre IKIDS DBS Dublin Elite Soccer and English.pdf:**

1. **Documento producido por la propia I-KIDS**: a diferencia de los 
   PDFs de Berlitz (que son material del proveedor), este documento es 
   marketing propio de i-kids para promocionar un programa que ha 
   organizado con dos partners (DBS Sports International Soccer Academy 
   + Future Learning). Esto plantea un caso de uso interesante: el 
   sistema procesa material que ya proviene de la propia academia, no 
   solo de proveedores externos.

2. **Empresa proveedora múltiple**: el programa real es una alianza de 
   tres entidades:
   - DBS Sports International Soccer Academy (entrenamiento de fútbol)
   - Future Learning (componente educativo de inglés)
   - i-kids (organización y marketing)
   
   El esquema actual asume un único campo `empresa_proveedora` y la 
   carpeta de origen ha forzado el valor "DBS". Se pierde la 
   información de que Future Learning es co-proveedor del componente 
   de inglés.

3. **Cálculo derivado del precio máximo**: el documento muestra una 
   tabla con tres entradas (1 semana 1.992€, 2 semanas 3.701€, 
   "setmanes addicionals fins a 5 setmanes" 1.850€). El precio máximo 
   no aparece explícito; el LLM lo ha calculado como 1.992 + 4×1.850 = 
   9.392€, asumiendo "1 semana base + 4 adicionales = 5 semanas". 
   Esta interpretación es razonable pero no es información literal del 
   documento, sino una inferencia. Otra interpretación posible sería 
   3.701 + 3×1.850 = 9.251€ ("2 semanas base + 3 adicionales = 5 
   semanas"). 
   
   Esta observación es relevante porque permite distinguir entre 
   "extracción literal" e "inferencia numérica" del LLM.

4. **Acreditaciones parcialmente capturadas**: el LLM ha extraído UEFA 
   A y UEFA Pro (acreditaciones de los entrenadores), pero ha 
   omitido:
   - Camps de gespa aprovats per la FIFA (acreditación FIFA de las 
     instalaciones)
   - Seu de les Seleccions Nacionals d'Irlanda (FAI)
   
   La distinción es sutil: las primeras son acreditaciones de 
   personal, las segundas de instalaciones. El esquema actual no 
   distingue entre ambos tipos.

5. **Dos sedes físicas para un mismo programa**: el documento describe 
   dos ubicaciones distintas (Sport Ireland Campus para entrenamiento 
   y Belvedere College para clases + alojamiento). El LLM ha capturado 
   solo una ciudad ("Dublín") y un tipo de alojamiento (residencia en 
   Belvedere). Información perdida: la dualidad de las sedes y el 
   transporte privado entre ellas.

6. **Costes adicionales no incluidos en el rango de precio**: el 
   documento detalla extras significativos que no se capturan:
   - Traslado privado al aeropuerto: 95 € por trayecto
   - Servicio de menor no acompañado: 75 €
   - Alergias alimentarias: 49 € por semana
   - Seguro médico: 50 € a 65 € según duración
   
   Para un programa de 5 semanas con todos los extras, el coste real 
   puede superar fácilmente los 9.700 €, frente a los 9.392 € del 
   rango actual.

## 4. NSX 2026 - Gross Prices.pdf

| Campo               | Extraído por LLM                            | Valor real en el doc                                  | Estado |
|---------------------|---------------------------------------------|-------------------------------------------------------|--------|
| nombre              | "NSX Summer School at Woodbridge School"    | "NSX at Woodbridge School" (LLM añadió "Summer School" del título general) | 🟡 |
| empresa_proveedora  | "NSX"                                       | NSX (nsxgroup.co.uk)                                  | ✅ |
| pais                | "Reino Unido"                               | Reino Unido (Heathrow + Woodbridge + £)               | ✅ |
| ciudad              | "Woodbridge"                                | Woodbridge (Suffolk, UK)                              | ✅ |
| idioma              | "inglés"                                    | inglés                                                | ✅ |
| edad_min            | null                                        | No especificado (es hoja de precios)                  | ⬜ |
| edad_max            | null                                        | No especificado                                       | ⬜ |
| duracion_min_dias   | 14                                          | "two weeks programme", "13 nights" (=14 días)         | ✅ |
| duracion_max_dias   | 14                                          | Programa fijo de 2 semanas                            | ✅ |
| precio_min_eur      | 3416.0                                      | £2.940 base × ~1.16 = 3.410€ (English+ básico)        | 🟡 |
| precio_max_eur      | 4111.0                                      | £3.540 (£2.940 + £600 Tennis) × ~1.16 = 4.106€        | 🟡 |
| tipo_alojamiento    | "residencia"                                | "13 nights full-board accommodation" en school        | ✅ |
| fecha_inicio        | "2026-07-05"                                | "Sunday 5th July"                                     | ✅ |
| fecha_fin           | "2026-08-01"                                | "Saturday 1st August"                                 | 🟡 |
| acreditaciones      | []                                          | "TEFL certified teachers" mencionado                  | 🟡 |
| idioma_documento_origen | "en"                                    | inglés                                                | ✅ |

**Observaciones sobre NSX 2026 - Gross Prices.pdf:**

1. **DOS PROGRAMAS EN UN MISMO DOCUMENTO (problema multi-programa repetido)**: 
   el PDF contiene la tabla de precios de **dos programas distintos**:
   - NSX at Woodbridge School (£2.940 base)
   - NSX at Millfield School (£3.375 base)
   
   El LLM ha extraído solo Woodbridge desde este PDF. La información 
   de Millfield desde este documento (precios) se pierde. Por suerte, 
   el corpus contiene otro PDF dedicado a Millfield ("NSX 2026 Summer 
   School Guide - Millfield School.pdf") que sí se extrae como entrada 
   separada del catálogo. Pero esto es coincidencia: la información de 
   precios de Millfield que aparece AQUÍ no llega al programa Millfield 
   que se extrae del otro PDF.
   
   Esta confirma la lección LD1 (multi-programa) y añade un caso nuevo: 
   los precios pueden estar en un documento distinto al de la 
   descripción del programa, sin que haya un mecanismo automático para 
   correlacionarlos.

2. **DOCUMENTO B2B (similar a NET Prices Berlitz)**: este PDF está 
   titulado "Gross Agent Bookings" y aplica un 25% de comisión de 
   agente. El precio que paga el cliente final NO es el "Price (Net)" 
   que aparece en la tabla, sino una versión modificada según la 
   estructura comercial. Confirma la lección LD6 (B2B vs cliente final).

3. **CONVERSIÓN DE MONEDA AUTOMÁTICA**: los precios originales están 
   en libras esterlinas (£), no en euros. El LLM ha aplicado una 
   conversión aproximada (1 GBP ≈ 1.16 EUR según la regla del prompt) 
   y reportado los valores ya en euros. Esto introduce dos cuestiones:
   
   - La conversión NO es literal del documento; el documento NO da 
     precios en euros. Es una transformación numérica del LLM.
   - La tasa usada es estática (la pusimos como 1.17 en el prompt, 
     pero el LLM parece haber aplicado ~1.16). Una tasa real de 
     mercado fluctúa diariamente, lo que afecta a la comparación 
     entre programas en distintas monedas.

4. **VARIANTES DEL PROGRAMA NO CAPTURADAS**: el documento ofrece 
   tres variantes del programa Woodbridge:
   - English+ (precio base)
   - English+ Horse Riding (+£565)
   - English+ Tennis (+£600)
   
   El LLM ha capturado el rango precio_min y precio_max correctamente, 
   pero ha perdido la **identidad de cada variante**. Un cliente que 
   busca específicamente "tenis" no puede saber si este programa lo 
   ofrece o no a partir de la información extraída.

5. **DOS VENTANAS DE FECHAS PARA UN MISMO PROGRAMA**: el documento 
   indica que el programa Woodbridge se ofrece en dos turnos:
   - Sunday 5th July - Saturday 18th July
   - Sunday 19th July - Saturday 1st August
   
   El LLM ha juntado ambas en un único rango (5 julio - 1 agosto), 
   lo que es engañoso porque parece sugerir un programa de 4 semanas 
   continuas, cuando en realidad son dos turnos de 2 semanas con un 
   cambio de grupo en medio.

6. **TEFL no extraído como acreditación**: el documento menciona 
   "English lessons with TEFL certified teachers". TEFL es una 
   certificación reconocida internacionalmente para profesores de 
   inglés y debería figurar en acreditaciones. El LLM ha dejado el campo vacío.

7. **AUSENCIA DE EDADES JUSTIFICADA**: este documento es 
   exclusivamente una hoja de precios, no contiene información de 
   edades en ningún punto. El null en edad_min/edad_max es 
   correcto en este contexto.

## 5. NSX 2026 Summer School Guide - Millfield School.pdf

| Campo               | Extraído por LLM            | Valor real en el doc                                  | Estado |
|---------------------|-----------------------------|-------------------------------------------------------|--------|
| nombre              | "Millfield School"          | Doc titulado "Millfield School" — es nombre de la sede, no del programa | 🟡 |
| empresa_proveedora  | "NSX"                       | NSX (NSX Summer Schools, info@nsxgroup.co.uk)         | ✅ |
| pais                | "Reino Unido"               | Reino Unido (BA16 0YD postcode)                       | ✅ |
| ciudad              | "Street, Somerset"          | Street BA16 0YD + "Located in Somerset"               | ✅ |
| idioma              | "inglés"                    | "Language: English"                                   | ✅ |
| edad_min            | 14                          | "Age Guide: 14 to 17"                                 | ✅ |
| edad_max            | 17                          | "Age Guide: 14 to 17"                                 | ✅ |
| duracion_min_dias   | 14                          | Cada turno: 5-18 julio o 19 julio-1 agosto = 14 días  | ✅ |
| duracion_max_dias   | 14                          | Programa fijo de 2 semanas                            | ✅ |
| precio_min_eur      | null                        | NO HAY PRECIOS en este documento                      | ⬜ |
| precio_max_eur      | null                        | NO HAY PRECIOS en este documento                      | ⬜ |
| tipo_alojamiento    | "residencia"                | "1 to 4 bedded rooms shared bathrooms" en NSX Accommodation Blocks | ✅ |
| fecha_inicio        | "2026-07-05"                | Inicio del primer turno                               | ✅ |
| fecha_fin           | "2026-08-01"                | Fin del segundo turno (combina dos turnos en un rango) | 🟡 |
| acreditaciones      | ["TEFL certified teachers"] | "English lessons with TEFL certified teachers"        | ✅ |
| idioma_documento_origen | "en"                    | inglés                                                | ✅ |

**Observaciones sobre NSX 2026 Summer School Guide - Millfield School.pdf:**

1. **DOCUMENTO COMPLEMENTARIO al de precios**: este PDF es la guía 
   detallada del programa Millfield (descripción de instalaciones, 
   horarios, comidas, cursos especialistas, etc.) pero NO contiene 
   precios. Los precios para Millfield están en el otro PDF (NSX 2026 
   Gross Prices). Como el sistema procesa cada PDF de forma 
   independiente, el Programa Millfield extraído aquí queda con 
   precio_min/precio_max nulos a pesar de que la información existe 
   en el corpus, simplemente en otro fichero.
   
   Esta es la confirmación más clara de la lección LD16 (información 
   cruzada entre documentos del mismo proveedor).

2. **CURSOS ESPECIALISTAS NO CAPTURADOS**: el documento dedica dos 
   páginas completas a describir los Specialist Courses disponibles 
   en Millfield: Tennis (en partnership con Active Away | Jamie 
   Murray) y Football. Estos cursos cambian sustancialmente la 
   experiencia del programa: son 20 horas (Tennis) o 30 horas 
   (Football) específicas que reemplazan parcialmente las English+ 
   sessions del programa estándar. El LLM no los ha capturado en 
   ningún campo del esquema. Confirma la lección LD18 (variantes de 
   programa).

3. **PARTNERSHIP NO CAPTURADO**: Active Away | Jamie Murray Tennis 
   Programme es una alianza relevante (Jamie Murray es tenista 
   profesional británico, hermano de Andy Murray). Esta colaboración 
   con tercera marca añade valor comercial al programa. El esquema 
   actual no contempla un campo `partners`.

4. **POCKET MONEY como información financiera**: el documento indica 
   "£30-£50 per week" como dinero de bolsillo recomendado. No es 
   precio del programa pero sí información económica útil para que el 
   cliente planifique el presupuesto total. El esquema actual no 
   capta esta información.

5. **EXCURSIONES NO CAPTURADAS**: el doc lista tres destinos 
   incluidos en el programa: Bath, Oxford, Glastonbury. Esta 
   información puede ser determinante para clientes con preferencias 
   geográficas o culturales específicas. El esquema actual no lo 
   captura.

6. **TEFL acreditación SÍ capturada aquí (a diferencia del PDF 
   anterior)**: en NSX Gross Prices, el LLM había omitido TEFL 
   certified teachers. En este documento sí lo captura. La diferencia 
   probable: aquí aparece en una lista estructurada ("Programme 
   Includes:"), mientras que en el otro estaba en un párrafo de texto 
   más diluido. Esto sugiere que la presentación visual del documento 
   afecta a la calidad de extracción.

7. **DOS TURNOS DE FECHAS combinados**: igual que en NSX Gross 
   Prices, las dos ventanas (5-18 julio y 19 julio-1 agosto) se 
   funden en un rango único 5 julio - 1 agosto. Confirma LD19.

8. **CALIDAD VISUAL DEL DOCUMENTO**: este PDF tiene la información 
   estructurada en tabla muy clara (Address, Dates, Language, 
   Accommodation, etc.). Esa estructura tabular se traduce 
   directamente en alta tasa de acierto del LLM. Sugiere que la 
   calidad de la presentación del proveedor condiciona la calidad de 
   extracción.




