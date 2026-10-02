"""Enrutador de lectura por tipo de documento.

Despacha a `pdf_reader.read_pdf_text` o a `image_reader.read_image_text`
según la extensión del fichero. El resto del pipeline de extracción
(prompt, tool use, validación Pydantic) permanece inalterado: cambia
solo el adaptador de entrada.

Formatos soportados actualmente: PDF e imágenes
(.png, .jpg, .jpeg, .tiff, .tif, .bmp). Para añadir un nuevo formato
basta con escribir un adaptador que devuelva texto plano y registrarlo
en el despachador de este módulo.
"""

from __future__ import annotations

from pathlib import Path

from src.extraction.image_reader import EXTENSIONES_IMAGEN, read_image_text
from src.extraction.pdf_reader import read_pdf_text


class FormatoNoSoportadoError(ValueError):
    """La extensión del fichero no corresponde a ningún lector registrado."""


def read_document_text(document_path: Path | str, idioma_ocr: str = "spa+eng") -> str:
    """Lee un documento y devuelve su contenido textual.

    Args:
        document_path: Ruta al fichero (PDF o imagen).
        idioma_ocr: Idiomas para Tesseract cuando se requiera OCR.

    Returns:
        El texto extraído como una única cadena.

    Raises:
        FormatoNoSoportadoError: Si la extensión no corresponde a un
            lector registrado.
    """
    document_path = Path(document_path)
    extension = document_path.suffix.lower()

    if extension == ".pdf":
        return read_pdf_text(document_path, idioma_ocr=idioma_ocr)
    if extension in EXTENSIONES_IMAGEN:
        return read_image_text(document_path, idioma_ocr=idioma_ocr)

    raise FormatoNoSoportadoError(
        f"Extensión '{extension}' no soportada. "
        f"Formatos actuales: .pdf, {', '.join(sorted(EXTENSIONES_IMAGEN))}."
    )
