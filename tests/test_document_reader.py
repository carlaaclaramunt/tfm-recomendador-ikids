"""Tests del enrutador de lectura por formato.

Verifica que `read_document_text` despacha correctamente a los lectores
registrados y rechaza con un error claro los formatos no soportados.
También cubre el adaptador de imágenes de forma aislada mediante una
imagen sintética generada con PIL — así el test no depende de que haya
un fichero real en el corpus.
"""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from src.extraction.document_reader import (
    FormatoNoSoportadoError,
    read_document_text,
)
from src.extraction.image_reader import EXTENSIONES_IMAGEN, read_image_text


# ---------------------------------------------------------------------------
# Fábrica de imágenes sintéticas con texto reconocible por Tesseract
# ---------------------------------------------------------------------------


def _crear_imagen_con_texto(path: Path, texto: str) -> None:
    """Genera una imagen de 400x100 con el texto dado, en blanco y negro
    y a tamaño suficiente para que Tesseract lo reconozca con fiabilidad."""
    imagen = Image.new("RGB", (400, 100), color="white")
    dibujo = ImageDraw.Draw(imagen)
    # Fuente del sistema por defecto: no garantiza una grande, pero
    # tesseract reconoce esto en casi cualquier plataforma.
    try:
        fuente = ImageFont.truetype("DejaVuSans.ttf", 32)
    except OSError:
        fuente = ImageFont.load_default()
    dibujo.text((20, 30), texto, fill="black", font=fuente)
    imagen.save(path)


# ---------------------------------------------------------------------------
# Dispatcher: enrutado por extensión
# ---------------------------------------------------------------------------


def test_dispatcher_rechaza_formato_no_soportado(tmp_path):
    fichero = tmp_path / "folleto.docx"
    fichero.write_bytes(b"PK\x03\x04")  # DOCX es un ZIP, pero no está soportado
    with pytest.raises(FormatoNoSoportadoError) as exc:
        read_document_text(fichero)
    assert ".docx" in str(exc.value)


def test_dispatcher_acepta_todas_las_extensiones_de_imagen_registradas():
    """Documenta las extensiones de imagen que el router reconoce.
    Si alguien añade/quita una, este test fuerza a actualizar la memoria."""
    assert EXTENSIONES_IMAGEN == {
        ".png",
        ".jpg",
        ".jpeg",
        ".tiff",
        ".tif",
        ".bmp",
    }


# ---------------------------------------------------------------------------
# Adaptador de imágenes
# ---------------------------------------------------------------------------


def test_read_image_text_devuelve_texto_de_imagen_png(tmp_path):
    path = tmp_path / "folleto.png"
    _crear_imagen_con_texto(path, "SUMMER 2026")
    texto = read_image_text(path, idioma_ocr="eng")
    # Tesseract puede no reconocer todo con fuente default; aceptamos
    # cualquier reconocimiento parcial siempre que incluya "2026" o
    # "SUMMER" (el elemento más distintivo para la métrica OCR).
    assert "2026" in texto or "SUMMER" in texto.upper()


def test_read_image_text_falla_si_el_fichero_no_existe(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_image_text(tmp_path / "no_existe.png")


def test_read_image_text_normaliza_png_con_canal_alpha(tmp_path):
    """Un PNG con alpha (modo RGBA) no debe romper Tesseract."""
    path = tmp_path / "con_alpha.png"
    imagen = Image.new("RGBA", (200, 60), color=(255, 255, 255, 255))
    dibujo = ImageDraw.Draw(imagen)
    try:
        fuente = ImageFont.truetype("DejaVuSans.ttf", 24)
    except OSError:
        fuente = ImageFont.load_default()
    dibujo.text((10, 15), "HELLO", fill=(0, 0, 0, 255), font=fuente)
    imagen.save(path)

    # No debería lanzar excepción
    texto = read_image_text(path, idioma_ocr="eng")
    assert isinstance(texto, str)


# ---------------------------------------------------------------------------
# Integración router → adaptador imagen
# ---------------------------------------------------------------------------


def test_dispatcher_delega_a_image_reader_para_png(tmp_path):
    """El router debe producir el mismo texto que `read_image_text`
    directamente, para los formatos de imagen."""
    path = tmp_path / "folleto.png"
    _crear_imagen_con_texto(path, "LONDON 2026")

    desde_router = read_document_text(path, idioma_ocr="eng")
    desde_lector = read_image_text(path, idioma_ocr="eng")

    assert desde_router == desde_lector
