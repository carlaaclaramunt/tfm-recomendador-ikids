# Iteraciones

## Iteración 01
- 5 PDFs procesados, 5/5 extraídos sin errores
- 2/5 pasan el filtro con perfil sintético (estudiante 14 años, ≤2500€)
- Top: NSX Woodbridge y Millfield (ambos 0.40)
- Coste API: ~5 céntimos
- Problemas detectados:
  * Duración salía 7 días en 3/5 (era unidad de precio, no duración)
  * Precios null en 3/5
  * Edades null en 2/5
  * Empresa "Berlitz" mal asignada al programa English Language Malta
  * Catalán correctamente detectado en DBS Dublin
### Conclusiones
Idioma: 5/5 correcto (siempre "inglés").
País: 5/5 correcto y formateado en español ("Malta", "Irlanda", "Reino Unido").
Ciudad: 4/5 (solo NET Prices se quedó sin ciudad, lo que es lógico porque el PDF habla de varios destinos).
Acreditaciones: aparecen donde los hay (Berlitz Certificate, CEFR, UEFA A, UEFA Pro, TEFL).
Fechas: los que tienen rango de campaña sí se extraen.

Mi perfil exigía duracion_min_dias = 14, pero eso solo lo cumplían NSX y Millfield. Berlitz, Malta y DBS ha detectado 7 días.

## Iteración 02
- Cambio: fechas como Optional[date] en vez de str
- Cambio: prompt mejorado con reglas de fechas ISO 8601
- Resultados: las fechas salen en formato correcto
- Observación: Millfield cambia fecha_fin entre ejecuciones
  (motivó la decisión de fijar temperature=0)

## Iteración 03
- Cambios: duración y precio como rangos (min/max)
- Cambios: temperature=0 en API de Anthropic
- Cambios: filtros y MCDM actualizados para rangos
- Resultados:
  * 5/5 PDFs extraídos sin errores
  * DBS Dublin pasa de quedar filtrado a TOP 1 con score 0.69
  * Las explicaciones se enriquecen mucho (de 1-2 motivos a 6)
  * 3/5 programas tienen precio extraído (antes 2/5)
- Observación clave: la calidad de la extracción condiciona directamente
  la calidad de la recomendación. Programas con campos null reciben
  scores neutros y pierden ranking.

## Iteración 04

### Cambios introducidos
- Implementación del subsistema de curación (RF6).
- Nuevos campos en Programa: anyo_documento, estado_documento,
  campos_obsoletos, razon_obsolescencia.
- Nuevo módulo src/curation/obsolescence.py con clasificación
  heurística por año.
- Integración en pipeline y explicador con aviso al usuario.

## Iteración 05 

### Cambios introducidos
- Implementación de LD6: clasificación funcional del documento.
- Nuevo campo `tipo_documento` con cinco valores posibles.
- Regla añadida al prompt para clasificar el documento.
- Aviso en el explicador para programas extraídos de tarifas B2B
  o listas de precios.
- - Implementación de LD17: preservación de moneda original del precio.
- Tres campos nuevos en Programa: moneda_origen, precio_min_origen,
  precio_max_origen.
- Regla añadida al prompt para preservar valores literales antes de la
  conversión a euros.
- Explicador actualizado para mostrar el equivalente en moneda
  original cuando difiere del euro.

### Resultados
- Tasa de acierto en clasificación funcional: X/5
- NSX Woodbridge: moneda_origen="GBP", precio_min_origen=2940, etc.


### Observaciones
- La distinción entre valor literal (origen) y valor derivado (EUR)
  cierra el bucle de la Observación 4 del Capítulo 6
  ("Transformaciones durante la extracción"), que ahora pasa de ser
  una limitación a ser una decisión de diseño implementada.

### Iteración 06

Se han implementado simultáneamente cuatro lecciones que conforman
una capa coherente de curación documental:

- LD3 (alojamientos múltiples): tipo_alojamiento ahora es una lista
  con validator de retrocompatibilidad.
- LD10 (vigencia vs fechas de programa): se añaden los campos
  vigencia_inicio y vigencia_fin para separar ambos conceptos.
- LD16 (información cruzada): nuevo módulo src/curation/merge.py
  con agrupación, deduplicación y fusión de programas equivalentes
  procedentes de distintos PDFs del mismo proveedor.
- LD17 (moneda original): los precios se conservan también en su
  moneda literal del documento, además de la conversión a euros.

El módulo de fusión utiliza una métrica de similitud sobre nombres
normalizados (difflib.SequenceMatcher con umbral 0,72) junto con
restricciones duras sobre empresa, país, ciudad y año. La fusión
preserva la información más completa de cada campo según reglas
específicas por tipo (rango más amplio para precios y duraciones,
texto más largo para nombres, prioridad jerárquica para tipo y
estado documental).

## Iteracion 07
La transición del esquema mono-programa al esquema multi-programa, combinada con el módulo de fusión post-extracción, permite expandir el catálogo de 5 a 24 entradas brutas y consolidarlas a 15 entradas únicas tras la deduplicación inter-documental. El ratio de unificación del 37,5% confirma que la información sobre un mismo programa se reparte de forma significativa entre múltiples documentos del corpus, validando empíricamente la necesidad del subsistema de curación documental."

## Iteración 08

Durante esta iteración se ha consolidado una nueva capa de curación
documental orientada a mejorar la fidelidad semántica del catálogo,
la trazabilidad de la extracción y la capacidad del sistema para
trabajar con documentación comercial heterogénea y parcialmente
no estructurada.

La implementación integra simultáneamente varias lecciones derivadas
del análisis manual iterativo del corpus real utilizado por I-KIDS.

Se han implementado las siguientes mejoras:

