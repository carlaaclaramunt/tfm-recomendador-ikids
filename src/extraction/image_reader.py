"""Lectura de imágenes mediante OCR.

Complementa a `pdf_reader` para cubrir el 26 % del corpus de I-KIDS que
los proveedores entregan como fichero de imagen (PNG, JPG, JPEG, TIFF,
BMP) en lugar de PDF —típicamente folletos escaneados o infografías
comerciales exportadas directamente desde una herramienta de diseño—.

La salida es texto plano y encaja sin cambios con el resto del pipeline
de extracción: el `llm_extractor` recibe el texto y produce la lista de
`Programa` de la misma forma que para un PDF.
"""

from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image

EXTENSIONES_IMAGEN = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


def read_image_text(image_path: Path | str, idioma_ocr: str = "spa+eng") -> str:
    """Lee una imagen y devuelve su contenido textual vía OCR.

    Args:
        image_path: Ruta al fichero de imagen.
        idioma_ocr: Idiomas para Tesseract.
                    Formato: "spa", "eng", "spa+eng", etc.

    Returns:
        El texto extraído de la imagen como una única cadena.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"No se encuentra la imagen: {image_path}")

    with Image.open(image_path) as imagen:
        # Convertir a RGB evita que modos como RGBA (PNG con alpha) o P
        # (paleta indexada) fallen en Tesseract.
        if imagen.mode not in ("L", "RGB"):
            imagen = imagen.convert("RGB")
        return pytesseract.image_to_string(imagen, lang=idioma_ocr)
