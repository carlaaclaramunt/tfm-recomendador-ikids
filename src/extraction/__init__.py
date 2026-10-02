"""Subsistema de extracción de información sobre documentos."""

from src.extraction.document_reader import read_document_text
from src.extraction.image_reader import read_image_text
from src.extraction.llm_extractor import extract_programs
from src.extraction.pdf_reader import read_pdf_text

__all__ = [
    "extract_programs",
    "read_document_text",
    "read_image_text",
    "read_pdf_text",
]
