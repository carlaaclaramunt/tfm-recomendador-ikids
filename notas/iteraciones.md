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

### Iteración del 11 de mayo 2026 — bloque de curación documental

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

## Iteracion
La transición del esquema mono-programa al esquema multi-programa, combinada con el módulo de fusión post-extracción, permite expandir el catálogo de 5 a 24 entradas brutas y consolidarlas a 15 entradas únicas tras la deduplicación inter-documental. El ratio de unificación del 37,5% confirma que la información sobre un mismo programa se reparte de forma significativa entre múltiples documentos del corpus, validando empíricamente la necesidad del subsistema de curación documental."

## Iteración del 11–12 de mayo de 2026 — capa avanzada de curación documental y trazabilidad de extracción

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