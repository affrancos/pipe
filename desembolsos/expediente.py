"""Procesa el expediente de un caso: OCR, clasificación, extracción, validación y reportes."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from . import ocr
from .clasificador import clasificar
from .extractores import extraer_campos
from .validador import DatosCaso, Documento, completar_datos_caso, estado_resultado, validar

log = logging.getLogger(__name__)


def carpeta_caso(config: dict, caso: str) -> Path:
    return Path(config["rutas"]["casos"]) / str(caso)


def leer_documento(ruta: Path, config: dict, dir_textos: Path, hoy: date | None = None) -> Documento:
    cfg_ocr = config.get("ocr", {})
    resultado = ocr.extraer_texto(
        ruta, cfg_ocr.get("idioma", "spa"), cfg_ocr.get("dpi", 300), cfg_ocr.get("min_caracteres_pagina", 40)
    )
    # El texto se guarda para auditoría y para afinar las reglas con casos reales.
    dir_textos.mkdir(parents=True, exist_ok=True)
    (dir_textos / f"{ruta.name}.txt").write_text(resultado.texto, encoding="utf-8")
    tipo, puntaje = clasificar(resultado.texto, ruta.name)
    campos = extraer_campos(tipo, resultado.texto, hoy)
    log.info("%s -> %s (puntaje %s, OCR en %s/%s págs.)", ruta.name, tipo, puntaje,
             resultado.paginas_ocr, resultado.paginas)
    return Documento(ruta.name, tipo, puntaje, resultado.uso_ocr, campos)


def procesar_caso(datos: DatosCaso, config: dict, hoy: date | None = None) -> dict:
    ocr.configurar_tesseract(config.get("ocr", {}).get("tesseract_cmd"))
    base = carpeta_caso(config, datos.caso)
    dir_docs = base / "documentos"
    archivos = sorted(p for p in dir_docs.glob("*") if p.is_file()) if dir_docs.exists() else []
    if not archivos:
        raise FileNotFoundError(f"No hay documentos en {dir_docs}")

    documentos = []
    for archivo in archivos:
        try:
            documentos.append(leer_documento(archivo, config, base / "textos", hoy))
        except Exception as e:  # un archivo dañado no debe detener el caso completo
            log.error("No se pudo leer %s: %s", archivo.name, e)
            documentos.append(Documento(archivo.name, "desconocido", 0, False, {"error": str(e)}))

    datos = completar_datos_caso(datos, documentos)
    hallazgos = validar(datos, documentos, config, hoy)
    resultado = {
        "caso": datos.caso,
        "fecha_proceso": datetime.now().isoformat(timespec="seconds"),
        "estado": estado_resultado(hallazgos),
        "datos_caso": datos.to_dict(),
        "documentos": [asdict(d) for d in documentos],
        "hallazgos": [asdict(x) for x in hallazgos],
        "ruta_expediente": str(base),
    }
    (base / "resultado.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return resultado


def cargar_resultado(config: dict, caso: str) -> dict:
    ruta = carpeta_caso(config, caso) / "resultado.json"
    if not ruta.exists():
        raise FileNotFoundError(f"El caso {caso} no ha sido procesado ({ruta} no existe)")
    return json.loads(ruta.read_text(encoding="utf-8"))
