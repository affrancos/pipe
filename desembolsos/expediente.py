"""Procesa el expediente de un caso: OCR, clasificación, extracción, validación y reportes."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from . import ocr
from .clasificador import clasificar
from .extractores import extraer_campos
from .texto import parse_monto, parse_numero, solo_digitos
from .validador import DatosCaso, Documento, completar_datos_caso, estado_resultado, validar

log = logging.getLogger(__name__)


# Archivos que deja Power Automate Desktop en la carpeta del caso.
ARCHIVO_DATOS = "caso.json"  # datos del caso leídos del portal de Bizagi
MARCA_LISTO = "LISTO.txt"  # se crea al terminar la descarga: indica que el caso se puede procesar
MARCA_ERROR = "ERROR_PROCESO.txt"


def nombre_carpeta(caso: str) -> str:
    """Nombre de carpeta válido en Windows para el número o nombre del caso."""
    return re.sub(r'[<>:"/\\|?*]', "_", str(caso)).strip(" .")


def carpeta_caso(config: dict, caso: str) -> Path:
    return Path(config["rutas"]["casos"]) / nombre_carpeta(caso)


def datos_desde_dict(caso: str, valores: dict) -> DatosCaso:
    """Crea DatosCaso a partir de textos tal como vienen de Bizagi ('$ 15.000.000', '1,45 %')."""
    def texto(clave):
        valor = valores.get(clave)
        return str(valor).strip() if valor not in (None, "") else None

    monto, tasa, plazo, cedula = texto("monto"), texto("tasa"), texto("plazo_meses"), texto("cedula")
    tipo_tasa = texto("tipo_tasa")
    producto = texto("producto")
    return DatosCaso(
        caso=str(caso),
        producto=producto.lower().replace(" ", "_") if producto else None,
        convenio=texto("convenio"),
        cedula=solo_digitos(cedula) if cedula else None,
        nombre=texto("nombre"),
        monto=parse_monto(monto) if monto else None,
        tasa=parse_numero(tasa.replace("%", "")) if tasa else None,
        tipo_tasa=("EA" if tipo_tasa.upper().lstrip().startswith("E") else "MV") if tipo_tasa else None,
        plazo_meses=int(solo_digitos(plazo)) if plazo and solo_digitos(plazo) else None,
    )


def leer_datos_caso(config: dict, caso: str) -> dict:
    """Contenido de caso.json si Power Automate Desktop lo dejó; si no, un diccionario vacío."""
    ruta = carpeta_caso(config, caso) / ARCHIVO_DATOS
    if not ruta.exists():
        return {}
    # utf-8-sig: PAD puede escribir el archivo con BOM.
    return json.loads(ruta.read_text(encoding="utf-8-sig"))


def casos_pendientes(config: dict) -> list[str]:
    """Carpetas con LISTO.txt que no se han procesado desde que se marcaron como listas."""
    raiz = Path(config["rutas"]["casos"])
    if not raiz.exists():
        return []
    pendientes = []
    for carpeta in sorted(p for p in raiz.iterdir() if p.is_dir()):
        marca = carpeta / MARCA_LISTO
        if not marca.exists():
            continue
        salidas = [carpeta / "resultado.json", carpeta / MARCA_ERROR]
        if not any(s.exists() and s.stat().st_mtime >= marca.stat().st_mtime for s in salidas):
            pendientes.append(carpeta.name)
    return pendientes


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
