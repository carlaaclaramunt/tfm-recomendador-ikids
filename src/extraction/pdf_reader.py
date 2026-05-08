"""Lectura de PDFs.

Estrategia en dos pasos:

1. Intentar extraer texto nativo con pdfplumber.
2. Si el texto extraído es muy corto (señal de PDF escaneado),
   caer en OCR con pytesseract sobre las imágenes de cada página.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pytesseract
from pdf2image import convert_from_path

# Umbral mínimo de caracteres para considerar que el PDF tiene texto nativo.
# Por debajo de este valor se asume que es un escaneado y se aplica OCR.
UMBRAL_TEXTO_NATIVO = 200


def read_pdf_text(pdf_path: Path | str, idioma_ocr: str = "spa+eng") -> str:
    """Lee un PDF y devuelve su contenido textual.

    Args:
        pdf_path: Ruta al fichero PDF.
        idioma_ocr: Idiomas para Tesseract si hace falta OCR.
                    Formato: "spa", "eng", "spa+eng", etc.

    Returns:
        El texto extraído del PDF como una única cadena.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"No se encuentra el PDF: {pdf_path}")

    texto_nativo = _extract_native_text(pdf_path)

    if len(texto_nativo.strip()) >= UMBRAL_TEXTO_NATIVO:
        return texto_nativo

    # PDF probablemente escaneado: aplicar OCR
    return _extract_ocr_text(pdf_path, idioma_ocr=idioma_ocr)


def _extract_native_text(pdf_path: Path) -> str:
    """Extrae texto nativo de un PDF con pdfplumber."""
    paginas: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pagina in pdf.pages:
            contenido = pagina.extract_text() or ""
            paginas.append(contenido)
    return "\n\n".join(paginas)


def _extract_ocr_text(pdf_path: Path, idioma_ocr: str) -> str:
    """Aplica OCR a las imágenes de cada página."""
    imagenes = convert_from_path(str(pdf_path), dpi=300)
    paginas: list[str] = []
    for imagen in imagenes:
        texto = pytesseract.image_to_string(imagen, lang=idioma_ocr)
        paginas.append(texto)
    return "\n\n".join(paginas)