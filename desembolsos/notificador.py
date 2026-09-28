"""Envía el caso validado a Power Automate para la aprobación del gestor (Teams + Outlook)."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

import requests

from .texto import pesos


def enmascarar(cedula: str | None) -> str | None:
    """En Teams y Outlook solo se muestran los últimos 4 dígitos de la cédula."""
    if not cedula:
        return None
    return "*" * max(len(cedula) - 4, 0) + cedula[-4:]


def _resumen_markdown(resultado: dict) -> str:
    d = resultado["datos_caso"]
    monto = f"{pesos(d['monto'])}" if d.get("monto") is not None else "—"
    tasa = f"{d['tasa']}% {d.get('tipo_tasa') or ''}" if d.get("tasa") is not None else "—"
    lineas = [
        f"**Caso Bizagi:** {resultado['caso']}",
        f"**Producto:** {d.get('producto') or '—'} | **Convenio:** {d.get('convenio') or '—'}",
        f"**Cliente:** {d.get('nombre') or '—'} (C.C. {enmascarar(d.get('cedula')) or '—'})",
        f"**Monto:** {monto} | **Tasa:** {tasa} | **Plazo:** {d.get('plazo_meses') or '—'} meses",
        f"**Validación automática:** {resultado['estado']}",
    ]
    pendientes = [h for h in resultado["hallazgos"] if h["nivel"] != "OK"]
    if pendientes:
        lineas.append("")
        lineas.append("**Observaciones:**")
        lineas += [f"- [{h['nivel']}] {h['regla']}: {h['detalle']}" for h in pendientes]
    return "\n".join(lineas)


def construir_solicitud(resultado: dict, observaciones: str = "", config: dict | None = None) -> dict:
    d = resultado["datos_caso"]
    pa = (config or {}).get("power_automate", {})
    return {
        "caso": str(resultado["caso"]),
        "producto": d.get("producto"),
        "convenio": d.get("convenio"),
        "cliente": d.get("nombre"),
        "cedula_enmascarada": enmascarar(d.get("cedula")),
        "monto": d.get("monto"),
        "tasa": d.get("tasa"),
        "tipo_tasa": d.get("tipo_tasa"),
        "plazo_meses": d.get("plazo_meses"),
        "estado_validacion": resultado["estado"],
        "errores": [f"{h['regla']}: {h['detalle']}" for h in resultado["hallazgos"] if h["nivel"] == "ERROR"],
        "alertas": [f"{h['regla']}: {h['detalle']}" for h in resultado["hallazgos"] if h["nivel"] == "ALERTA"],
        "resumen_markdown": _resumen_markdown(resultado),
        "observaciones_auxiliar": observaciones,
        "enviado_por": getpass.getuser(),
        "correo_gestor": pa.get("correo_gestor"),
        "correo_auxiliar": pa.get("correo_auxiliar"),
        "ruta_expediente": resultado.get("ruta_expediente"),
    }


def enviar(solicitud: dict, config: dict) -> str:
    """Envía por HTTP al flujo o deja un JSON en la carpeta vigilada. Devuelve un texto descriptivo."""
    pa = config.get("power_automate", {})
    url = os.environ.get(pa.get("variable_url", ""), "")
    if url:
        r = requests.post(url, json=solicitud, timeout=pa.get("timeout_segundos", 30))
        r.raise_for_status()
        return f"Enviado al flujo de Power Automate (HTTP {r.status_code})"
    carpeta = pa.get("carpeta_solicitudes")
    if carpeta:
        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"solicitud_desembolso_{solicitud['caso']}.json"
        ruta.write_text(json.dumps(solicitud, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"Solicitud guardada en {ruta} (Power Automate la tomará de esa carpeta)"
    raise RuntimeError(
        f"Configure la variable de entorno {pa.get('variable_url')} o power_automate.carpeta_solicitudes"
    )