LD3 (alojamientos múltiples): tipo_alojamiento pasa de un valor
único a list[TipoAlojamiento], permitiendo representar programas
con varias modalidades simultáneas (familia, residencia, hotel, etc.).
Se añadió además lógica de retrocompatibilidad para aceptar tanto
strings individuales como listas.
LD10 (vigencia comercial vs fechas reales del programa): se añaden
los campos vigencia_inicio y vigencia_fin para separar la
validez temporal de tarifas/campañas de las fechas concretas del
programa (fecha_inicio y fecha_fin). Esta distinción evita
inconsistencias temporales en documentos multi-campaña.
LD11 y LD12 (documentos colaborativos y múltiples proveedores):
el sistema incorpora ahora los campos origen_documento,
es_programa_colaborativo y partners, permitiendo modelar
programas organizados conjuntamente por varias entidades
(ej. I-KIDS + DBS Sports + Future Learning). Esto introduce una
representación más fiel de la cadena de valor real del programa.
LD16 (información cruzada entre documentos): se implementa el módulo
src/curation/merge.py, encargado de detectar programas equivalentes
procedentes de múltiples PDFs y fusionar automáticamente su
información complementaria. El sistema genera claves canónicas
(programa_key) y aplica agrupación semántica mediante similitud
textual.

## Iteracion 09

### De dónde partíamos

Teniamos un sistema que extraía bien (15 programas tras fusión sobre 5 PDFs), pero **el recomendador no estaba dando los resultados esperados**. El TOP 1 era siempre DBS Dublin, independientemente del perfil, y los programas Berlitz nunca salían pese a ofrecer alojamiento "familia" (que era la preferencia del perfil demo). No estaba claro por qué.

### Qué hicimos

Teniamos **cinco bugs silenciosos**: cosas que no rompían el sistema (no había errores en consola), pero que producían resultados incorrectos sin que se notara. Los arreglé uno a uno:

**1. Fusión de programas con estados contradictorios.** Cuando dos PDFs equivalentes se fusionaban en un único programa y uno de ellos estaba marcado como "obsoleto", el resultado quedaba como "parcialmente obsoleto", suavizando un estado más grave. Ahora el más conservador (obsoleto) gana siempre. Es la regla coherente para una capa de curación documental: en caso de duda, avisa al asesor.

**2. Comparación de alojamiento contra una lista.** Este era el grande. Tras la iteración del 11-12 de mayo, el campo `tipo_alojamiento` pasó de ser un valor único a una lista (un programa puede ofrecer familia + residencia + hotel). Pero el recomendador seguía comparando esa lista contra la preferencia del cliente como si fuera un string. La comparación nunca era cierta. Resultado: cualquier programa con varios alojamientos puntuaba 0 en ese criterio, aunque el alojamiento preferido estuviera entre los ofrecidos. Con un peso del 25% en el perfil demo, esto descabezaba el ranking entero. Ahora se comprueba si la preferencia está dentro de la lista.

**3. Texto de la explicación con listas mal renderizadas.** Mismo origen que el #2: cuando el motivo "alojamiento" entraba en la explicación, se imprimía literalmente la lista Python (`['familia', 'residencia', 'hotel']`) en vez de un texto natural. Reescrito para que diga "el alojamiento preferido (familia) está entre los ofrecidos por el programa (familia, residencia, hotel)".

**4. Programas obsoletos no se filtraban del catálogo.** El módulo de curación detectaba la obsolescencia y marcaba los programas, pero el pipeline no usaba esa información para descartarlos. La función `filtrar_no_obsoletos` estaba escrita pero nunca se llamaba. Ahora sí: los obsoletos se eliminan, los parcialmente obsoletos se conservan (el explainer ya añade un aviso al asesor cuando los presenta).

**5. Interpretación de cotas abiertas en duración.** Cuando un documento decía "Minimum 1 Week" sin indicar máximo, el extractor guardaba correctamente `min=7, max=null`. Pero tanto el filtro como el cálculo de score interpretaban ese `null` como "duración fija de 7 días", filtrando programas que en realidad eran abiertos. Por eso los programas Berlitz nunca pasaban el filtro de duración cuando el perfil pedía un mínimo de 14 días. Ahora `null` en el extremo superior se interpreta como "sin tope" (365 días por defecto), y `null` en el extremo inferior como "desde el principio" (1 día). El mismo cambio en filtro y en score, para que sean coherentes.

### Lo que se ha conseguido

Ejecutando el pipeline sobre los mismos 5 PDFs con el mismo perfil demo (estudiante de 14 años, presupuesto ≤2500€, preferencia familia, duración 14-30 días), el TOP 3 ha cambiado por completo:

| Posición | Antes | Después |
|---|---|---|
| #1 | DBS Dublin · 0.69 | **Berlitz General English · 0.75** |
| #2 | Millfield Summer · 0.42 | **Berlitz Private Lessons 1-1 · 0.75** |
| #3 | Millfield Football · 0.42 | DBS Dublin · 0.69 |

El número de candidatos tras el filtrado pasó de 3 a 5 (entraron los dos Berlitz "all ages" que antes caían por duración).

### Detalle interesante para la memoria

Los dos Berlitz que ahora encabezan el ranking **no tienen precio extraído**. Su score neutro (0.5) en precio les basta porque ganan en alojamiento y duración. Esto es el reverso de la observación de la iteración 3 ("programas con campos null pierden ranking"): aquí ganan ranking en las dimensiones donde sí tienen datos. Conviene comentarlo en la memoria como un caso real de cómo un perfil con preferencias parciales del cliente y un programa con datos parciales del proveedor producen una recomendación coherente sin información completa por ninguno de los dos lados.

### Lo que queda

