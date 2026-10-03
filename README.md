
# TFM — Recomendador de programas de inmersión lingüística para I-KIDS

Trabajo de Fin de Máster (MEI, FIB-UPC) de Carla Claramunt Guix.

Sistema de apoyo a la decisión que ayuda al equipo asesor de I-KIDS a recomendar programas de inmersión lingüística a sus clientes a partir de la documentación comercial heterogénea aportada por los veintiséis proveedores asociados.

**Despliegue público (sin instalación):** [https://tfm-ikids-recomendador.streamlit.app](https://tfm-ikids-recomendador.streamlit.app)

El sistema se articula en torno a cuatro componentes técnicos:

1. **Extracción estructurada** sobre PDFs e imágenes mediante LLM con validación en dos fases (`tool use` + Pydantic).
2. **Recomendación multi-criterio** con preferencias incompletas, combinando filtros duros basados en conocimiento del dominio con un núcleo MCDM de suma ponderada y seis criterios (precio, duración, ubicación, alojamiento, edad, afinidad temática).
3. **Trazabilidad verificable**: cada dato numérico extraído se anota con una cita literal del documento fuente, clasificable automáticamente en cuatro niveles de fidelidad.
4. **Dashboard Streamlit** para el asesor: formulario de perfil del cliente, top-k de recomendaciones con descomposición MCDM, explicación en lenguaje natural y gestión documental (exclusiones en vivo).

El protocolo de evaluación se articula en torno a tres hipótesis con contrastes estadísticos independientes (F1 macro para extracción, Wilcoxon sobre nDCG@10 y Precision@5 para ranking, escala Likert para explicación).

## Estructura del repositorio

```
tfm-recomendador-ikids/
├── src/
│   ├── models.py              # Esquemas Pydantic (Programa, PerfilCliente, …)
│   ├── extraction/            # Lectura de documentos + extractor LLM
│   │   ├── document_reader.py # Router por extensión (PDF / imagen)
│   │   ├── pdf_reader.py      # pdfplumber + OCR fallback
│   │   ├── image_reader.py    # OCR directo sobre imagen
│   │   └── llm_extractor.py   # Claude Sonnet 4.5 + tool use + Pydantic
│   ├── curation/              # Obsolescencia, origen, partnerships, evidencias
│   ├── recommendation/        # Filtros duros + MCDM
│   ├── explanation/           # Generación de explicaciones trazables
│   ├── evaluation/            # Métricas, baselines, run H1/H2
│   ├── application/           # Casos de uso (construir_catalogo, recomendar)
│   └── webapp/                # Dashboard Streamlit
│       └── assets/            # Logo y recursos estáticos
├── prompts/
│   └── extraccion_v3.md       # System prompt versionado del extractor
├── config/
│   └── reglas_partnerships.yaml
├── notas/
│   └── decisiones_diseno.md   # Catálogo de lecciones de diseño LD1-LD23
├── data/
│   ├── raw/                   # Documentos originales por proveedor (vía Git LFS)
│   ├── processed/
│   │   └── programas.json     # Catálogo persistido (versionado)
│   ├── eval/                  # Ground truth y resultados de evaluación
│   └── exclusions.json        # Exclusiones documentales del asesor
└── tests/                     # 166 tests unitarios (pytest)
```

## Despliegue público

La aplicación está desplegada en Streamlit Community Cloud y accesible sin instalación local en:

**https://tfm-ikids-recomendador.streamlit.app**

El despliegue se actualiza automáticamente con cada `push` a la rama `main` del repositorio. En el entorno desplegado:

- El catálogo se lee desde `data/processed/programas.json` (ya construido).
- Los documentos originales (PDFs e imágenes de `data/raw/`) se sirven mediante Git LFS, lo que permite consultar y previsualizar cada documento fuente desde la pestaña **Documentos**.
- Las exclusiones documentales guardadas por el asesor en el deploy son por sesión (no se persisten entre reinicios de la app, por diseño de Streamlit Cloud).

La re-extracción con LLM y la gestión persistente del corpus requieren la instalación local descrita a continuación.

## Puesta en marcha (local)

### 1. Clonar el repositorio con Git LFS

El corpus original de documentos se versiona con Git LFS. Hace falta instalarlo antes del clon para que los PDFs e imágenes se descarguen correctamente:

```bash
# Instalar git-lfs si no lo tienes
brew install git-lfs                      # macOS
# sudo apt install git-lfs                # Ubuntu/Debian
# https://git-lfs.com/                    # Windows

git lfs install
git clone https://github.com/carlaaclaramunt/tfm-recomendador-ikids.git
cd tfm-recomendador-ikids
```

### 2. Crear el entorno

```bash
python -m venv .venv
source .venv/bin/activate     # macOS/Linux
# .venv\Scripts\activate      # Windows
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env y rellenar ANTHROPIC_API_KEY=sk-ant-...
```

Solo necesario si se van a lanzar re-extracciones con el LLM. Para usar únicamente el dashboard sobre el catálogo ya construido no hace falta API key.

### 4. Instalar Tesseract (OCR)

- **macOS**: `brew install tesseract tesseract-lang`
- **Ubuntu/Debian**: `sudo apt install tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng`
- **Windows**: instalador en https://github.com/UB-Mannheim/tesseract/wiki

### 5. Lanzar el dashboard

```bash
streamlit run src/webapp/app.py
```

Accesible en `http://localhost:8501`. Tres pestañas:

- **Recomendar**: formulario de perfil del cliente → top-k de recomendaciones con explicación.
- **Catálogo**: tabla filtrable del catálogo completo.
- **Documentos**: gestión documental (exclusiones aplicadas en vivo, preview de PDFs).

### 6. (Opcional) Reconstruir el catálogo desde cero

Requiere `ANTHROPIC_API_KEY` configurada en `.env`:

```bash
python -m src.application.construir_catalogo --reextraer
```

El resultado se persiste en `data/processed/programas.json`.

### 7. Ejecutar los tests

```bash
pytest -q
```

### 8. Reproducir las evaluaciones

```bash
python -m src.evaluation.run_h1    # Métricas de extracción (F1 macro)
python -m src.evaluation.run_h2    # Métricas de ranking + Wilcoxon
```

## Reproducibilidad

- El prompt del extractor está versionado en `prompts/extraccion_v3.md`. La variable de entorno `IKIDS_PROMPT_VERSION` permite alternar entre versiones sin modificar el código.
- `temperature=0` fija el comportamiento del LLM, de modo que la métrica reportada (F1 macro = 0,875 sobre veintiuna entradas de ground truth con prompt v3 y modelo claude-sonnet-4-5) es reproducible a partir del código y de los artefactos versionados.
- Las decisiones de diseño iterativas quedan registradas en `notas/decisiones_diseno.md` como lecciones LD1-LD23.

## Flujo de desarrollo asistido

Este proyecto se ha desarrollado con asistencia parcial de modelos de lenguaje (Claude Opus 4.7, Anthropic) en calidad de *pair programmer* bajo supervisión directa de la autora. El rol del asistente ha consistido en:

- Proponer implementaciones de componentes concretos a partir de decisiones arquitectónicas tomadas por la autora.
- Redactar primeras versiones de tests unitarios que la autora revisaba y adaptaba al contexto.
- Facilitar la navegación de dependencias de la base de código.

Las decisiones de diseño, el modelo de datos, la arquitectura hexagonal ligera, el protocolo de evaluación por hipótesis, la selección de métricas y las lecciones de diseño LD1-LD23 son autoría de Carla Claramunt. Cada *commit* fusionado a `main` ha sido revisado y aprobado antes de su integración. Los commits conservan la etiqueta `Co-Authored-By` como registro transparente del flujo de trabajo.

Esta práctica es coherente con las recomendaciones de FIB-UPC sobre uso de herramientas de IA en TFMs.

## Autoría

**Carla Claramunt Guix** — Facultad de Informática de Barcelona (FIB), Universidad Politécnica de Cataluña (UPC). Dirigido por Fernando Barrabés Naval.

Curso 2025/2026.