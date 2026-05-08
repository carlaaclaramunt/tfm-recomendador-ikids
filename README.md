# TFM — Recomendador de programas de inmersión lingüística para I-KIDS

Trabajo de Fin de Máster (MEI, FIB-UPC). Sistema que recomienda programas
de inmersión lingüística a partir de la documentación heterogénea aportada
por las empresas asociadas a I-KIDS.

El sistema combina tres pilares técnicos:

1. **Extracción de información** sobre PDF e imagen mediante LLM + OCR.
2. **Recomendación multi-criterio** con preferencias incompletas
   (recomendador basado en conocimiento + MCDM en cascada).
3. **Explicabilidad** basada en trazabilidad sistemática.

## Estructura del repositorio

```
tfm-recomendador-ikids/
├── src/
│   ├── models.py              # Esquemas Pydantic (Programa, PerfilCliente)
│   ├── extraction/            # Extracción de información sobre documentos
│   ├── recommendation/        # Filtros + MCDM
│   ├── explanation/           # Generación de explicaciones trazables
│   └── pipeline.py            # Orquestador end-to-end
├── notebooks/                 # Exploración del corpus
├── data/
│   ├── raw/                   # PDFs originales (no versionados)
│   └── processed/             # JSONs extraídos (no versionados)
└── tests/
```

## Puesta en marcha

### 1. Crear el entorno

```bash
python -m venv .venv
source .venv/bin/activate     # macOS/Linux
# .venv\Scripts\activate      # Windows
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env y rellenar ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Instalar Tesseract (para OCR)

- **macOS**: `brew install tesseract tesseract-lang`
- **Ubuntu/Debian**: `sudo apt install tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng`
- **Windows**: descargar el instalador desde
  https://github.com/UB-Mannheim/tesseract/wiki

### 4. Colocar PDFs de prueba

Copiar 5-10 PDFs representativos del corpus de I-KIDS a `data/raw/`.

### 5. Ejecutar el pipeline

```bash
python -m src.pipeline
```

## Notas de desarrollo

- El LLM usado en la primera iteración es Claude (API de Anthropic) por
  velocidad de prototipado. La migración a Llama 3.1 8B local está prevista
  para la fase de validación.
- Los documentos en `data/` no se versionan (ver `.gitignore`).
- Las claves de API nunca se comprometen al repositorio.
