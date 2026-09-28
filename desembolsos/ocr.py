"""Extracción de texto de PDF (digitales o escaneados) e imágenes.

- PDF con capa de texto: se lee directamente con PyMuPDF (rápido y exacto).
- PDF escaneado / página sin texto: se renderiza la página y se le aplica OCR con Tesseract.
- Imágenes (JPG, PNG, TIFF...): OCR con Tesseract, probando otras orientaciones si sale ilegible.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image, ImageOps, ImageSequence

log = logging.getLogger(__name__)

EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


@dataclass
class TextoDocumento:
    texto: str
    paginas: int
    paginas_ocr: int

    @property
    def uso_ocr(self) -> bool:
        return self.paginas_ocr > 0


def configurar_tesseract(tesseract_cmd: str | None) -> None:
    if tesseract_cmd and Path(tesseract_cmd).exists():
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def _preparar_imagen(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    img = ImageOps.grayscale(img)
    # Fotos de celular pequeñas: ampliar mejora mucho el OCR.
    if img.width < 1500:
        factor = 1500 / img.width
        img = img.resize((int(img.width * factor), int(img.height * factor)), Image.LANCZOS)
    return ImageOps.autocontrast(img)


def _puntaje_texto(texto: str) -> int:
    """Cantidad de palabras 'reales' (3+ letras con vocal): mide qué tan legible salió el OCR."""
    palabras = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", texto)
    return sum(1 for p in palabras if re.search(r"[AEIOUaeiouÁÉÍÓÚáéíóú]", p))


def ocr_imagen(img: Image.Image, idioma: str = "spa") -> str:
    img = _preparar_imagen(img)
    texto = pytesseract.image_to_string(img, lang=idioma, config="--psm 3")
    if _puntaje_texto(texto) >= 15:
        return texto
    # Poco texto legible: puede ser una foto o escaneo girado. Se prueban las otras
    # orientaciones y se conserva la que produzca más palabras.
    mejor, mejor_puntaje = texto, _puntaje_texto(texto)
    for angulo in (90, 180, 270):
        candidato = pytesseract.image_to_string(img.rotate(angulo, expand=True), lang=idioma, config="--psm 3")
        if (puntaje := _puntaje_texto(candidato)) > mejor_puntaje:
            mejor, mejor_puntaje = candidato, puntaje
    return mejor


def _texto_pdf(ruta: Path, idioma: str, dpi: int, min_caracteres: int) -> TextoDocumento:
    partes, paginas_ocr = [], 0
    with pymupdf.open(ruta) as doc:
        for pagina in doc:
            texto = pagina.get_text()
            if len(re.sub(r"\s", "", texto)) < min_caracteres:
                pix = pagina.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                texto = ocr_imagen(img, idioma)
                paginas_ocr += 1
            partes.append(texto)
        return TextoDocumento("\n".join(partes), len(doc), paginas_ocr)


def _texto_imagen(ruta: Path, idioma: str) -> TextoDocumento:
    partes = []
    with Image.open(ruta) as img:
        for cuadro in ImageSequence.Iterator(img):  # TIFF multipágina
            partes.append(ocr_imagen(cuadro.convert("RGB"), idioma))
    return TextoDocumento("\n".join(partes), len(partes), len(partes))


def extraer_texto(ruta: Path, idioma: str = "spa", dpi: int = 300, min_caracteres: int = 40) -> TextoDocumento:
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext == ".pdf":
        return _texto_pdf(ruta, idioma, dpi, min_caracteres)
    if ext in EXT_IMAGEN:
        return _texto_imagen(ruta, idioma)
    raise ValueError(f"Formato no soportado: {ruta.name}")
