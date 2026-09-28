"""Recoge de la carpeta de Descargas los documentos que el auxiliar bajó de Bizagi."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

TEMPORALES = {".crdownload", ".part", ".tmp", ".download"}


def archivos_recientes(carpeta: Path, extensiones: list[str], ventana_minutos: int) -> list[Path]:
    limite = time.time() - ventana_minutos * 60
    extensiones = {e.lower() for e in extensiones}
    return sorted(
        (p for p in Path(carpeta).iterdir()
         if p.is_file() and p.suffix.lower() in extensiones and p.stat().st_mtime >= limite),
        key=lambda p: p.stat().st_mtime,
    )


def descargas_en_curso(carpeta: Path) -> list[Path]:
    return [p for p in Path(carpeta).iterdir() if p.suffix.lower() in TEMPORALES]


def _destino_libre(destino: Path) -> Path:
    if not destino.exists():
        return destino
    n = 1
    while (candidato := destino.with_name(f"{destino.stem}_{n}{destino.suffix}")).exists():
        n += 1
    return candidato


def mover_a_expediente(archivos: list[Path], carpeta_documentos: Path, copiar: bool = False) -> list[Path]:
    carpeta_documentos.mkdir(parents=True, exist_ok=True)
    movidos = []
    for archivo in archivos:
        destino = _destino_libre(carpeta_documentos / archivo.name)
        (shutil.copy2 if copiar else shutil.move)(str(archivo), str(destino))
        movidos.append(destino)
    return movidos
