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