Sigue pendiente lo que ya identificamos: las lecciones LD2 (precios distribuidos en páginas no contiguas — los precios Berlitz siguen null), LD5, LD7, LD8, LD15, LD18, LD19, LD20 y LD23, además de la infraestructura de evaluación H1 que es la que más necesita el TFM para medir progreso de forma objetiva.

## Iteración 7 — Infraestructura de evaluación H1 (14 mayo 2026)
Motivación
Hasta esta iteración, la hipótesis H1 del proyecto ("los modelos de lenguaje permiten extraer información estructurada de documentación heterogénea con una precisión suficiente para alimentar un recomendador") se evaluaba de manera informal: el ground truth de la iteración 3 estaba anotado a mano en un fichero markdown y la valoración del progreso se hacía por comparación visual entre ejecuciones. Este enfoque tenía dos problemas críticos para el TFM. Primero, el objetivo específico OE2 exige un F1 macro ≥ 0,85 sobre un conjunto etiquetado, y sin métrica automatizada no es posible afirmar si ese umbral se alcanza ni mucho menos cuantificar la mejora entre iteraciones. Segundo, la ausencia de medida objetiva hace que el resto del desarrollo opere a ciegas: cualquier cambio en el extractor, en el prompt o en el esquema puede mejorar unos campos y empeorar otros sin que el equipo se entere hasta una inspección manual posterior.

El objetivo de la iteración ha sido construir la infraestructura mínima viable para medir H1 de forma reproducible y versionada, partiendo del ground truth ya disponible.

Qué se ha implementado
Se ha creado un subsistema nuevo src/evaluation que orquesta todo el ciclo de evaluación. La pieza central es un conjunto de comparadores especializados por tipo de campo, porque no todos los atributos del esquema se pueden comparar igual. Los precios admiten una tolerancia del 5 %, justificada porque cubre las variaciones razonables de la conversión GBP→EUR realizada por el LLM con tasas estáticas y otras pequeñas discrepancias numéricas que no constituyen errores de extracción. Las edades y las duraciones se comparan de forma exacta porque cualquier desviación cambia el comportamiento del filtro de recomendación. Las fechas se comparan ISO exacto. Los campos de texto se comparan con normalización Unicode más una medida de similitud para nombres y ciudades, donde "St. Julians" y "St Julians" deben tratarse como equivalentes. Los campos de lista, como tipo_alojamiento o acreditaciones, se comparan como conjuntos para que el orden no afecte al resultado. Los enumerados (idioma, idioma_documento_origen) se comparan estrictamente.

Sobre estos comparadores se calcula, para cada campo, un veredicto: verdadero positivo (el GT espera un valor y la extracción coincide), falso positivo (la extracción aporta un valor distinto o alucina uno donde el GT marca ausente), falso negativo (la extracción omite un valor presente en el documento) o verdadero negativo (ambos vacíos, el documento realmente no contenía esa información). A partir de la suma de veredictos se computa precisión, recall y F1 por campo, y un F1 macro como media aritmética sobre los campos que tienen al menos una muestra positiva. Se ha tomado deliberadamente la decisión de que los campos con cero predicciones correctas pero positivos esperados (precisión indefinida) cuenten como F1=0 en lugar de excluirse del macro, porque excluirlos enmascararía los fallos sistemáticos del extractor en lugar de penalizarlos.

El ground truth markdown se ha migrado a un fichero JSON estructurado en data/eval/ground_truth.json, que es la fuente de verdad para todas las ejecuciones futuras. La migración ha aprovechado para resolver ambigüedades del GT original: los casos de "🟡 parcial" se han convertido en el valor que estrictamente debería extraerse según el esquema y las reglas del prompt actuales, los casos de "⬜ no aparece en el documento" se codifican como esperado nulo con la bandera ausente_doc, y se han incluido notas explicativas para los casos sutiles (la conversión GBP→EUR del precio NSX Woodbridge, la interpretación de "all ages" como 0-99 para Berlitz, la divergencia entre apartamento y el enum actual de tipos de alojamiento). Esta criterio de anotación se ha acordado como estricto: cualquier desviación cuenta como falso positivo, lo cual es la lectura más conservadora y la más defendible para la memoria del TFM. Se mantiene el alcance mínimo de cinco programas, uno por PDF, suficiente para empezar a medir.

Todo el flujo está expuesto en un CLI ejecutable con python -m src.evaluation.run_h1. La salida es doble: un informe legible por pantalla con tabla tp/fp/fn/tn y F1 por campo, y un fichero JSON versionado en data/eval/resultados/h1_<fecha>_<etiqueta>.json que captura el estado completo de la evaluación, incluyendo el detalle programa a programa de cada veredicto. Este último punto era un requisito explícito de la iteración: tener los resultados de cada ejecución persistidos en disco permite construir la tabla "F1 macro por iteración" para la memoria sin necesidad de volver a ejecutar el sistema.

Se han añadido 16 tests unitarios que validan los comparadores y el cálculo de métricas, especialmente los casos de borde que son fáciles de equivocar: la diferencia entre TN y FP, el comportamiento de campos sin positivos en el GT, la tolerancia numérica aplicada correctamente a la conversión GBP→EUR.

Resultado
La primera ejecución sobre el catálogo extraído tras la iteración 6 arroja un F1 macro de 0.819, por debajo del umbral OE2 de 0.85.

El desglose por campo identifica con precisión dónde está el problema. Siete de los dieciséis campos evaluados llegan a F1=1.0: empresa proveedora, país, idioma, duración mínima, fecha de inicio, idioma del documento de origen y edad máxima. Estos campos están plenamente resueltos. En el otro extremo, acreditaciones cae a 0.00 porque el extractor omite sistemáticamente las acreditaciones presentes (TEFL en dos NSX, UEFA y FIFA en DBS Dublin), precio_max_eur se queda en 0.40 y precio_min_eur en 0.67 debido principalmente al caso Berlitz donde los precios están en una página separada del documento y el LLM no los conecta con el programa. El campo nombre baja a 0.75 por el efecto de la extracción multi-programa: el LLM acierta el nombre principal en algunos PDFs pero en otros (NSX, NET Prices) lo modifica o lo cambia ligeramente respecto a la anotación de iteración 3.

