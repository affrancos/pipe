"""Utilidades para interpretar texto de documentos colombianos (montos, fechas, tasas)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples. Útil para buscar palabras clave."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def solo_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def parse_monto(texto: str) -> float | None:
    """Convierte '1.500.000', '$ 1.500.000,00' o '1,500,000.00' a número."""
    limpio = re.sub(r"[^\d.,]", "", texto or "")
    if not limpio or not re.search(r"\d", limpio):
        return None
    if "." in limpio and "," in limpio:
        decimal = "." if limpio.rfind(".") > limpio.rfind(",") else ","
        miles = "," if decimal == "." else "."
        limpio = limpio.replace(miles, "").replace(decimal, ".")
    else:
        sep = "." if "." in limpio else ("," if "," in limpio else None)
        if sep:
            partes = limpio.split(sep)
            # Varias apariciones o grupo final de 3 dígitos => separador de miles.
            if len(partes) > 2 or len(partes[-1]) == 3:
                limpio = limpio.replace(sep, "")
            else:
                limpio = limpio.replace(sep, ".")
    try:
        return float(limpio)
    except ValueError:
        return None


def pesos(valor: float) -> str:
    """Formato colombiano: $15.000.000"""
    return f"${valor:,.0f}".replace(",", ".")


def parse_numero(texto: str) -> float | None:
    """Número decimal corto como '1,55' o '20.5' (tasas, porcentajes)."""
    try:
        return float(texto.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


_RE_FECHA_NUM = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_RE_FECHA_ISO = re.compile(r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b")
_RE_FECHA_TXT = re.compile(
    r"\b(\d{1,2})\)?\s*(?:dias?\s+)?(?:de|del)?\s*(?:mes\s+de\s+)?"
    r"(" + "|".join(MESES) + r")\s*(?:de|del)?\s*(?:ano\s+)?(\d{4})\b"
)


def _fecha_segura(anio: int, mes: int, dia: int) -> date | None:
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def buscar_fechas(texto: str) -> list[date]:
    """Todas las fechas reconocibles del texto (dd/mm/aaaa, aaaa-mm-dd, '5 de marzo de 2026')."""
    norm = normalizar(texto)
    fechas: list[date] = []
    for d, m, a in _RE_FECHA_NUM.findall(norm):
        f = _fecha_segura(int(a), int(m), int(d))
        if f:
            fechas.append(f)
    for a, m, d in _RE_FECHA_ISO.findall(norm):
        f = _fecha_segura(int(a), int(m), int(d))
        if f:
            fechas.append(f)
    for d, mes, a in _RE_FECHA_TXT.findall(norm):
        f = _fecha_segura(int(a), MESES[mes], int(d))
        if f:
            fechas.append(f)
    return fechas


# --- Tasas de interés ---------------------------------------------------------

def mv_a_ea(tasa_mv_pct: float) -> float:
    return ((1 + tasa_mv_pct / 100) ** 12 - 1) * 100


def ea_a_mv(tasa_ea_pct: float) -> float:
    return ((1 + tasa_ea_pct / 100) ** (1 / 12) - 1) * 100


def a_mv(tasa: float, tipo: str) -> float:
    return tasa if tipo.upper() == "MV" else ea_a_mv(tasa)


def a_ea(tasa: float, tipo: str) -> float:
    return tasa if tipo.upper() == "EA" else mv_a_ea(tasa)


def cuota_fija(monto: float, tasa_mv_pct: float, plazo_meses: int) -> float:
    """Cuota mensual con amortización francesa (cuota fija), sin seguros."""
    i = tasa_mv_pct / 100
    if i == 0:
        return monto / plazo_meses
    return monto * i / (1 - (1 + i) ** -plazo_meses)
