# Estado del proyecto — snapshot 14 mayo 2026 (post-iteración 12)

Este documento es una foto puntual del estado del proyecto. Para el
detalle de qué se hizo en cada iteración, ver `iteraciones.md`. Para el
catálogo completo de lecciones de diseño identificadas, ver
`decisiones_diseno.md`.

## Métrica principal — hipótesis H1

**F1 macro actual: 0.938** sobre ground truth mínimo (5 programas anotados).

Umbral OE2: ≥ 0.85 → cumplido con margen.

Historial versionado en `data/eval/resultados/`:

| Iteración | F1 macro | Delta | Notas |
|---|---|---|---|
| 7 (baseline) | 0.819 | — | Primera medición sistemática |
| 10 · foco 1 | 0.853 | +0.034 | Acreditaciones vía prompt |
| 10 · foco 3 | 0.879 | +0.026 | Comparador nombre asimétrico |
| 10 · foco 2 | 0.926 | +0.047 | Precios €/semana + fixes infra |
| 11 · LD5+LD20 | 0.922 | -0.004 | Fechas recurrentes + specialist courses (cambio estructural, F1 estable) |
| 12 · LD18+LD19 | 0.938 | +0.016 | Precio adicional por variante + turnos discretos |

## Catálogo actual

- 5 PDFs de entrada (2 Berlitz + 1 DBS + 2 NSX)
- **18 programas** extraídos brutos
- **15 programas** en catálogo tras fusión
- Ratio de unificación: 17%

Distribución por proveedor tras extracción:
- Berlitz ELA 2026: 13 programas
- Berlitz NET Prices: 1 programa (unificado)
- DBS Dublin: 1 programa
- NSX Gross Prices: 2 programas (Woodbridge y Millfield, con specialists dentro)
- NSX Millfield Guide: 1 programa (Summer Programme con specialists Tennis + Football)

**Enriquecimiento estructural nuevo (iter 12):**
- 5 programas con turnos discretos capturados (LD19)
- 2 programas con sobreprecio por variante en cursos_especialistas (LD18)
- 1 programa con 10 turnos anuales (Berlitz 50+ Programme)

## Subsistemas — estado

| Subsistema | Estado | Ficheros |
|---|---|---|
| Extracción | Consolidado sobre 5 PDFs | `src/extraction/` |
| Curación (5 pasadas + fusión) | Funcional | `src/curation/` |
| Recomendación (filtros + MCDM) | Funcional | `src/recommendation/` |
| Explicación trazable | Funcional | `src/explanation/` |
| Evaluación H1 | Funcional con GT mínimo | `src/evaluation/` |
| Evaluación H2 | No iniciado | — |
| Plataforma web | No iniciado | — |
| Validación H3 (Likert) | No iniciado | — |

## Lecciones de diseño — cobertura

### Implementadas en el sistema (19)

LD1 multi-programa · LD3 alojamiento como lista · LD4 all ages 0-99 ·
LD5 fechas recurrentes · LD6 tipo de documento (folleto/tarifa_b2b/etc) ·
LD10 vigencia vs fechas programa · LD11 origen documento · LD12
partners · LD13 fidelidad de evidencias (literal/derivado/inferido) ·
LD14 costes adicionales · LD16 fusión cross-doc · LD17 moneda original
preservada · LD18 variantes con precio adicional · LD19 múltiples
turnos · LD20 specialist courses como modificadores · LD21
partnerships · LD22 costes complementarios · RF6 obsolescencia ·
LD8 parcial (normalización a €/semana, sin desglose completo)

### Pendientes (4)

LD2 parcial (precios distribuidos siguen residuos en Berlitz) · LD7
multi-campaña · LD8 desglose completo por componentes · LD15 múltiples
sedes · LD23 F1 desglosado por tipo de documento

## Bugs conocidos y limitaciones

- ~~**NSX Woodbridge `precio_semanal_max_eur`**~~: RESUELTO en iter 12
  con LD18 (`precio_adicional_semanal_eur` en CursoEspecialista +
  regla del prompt para reflejar el max efectivo).
- **Berlitz General English nombre**: el matcher del GT elige
  "General Intensive English 30" con similitud muy cercana a la de
  "General English". Caso de borde del matcher, resoluble ajustando
  `match_nombre` en el GT.
- **Berlitz tipo_alojamiento**: extractor devuelve `[familia, residencia]`
  donde GT dice `[familia, otro]` por interpretación distinta de
  "apartamento". Discrepancia semántica del GT.
- **Berlitz precios min/max**: aunque la PRICE LIST se lee entera tras
  el fix de truncamiento, el extractor sigue capturando precios de
  otros cursos del catálogo. Requiere prompt más específico para
  correlacionar programa con su fila de la lista de precios.
- **Berlitz NET Prices `duracion_max_dias=7`**: el LLM sigue poniendo
  máximo 7 cuando el documento no lo especifica (curso modular).
  Regla del prompt aparentemente insuficiente.

## Tests

- 26 tests unitarios en `tests/`
- Cobertura: modelos, obsolescencia, tipo_documento, comparadores,
  métricas de extracción
- Todos pasan en verde tras la iteración 10

## Ficheros clave del proyecto

- `src/models.py`: esquema Pydantic Programa + PerfilCliente + Recomendacion
- `src/pipeline.py`: orquestador end-to-end
- `src/extraction/llm_extractor.py`: prompt + tool schema + llamada API
- `src/curation/merge.py`: fusión cross-doc
- `src/evaluation/run_h1.py`: CLI de evaluación
- `data/eval/ground_truth.json`: GT versionado (iter03_minima_semanal)
- `data/eval/resultados/`: histórico de F1 por iteración
- `data/processed/programas.json`: catálogo actual persistido
- `data/raw/`: 5 PDFs del corpus mínimo
- `notas/iteraciones.md`: log detallado de qué se hizo en cada iteración
- `notas/decisiones_diseno.md`: catálogo de LDs identificadas

## Plan de trabajo — 4 semanas para cierre práctico

Ver conversación de sesión para detalle completo. Resumen:

- **Semana 1**: cierre H1 (foco 2 hecho el lunes; martes LD5+LD20;
  miércoles LD18+LD19; jueves ampliar GT a 17; viernes iteración final)
- **Semana 2**: cierre H2 (GT ranking con I-KIDS, métrica P@5 + nDCG@10
  + Wilcoxon)
- **Semana 3**: plataforma web mínima (dashboard consulta, Streamlit o
  FastAPI)
- **Semana 4**: sesión H3 con I-KIDS, cuestionario Likert, análisis,
  buffer, cierre

Dependencias externas críticas: coordinación con I-KIDS para GT de H2
y sesión de H3. Pedir cuanto antes.