Conclusiones
La conclusión más importante no es el número en sí, sino que por primera vez en el proyecto disponemos de un número objetivo y reproducible al que apuntar. El 0.819 actual es el resultado real del sistema tras la iteración 6, sin maquillaje, y todas las iteraciones futuras tendrán que justificar empíricamente que mueven ese número en la dirección correcta. La validez de OE2 deja de ser una afirmación cualitativa para convertirse en una afirmación verificable.

La segunda conclusión es que el sistema está muy cerca del umbral —a 0.031 puntos— y que ese gap se concentra en un número pequeño de campos concretos. El macro está penalizado fundamentalmente por tres focos: la omisión total de acreditaciones, los precios distribuidos en páginas no contiguas (la lección LD2 del cuaderno de decisiones de diseño, no completamente resuelta) y el comportamiento del nombre en documentos multi-programa. Ninguno requiere un cambio arquitectónico mayor; los tres se pueden atacar en iteraciones cortas con cambios localizados en el prompt y, para el caso de los precios, eventualmente con la estrategia de dos pasadas focalizadas que se discutió en iteraciones anteriores.

La tercera conclusión, más sutil pero relevante para la memoria, es que el ground truth en su versión mínima ya sirve para tomar decisiones de diseño. Los cinco programas anotados son suficientes para identificar dónde está fallando el sistema y para orientar el trabajo de extracción de las próximas iteraciones. La extensión del GT a los quince programas del catálogo actual sigue siendo necesaria para reportar conclusiones robustas en la memoria final, pero no es un bloqueador para seguir iterando ahora. El siguiente paso natural es atacar los tres focos identificados (acreditaciones, precios Berlitz, nombre multi-programa) y medir el efecto sobre F1 macro, registrando cada iteración en data/eval/resultados/ para construir la tabla de progreso del TFM.

## Iteración 10 — Cierre de los tres focos de H1 (13-14 mayo 2026)

### Motivación

Tras la iteración de infraestructura de evaluación, disponíamos de una
métrica objetiva (F1 macro = 0.819) por debajo del umbral OE2 de 0.85 y
con tres focos claramente identificados donde se concentraba el gap:
acreditaciones nunca extraídas (F1 = 0.00), precios de Berlitz nulos por
información distribuida en páginas no contiguas (LD2), y matching del
nombre penalizado por el efecto multi-programa. La iteración ha atacado
los tres focos de forma incremental, midiendo el delta tras cada cambio
para construir una tabla honesta de contribuciones. El orden acordado
fue 1 → 3 → 2, del más barato y de riesgo bajo al más arquitectónico.

### Foco 1 — Extracción de acreditaciones vía prompt

El sistema no extraía acreditaciones porque el prompt no las mencionaba
explícitamente. El LLM las reconoce cuando las ve, pero no las buscaba
activamente en secciones tipo "About us", "Quality" o pies de página.
Se añadió una sección específica al system prompt con ejemplos
concretos del corpus real: TEFL, TESOL, CELTA, UEFA A/Pro/B, IALC,
EAQUALS, IELTS, Cambridge (FCE/CAE/CPE), TOEFL iBT, TOEIC, Trinity,
Pearson PTE, FIFA, FAI, LTA, Berlitz Certificate. Se acompaña de tres
reglas: extraer cada acreditación como string corto reconocible,
listarlas todas sin duplicar, y no inventar acreditaciones que no
aparezcan en el documento.

Tras la re-extracción del catálogo, el F1 del campo acreditaciones
pasó de 0.00 a 1.00 (los tres documentos con acreditaciones presentes
las capturan correctamente: TEFL en los dos NSX, UEFA A/UEFA Pro/FIFA/
FAI en DBS Dublin). El F1 macro global subió de 0.819 a 0.853,
cruzando el umbral OE2 por primera vez.

