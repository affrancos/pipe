"""Carga de config/config.yaml y config/convenios.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
DIR_CONFIG = RAIZ_PROYECTO / "config"


def _ruta(valor: str | None) -> Path | None:
    if not valor:
        return None
    ruta = Path(valor).expanduser()
    return ruta if ruta.is_absolute() else (RAIZ_PROYECTO / ruta).resolve()


def cargar_config(dir_config: Path | None = None) -> dict:
    dir_config = Path(dir_config) if dir_config else DIR_CONFIG
    with open(dir_config / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    with open(dir_config / "convenios.yaml", encoding="utf-8") as f:
        config["convenios"] = yaml.safe_load(f).get("convenios", [])

    rutas = config.setdefault("rutas", {})
    for clave in ("descargas", "casos", "control_excel"):
        rutas[clave] = _ruta(rutas.get(clave))
    pa = config.setdefault("power_automate", {})
    pa["carpeta_solicitudes"] = _ruta(pa.get("carpeta_solicitudes"))
    return config