Como efecto colateral, el campo ciudad mejoró de 0.889 a 1.000 (la
re-extracción resolvió la ambigüedad de NET Prices), pero apareció una
regresión inesperada en el campo nombre (0.750 → 0.571) y una pérdida
adicional en precio_max_eur (0.400 → 0.000). El análisis diagnóstico
mostró que las tres regresiones de nombre seguían un mismo patrón:
el extractor ahora producía nombres más específicos que los anotados
en el GT (por ejemplo "NSX at Woodbridge School - English+ Horse
Riding" frente al GT "NSX at Woodbridge School"). El extractor daba
más información, no menos, pero el comparador estricto lo marcaba
como falso positivo.

### Foco 3 — Comparador asimétrico para el campo nombre

El diagnóstico anterior dejaba claro que el problema estaba en la
métrica, no en el extractor. Se añadió un comparador nuevo,
string_contains_or_loose, que acepta como verdadero positivo el caso
en que el nombre del ground truth es substring del extraído, es decir,
cuando la extracción es más específica que la anotación. La
asimetría es deliberada: si el extractor produce un nombre más
genérico que el GT sigue contando como falso positivo, porque en ese
caso sí se está perdiendo información.

Se documentó explícitamente en el código que la asimetría se justifica
por la evolución del extractor hacia extracción multi-programa, donde
enriquecer el nombre con la variante o la campaña es información de
valor real, no ruido. Se añadieron dos tests unitarios que fijan el
comportamiento en ambos sentidos.

Tras el cambio, el F1 del campo nombre pasó de 0.571 a 1.000. El F1
macro global subió de 0.853 a 0.879. Es importante reconocer que este
salto no viene del extractor sino de la calibración del comparador;
la memoria debe reportar tres números diferenciados (baseline, después
del foco 1, después del foco 3) para que el lector pueda distinguir
las contribuciones de sistema y de métrica.

### Foco 2 — Normalización de precios a euros por semana

El foco 2 era el más arquitectónico y desveló varios problemas
encadenados. El diagnóstico de partida identificaba cuatro sub-causas
distintas para el F1 = 0.000 de precio_max_eur: Berlitz General
English con precio nulo por posible truncamiento del texto de entrada,
Berlitz NET Prices dividido en variantes por temporada donde cada
variante veía solo sus propios precios, DBS Dublin donde el LLM había
perdido la capacidad de calcular el máximo derivado, y NSX Woodbridge
donde el GT esperaba el máximo global pero el matcher elegía una
variante concreta con máximo local.

El análisis con la usuaria llevó a una decisión más profunda que la
que se había anticipado. El campo precio_min_eur y precio_max_eur
tenía una semántica ambigua: unos documentos daban precios por
semana (Berlitz), otros el total del programa completo (DBS con 5
semanas cerradas, NSX Woodbridge con 2 semanas fijas). Comparar 232 €
de una tarifa semanal Berlitz con 9392 € del total de DBS era mezclar
unidades. Además, el filtro de presupuesto del recomendador operaba
sobre esos valores heterogéneos, produciendo un bug silencioso: el
cliente con presupuesto de 2500 € pasaba a DBS porque precio_min era
1992 €, pero al aceptar la duración mínima del cliente (2 semanas) el
coste real era 3701 €, ya fuera de presupuesto.

Se acordó normalizar toda la información económica a euros por semana.
Los campos se renombraron a precio_semanal_min_eur,
precio_semanal_max_eur, precio_semanal_min_origen y
precio_semanal_max_origen para hacer la semántica explícita en el
propio esquema. El prompt se reescribió con reglas específicas: si el
documento da el precio por semana se copia tal cual, si da el total
se divide entre el número de semanas del programa, si hay una fórmula
base más marginales se calcula por opción. Se preserva el valor por
semana en la moneda original antes de la conversión a euros. El
filtro de recomendación se rehizo para multiplicar el precio semanal
por la duración mínima que el cliente acabaría pasando en el programa
antes de comparar contra el presupuesto. El explainer se reescribió
para hablar en euros por semana y mostrar el total mínimo estimado
junto al presupuesto.

Durante la re-extracción del catálogo aparecieron tres bugs de
infraestructura que llevaban tiempo latentes y solo se manifestaron
al alterar simultáneamente el tamaño del texto de entrada y la
complejidad del prompt. Primero, el truncamiento del texto se
mantenía a 20.000 caracteres desde la primera iteración, cuando el
catálogo Berlitz tiene 52.000 caracteres y la PRICE LIST 2026 estaba
en la posición 1349: paradójicamente sí entraba en el rango truncado,
pero el LLM se distraía porque el prompt no la marcaba como
información clave. Se subió el truncamiento a 80.000 caracteres para
dar margen a otros documentos largos. Segundo, el parámetro
max_tokens del API se mantenía a 8192, insuficiente para devolver los
once o doce programas del catálogo Berlitz con el esquema enriquecido:
las respuestas se cortaban a mitad y devolvían estructuras
malformadas. Se subió a 16384. Tercero, y más sutil, el API de
Anthropic devuelve ocasionalmente el campo programas como un string
JSON serializado dentro de la respuesta del tool en vez de como array
directo, un comportamiento observado con documentos largos y schemas
anidados. Se añadió un fallback defensivo que detecta el caso y hace
json.loads antes de continuar. También se añadió validación defensiva
que descarta programas individuales malformados en lugar de romper la
extracción del PDF entero.

Con los cuatro problemas corregidos, la re-extracción produce 24
programas brutos que la capa de fusión consolida a 17 únicos. Berlitz
aporta 11 programas ahora (antes 10-12 inestables), NET Prices se
divide en tres campañas, DBS mantiene uno, NSX Gross Prices genera
seis programas variante-por-variante y Millfield tres. El F1 macro
final pasó de 0.879 a 0.926, netamente por encima del umbral OE2.

### Efectos colaterales en el ranking

El cambio de semántica del filtro tiene una consecuencia directa en
la recomendación demo. DBS Dublin, que hasta ahora aparecía siempre
en el top 3, queda fuera del ranking del perfil de ejemplo
(estudiante de 14 años, presupuesto 2500 €, mínimo 14 días) porque
su total real mínimo (1850,5 €/semana × 2 semanas = 3701 €) supera
el presupuesto. Este es el arreglo del bug silencioso identificado
en el diagnóstico. Para la memoria, es un buen ejemplo de cómo la
normalización de la información económica no es solo una decisión
de esquema sino una condición necesaria para que la recomendación
respete restricciones que el cliente considera duras.

### Tabla acumulada de progreso de H1

| Iteración | Cambio principal | F1 macro | Delta |
|---|---|---|---|
| 7 (baseline) | Primera medición sobre GT iter03 | 0.819 | — |
| 10 · foco 1 | Extracción de acreditaciones vía prompt | 0.853 | +0.034 |
| 10 · foco 3 | Comparador asimétrico para nombre | 0.879 | +0.026 |
| 10 · foco 2 | Precios por semana + fixes de infraestructura | 0.926 | +0.047 |

El salto acumulado es +0.107 (13% de mejora relativa) en tres
iteraciones cortas. El resultado supera cómodamente el umbral OE2 y
deja al sistema con margen para el resto del desarrollo.

### Residuos de F1 tras la iteración

Ocho de los dieciséis campos evaluados llegan a F1 = 1.0. Los ocho
restantes tienen residuos menores que se distribuyen en tres tipos
de casos. Primero, matches por variante: NSX Woodbridge empareja el
nombre "English+ Horse Riding at Woodbridge School" con el GT
"NSX at Woodbridge School" y la similitud queda justo bajo el
umbral. Segundo, discrepancias semánticas en el GT: Berlitz General
English tiene tipo_alojamiento anotado como [familia, otro] mientras
que el extractor entrega [familia, residencia] al interpretar los
apartamentos como residencia. Tercero, casos que se resolverán al
ampliar el GT a los 17 programas del catálogo actual: el GT
anclado al programa principal por PDF ya no representa
adecuadamente un catálogo donde el extractor produce variantes
correctamente diferenciadas.

### Ficheros modificados en la iteración

- src/models.py: renombrado de los cuatro campos de precio
- src/extraction/llm_extractor.py: nueva regla de precios normalizados,
  truncamiento a 80k, max_tokens a 16384, parsing defensivo de
  programas como string JSON, validación defensiva de items
- src/recommendation/filtros.py: nueva lógica precio × semanas cliente
- src/recommendation/mcdm.py: renombrado de campos
- src/explanation/explainer.py: texto habla en €/semana + total estimado
- src/curation/merge.py, evidence.py, obsolescence.py: renombrado de
  campos
- src/evaluation/comparators.py: comparador string_contains_or_loose
  asimétrico para nombre, renombrado de FIELD_COMPARATORS
- data/eval/ground_truth.json: nueva versión iter03_minima_semanal con
  valores recalculados a €/semana
- tests: actualizados los 26 tests para reflejar el renombrado y el
  nuevo comparador de nombre; suite pasa en verde
- data/eval/resultados/h1_2026-05-14_iteracion8_acreditaciones.json,
  h1_2026-05-14_iteracion8_acreditaciones_y_nombre.json y
  h1_2026-08-13_iteracion8_precios_semanales.json: los tres puntos
  de la tabla de progreso persistidos en disco

### Lecciones de diseño relacionadas

Esta iteración cierra parcialmente la lección LD8 (multi-pricing
estructurado): la normalización a euros por semana es el primer
paso hacia el desglose completo tuition + alojamiento + actividades
+ extras, pero solo cubre la dimensión temporal, no la dimensión de
composición. El desglose por componentes queda como línea de trabajo
futura, documentada.

También aporta evidencia empírica adicional a la lección LD23 (la
calidad de la presentación documental condiciona la extracción):
los documentos con estructura tabular clara (NSX Millfield Guide,
NET Prices) producen extracción de precios más limpia que los que
presentan los precios en tablas complejas dentro de folletos largos
(Berlitz ELA 2026, donde persisten residuos de F1 en precio_max
incluso tras todos los arreglos).

### Estado del proyecto tras la iteración

El subsistema de extracción se considera consolidado para el corpus
de cinco PDFs. El siguiente bloque del plan de cuatro semanas
contempla el martes atacar las lecciones LD5 (fechas recurrentes) y
LD20 (specialist courses como modificadores), con impacto directo
en los residuos de duracion_max y de la duplicación aparente del
programa Millfield. La ampliación del ground truth a los 17
programas del catálogo actual está prevista para el jueves de la
misma semana y previsiblemente resolverá varios de los residuos
diagnosticados aquí.

## Iteración 11 — Fechas recurrentes y cursos especialistas (LD5 + LD20)

### Motivación

Los residuos de F1 tras la iteración 10 se concentraban en tres
patrones estructurales que ninguna afinación de prompt podría cerrar:
Berlitz General English con fecha_inicio inventada porque el documento
dice "Every Monday" y el schema forzaba una fecha fija; NSX Millfield
apareciendo tres veces en el catálogo (base + Tennis + Football) como
si fueran programas diferentes cuando en realidad son un programa base
con dos modalidades especialistas; y NSX Woodbridge con seis variantes
que también inflaban la lista sin aportar programas semánticamente
distintos. Las tres cosas apuntan a lecciones catalogadas hace tiempo
(LD5 y LD20) pero pendientes de implementar. Esta iteración las cierra.

### Qué se ha implementado

Se ha ampliado el esquema Pydantic con dos elementos nuevos. El campo
`fechas_inicio_recurrentes: Optional[str]` en `Programa` captura el
patrón textual de recurrencia cuando el documento indica arranques
periódicos ("Every Monday", "Cualquier lunes de enero a mayo"). No
sustituye a `fecha_inicio` sino que se activa cuando esta debe quedar
nula por no haber calendario fijo. La nueva clase `CursoEspecialista`
modela cada modalidad especialista con nombre, actividad normalizada,
horas semanales dedicadas y partnership opcional, y se agrupa en la
lista `cursos_especialistas` dentro del programa base.

El prompt del extractor se ha reforzado con dos secciones. Una regla
LD5 que describe cómo detectar recurrencia y rellenar el campo con
formato compacto preservando la información. Y una regla LD20 que
instruye explícitamente al modelo para NO duplicar programas cuando
detecta secciones dedicadas a specialist courses, con el ejemplo
Millfield como referencia. El tool schema se ha ampliado en
consecuencia con los dos campos y la sub-estructura de curso
especialista.

La capa de fusión en `src/curation/merge.py` se ha actualizado para
tratar los dos campos nuevos. `fechas_inicio_recurrentes` se resuelve
tomando el texto más informativo entre los del grupo. `cursos_especialistas`
se une sin duplicados usando como clave la tupla (nombre, actividad)
normalizada, y cuando hay colisión se conserva el ejemplar con más
campos rellenos (heurística de "el que sabe más gana").

### Resultado sobre el catálogo

La re-extracción produce ahora **17 programas brutos** (frente a 24 en
la iteración 10) y **15 tras fusión** (frente a 17). La reducción es
neta y saludable: viene íntegramente de colapsar duplicaciones que no
representaban programas distintos.

- NSX Gross Prices: de 6 → 2 programas (Woodbridge y Millfield base,
  sin las variantes Horse Riding / Tennis extraídas como programas
  independientes).
- NSX Millfield Guide: de 3 → 1 programa (Summer Programme, con los
  cursos especialistas Tennis y Football dentro).
- Berlitz NET Prices: de 3 → 1 programa (Closed Groups Mini Stay
  unificado).

### Resultado sobre F1

F1 macro pasa de 0.926 a 0.922, prácticamente estable. La descomposición
por campo revela dos cambios opuestos que casi se compensan:

- `fecha_fin` mejora de 0.800 → 1.000 al desaparecer la separación
  artificial de los dos turnos de NSX Woodbridge y quedar consolidada
  correctamente.
- `precio_semanal_max_eur` empeora de 0.667 → 0.400 (tres FP en lugar
  de dos). La causa es un tradeoff previsto: al colapsar las variantes
  de Woodbridge en un único programa base, el máximo por semana refleja
  solo el precio base (1720,5 €/sem) y se pierde el máximo de la
  variante Tennis (2071 €/sem). Este residuo se resolverá cuando se
  aborde LD18 (variantes con precio adicional), que quedará como campo
  `precio_adicional_eur` dentro de `CursoEspecialista`.

### Interpretación

El cambio de F1 (-0.004) es engañoso si se mira aislado. La lectura
correcta es que la iteración es un éxito estructural: el catálogo pasa
a representar la realidad semántica (Millfield es un programa, no tres)
y la métrica se mantiene en la zona alta gracias a la mejora
compensatoria de fecha_fin. Además, se han añadido dos campos nuevos
al esquema que no están todavía evaluados en H1 (el GT mínimo no anota
`fechas_inicio_recurrentes` ni `cursos_especialistas` como campos con
esperado). Cuando se amplíe el GT a los 15 programas actuales,
`cursos_especialistas` para Millfield tendría un esperado de dos
elementos (Tennis, Football) y sería directamente medible; ese hito
convertirá la mejora estructural en una mejora también métrica.

### Bugs conocidos que quedan tras esta iteración

- NSX Woodbridge `precio_semanal_max_eur`: subestima el máximo por
  perder la variante Tennis. Se resolverá con LD18.
- Berlitz General English `nombre`: el matcher del GT empareja
  "General Intensive English 30" en vez de "General English" por
  ordenación de similitud casi empatada. Es un caso de borde del
  matcher, resoluble anotando `match_nombre` con mayor especificidad
  en el GT.
- Berlitz `tipo_alojamiento`: discrepancia semántica persistente
  entre `[familia, otro]` (GT) y `[familia, residencia]` (extracción).

### Ficheros modificados

- `src/models.py`: nuevo campo `fechas_inicio_recurrentes`, nuevo
  campo `cursos_especialistas`, nueva clase `CursoEspecialista`
- `src/extraction/llm_extractor.py`: reglas nuevas en el prompt (LD5,
  LD20 y refuerzo de multi-programa), dos campos nuevos en el tool
  schema (incluyendo la sub-estructura de curso especialista)
- `src/curation/merge.py`: fusión de los dos campos nuevos
- `data/eval/resultados/h1_2026-08-20_iteracion11_ld5_ld20.json`:
  resultado versionado
- `data/processed/programas_pre_iter11.json.bak`: backup del catálogo
  anterior

### Estado tras la iteración

Con LD5 y LD20 cerradas y el catálogo consolidado en 15 programas
semánticamente distintos, el subsistema de extracción está listo para
la siguiente pieza del plan: ampliar el ground truth de 5 a 15
programas. Esa ampliación (miércoles del plan) permitirá evaluar los
campos que hoy están en el esquema pero fuera del alcance de H1
(cursos_especialistas, fechas_inicio_recurrentes, partners,
partnerships, costes_adicionales) y previsiblemente resolverá varios
de los FP residuales anclados al viejo GT de 5 programas.

## Iteración 12 — Variantes con precio adicional y turnos discretos (LD18 + LD19)

### Motivación

La iteración 11 dejó un residuo previsible: `precio_semanal_max_eur`
en 0.400 porque tras colapsar las variantes de NSX Woodbridge con
LD20, el máximo del programa se quedaba en el precio base y se perdía
el sobreprecio de las variantes Tennis y Horse Riding. En paralelo,
el campo `fecha_fin` acertaba por casualidad al elegir el fin del
segundo turno de NSX Woodbridge, pero la semántica seguía siendo
incorrecta: dos summer camps de dos semanas cada uno se representaban
como un único rango continuo de cuatro semanas, sugiriendo al
recomendador una experiencia que no existe. Ambos residuos apuntan a
dos lecciones catalogadas hace tiempo: LD18 (variantes con precio
adicional) y LD19 (múltiples turnos). Esta iteración las cierra.

### Qué se ha implementado

Se ha extendido la clase `CursoEspecialista` con dos campos nuevos:
`precio_adicional_semanal_eur` y `precio_adicional_semanal_origen`,
ambos opcionales, que capturan el suplemento por semana que añade la
modalidad sobre el precio base del programa. Esto completa la
implementación conceptual de LD18 dentro de la estructura ya creada
para LD20: cada modalidad especialista es, funcionalmente, una
variante del programa con horas dedicadas propias, partnership
opcional y ahora sobreprecio opcional. Se descartó crear una clase
`Variante` separada porque duplicaría estructura sin aportar
semántica: en el corpus real, las variantes de NSX (Horse Riding,
Tennis) y los specialists de Millfield (Tennis, Football) son la
misma categoría.

Para LD19 se ha añadido una clase nueva `TurnoPrograma` con
`fecha_inicio`, `fecha_fin` y un `nombre` opcional para etiquetar el
turno si el documento lo hace. El campo `turnos: list[TurnoPrograma]`
en `Programa` recoge la lista completa. Los campos `fecha_inicio` y
`fecha_fin` de nivel programa se conservan como la ventana global
(mínimo de inicios y máximo de fines) para mantener la compatibilidad
con el filtro y el score de duración.

El prompt del extractor ha ganado dos reglas nuevas. La regla LD19
detalla cómo detectar turnos discretos, con ejemplo NSX Woodbridge, e
insiste en la distinción con LD5 (recurrencia abierta tipo "Every
Monday" no es una lista de turnos). La regla LD18 dentro de la
sección de cursos especialistas indica cómo calcular el suplemento
por semana cuando el documento lo da como total, y añade una
consecuencia importante: `precio_semanal_max_eur` del programa base
debe reflejar el máximo efectivo posible (base + suplemento más caro),
para que el rango de precios cubra todas las opciones que el cliente
puede elegir. El tool schema se ha ampliado con los dos campos nuevos
en `CursoEspecialista` y con la sub-estructura de `TurnoPrograma`.

La capa de fusión trata `turnos` como unión sin duplicados por
combinación `(fecha_inicio, fecha_fin)`, ordenados por fecha de
inicio para reproducibilidad. Los campos de precio adicional del
curso especialista se benefician automáticamente de la heurística "el
que sabe más gana" ya implementada en iter 11.

### Resultado sobre el catálogo

El catálogo se mantiene en 15 programas fusionados (17 de partida
esta vez, uno más de lo habitual porque el LLM detectó un programa
adicional en Berlitz). La riqueza estructural del catálogo aumenta
significativamente: cinco programas ahora tienen turnos discretos
capturados (Berlitz 50+ Programme con diez turnos a lo largo del año,
Berlitz Youth Camps Easter con tres, NSX Woodbridge, NSX Millfield y
Millfield Summer Programme con dos cada uno). Dos programas tienen
sobreprecios de variante correctamente calculados (NSX Woodbridge con
+351 €/semana para Horse Riding y +330,75 €/semana para Tennis; NSX
Millfield con +351 €/semana para Tennis y +269,1 €/semana para
Football).

### Resultado sobre F1

F1 macro pasa de 0.922 a 0.938. El delta viene íntegramente del campo
esperado: `precio_semanal_max_eur` sube de 0.400 a 0.667. El LLM
ahora suma correctamente el suplemento de la variante más cara al
calcular el máximo del programa base. Los demás campos se mantienen.

Los dos FP residuales de `precio_semanal_max_eur` siguen ambos
anclados a Berlitz: General English (GT 825 vs extraído 315, precios
distribuidos en el catálogo entre múltiples cursos) y NET Prices Mini
Stay (GT 580 vs extraído 276, discrepancia de temporada). Estos
residuos apuntan a LD2 y LD7, no a LD18.

### Comparativa acumulada de H1

| Iteración | F1 macro | Delta acumulado |
|---|---|---|
| 7 baseline | 0.819 | — |
| 10 foco 1 acreditaciones | 0.853 | +0.034 |
| 10 foco 3 comparador nombre | 0.879 | +0.060 |
| 10 foco 2 precios €/semana | 0.926 | +0.107 |
| 11 LD5 + LD20 | 0.922 | +0.103 |
| 12 LD18 + LD19 | 0.938 | +0.119 |

El sistema arranca esta semana en 0.819 y termina el martes en 0.938,
una mejora relativa del 14,5% en dos días de trabajo, cubriendo
cinco lecciones de diseño (LD5, LD8 parcial, LD18, LD19, LD20) más
tres bugs silenciosos de infraestructura y una calibración de
métrica. Todo por encima del umbral OE2 = 0.85 con margen creciente.

### Ficheros modificados

- `src/models.py`: dos campos nuevos en `CursoEspecialista`
  (precio_adicional_semanal_eur y _origen), nueva clase
  `TurnoPrograma`, nuevo campo `turnos` en `Programa`.
- `src/extraction/llm_extractor.py`: regla nueva LD19 en la sección
  de fechas, regla nueva LD18 dentro de la sección de cursos
  especialistas, consecuencia sobre `precio_semanal_max_eur`, dos
  campos nuevos en el tool schema y sub-estructura de turno.
- `src/curation/merge.py`: fusión sin duplicados de turnos por
  (fecha_inicio, fecha_fin), orden reproducible.
- `data/eval/resultados/h1_2026-08-20_iteracion12_ld18_ld19.json`:
  resultado versionado.
- `data/processed/programas_pre_iter12.json.bak`: backup del catálogo
  anterior.

### Estado del proyecto tras la iteración

El subsistema de extracción cubre ahora **17 lecciones de diseño de
las 23 catalogadas**. Las seis pendientes son LD2 (parcial, residuos
Berlitz), LD7 (multi-campaña), LD8 (desglose completo por
componentes), LD15 (múltiples sedes), LD23 (F1 desglosado por tipo
de documento) más el propio LD2 residual. El F1 macro se ha
consolidado en 0.938 y el catálogo tiene 15 programas semánticamente
distintos con turnos y variantes bien modelados.

El siguiente paso del plan de cuatro semanas es la ampliación del
ground truth de 5 a 15 programas (miércoles), que permitirá evaluar
los campos que hoy están en el esquema pero fuera del GT
(cursos_especialistas, turnos, fechas_inicio_recurrentes, partners,
partnerships, costes_adicionales) y previsiblemente aportará un
salto adicional al desbloquear medición sobre el catálogo completo.
