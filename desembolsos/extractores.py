"""Extracción de campos (cédula, montos, tasa, plazo, salario...) del texto de cada documento.

Todas las búsquedas se hacen sobre el texto normalizado (minúsculas, sin tildes, espacios
simples), lo que las hace tolerantes a los errores típicos del OCR. Las expresiones regulares
son un punto de partida: se deben afinar con los formatos reales de la entidad.
"""

from __future__ import annotations

import re
from datetime import date

from .texto import buscar_fechas, normalizar, parse_monto, parse_numero, solo_digitos

_MONTO = r"\$?\s*(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d{4,}(?:[.,]\d{1,2})?)"
_CEDULA = r"(\d{6,10}(?!\d)|\d{1,3}(?:[.,\s]?\d{3}){1,3}(?!\d))"


def _monto_con_etiqueta(norm: str, etiquetas: list[str], ventana: int = 40) -> float | None:
    """Primer monto que sigue a una etiqueta. Las etiquetas van en orden de prioridad."""
    for etiqueta in etiquetas:
        for m in re.finditer(rf"{etiqueta}[^\d$]{{0,{ventana}}}{_MONTO}", norm):
            valor = parse_monto(m.group(1))
            if valor and valor >= 1000:  # descarta números sueltos (días, códigos)
                return valor
    return None


def extraer_cedula(norm: str) -> str | None:
    patron = (
        r"(?:cedula de ciudadania|cedula|c\.\s?c\.?|\bcc\b|nuip|documento de identidad|"
        r"identificad[oa] con|identificacion)\s*(?:no\.?|numero|n[°o])?\s*[:#.]?\s*" + _CEDULA
    )
    for m in re.finditer(patron, norm):
        digitos = solo_digitos(m.group(1))
        if 6 <= len(digitos) <= 10:
            return digitos
    # Cédula física: "NUMERO 1.234.567.890" sin otra etiqueta.
    m = re.search(r"numero\s*" + _CEDULA, norm)
    if m and 6 <= len(solo_digitos(m.group(1))) <= 10:
        return solo_digitos(m.group(1))
    return None


def extraer_nombre(norm: str) -> str | None:
    patrones = [
        r"(?:nombres? y apellidos|nombre completo|nombre del (?:solicitante|trabajador|empleado|deudor)|"
        r"nombre)\s*:\s*([a-z][a-z ]{4,60}?)(?=\s*(?:cedula|c\.c|cc\b|identificacion|documento|\d|$))",
        r"(?:senor|senora|sr\.|sra\.)(?:\s*\(a\))?\s+([a-z][a-z ]{4,60}?)\s*,?\s*(?:identificad|con cedula|c\.c|cc\b)",
    ]
    for patron in patrones:
        m = re.search(patron, norm)
        if m:
            return m.group(1).strip().upper()
    return None


def extraer_tasa(norm: str) -> tuple[float, str] | None:
    """Devuelve (tasa_en_%, 'MV' | 'EA')."""
    patron = (
        r"tasa[^\d%]{0,60}?(\d{1,2}(?:[.,]\d{1,4})?)\s*%\s*"
        r"(e\.?\s?a\.?|efectiva anual|m\.?\s?v\.?|n\.?\s?m\.?\s?v\.?|mes vencido|mensual|nominal mensual)?"
    )
    m = re.search(patron, norm)
    if not m:
        return None
    valor = parse_numero(m.group(1))
    if valor is None:
        return None
    sufijo = (m.group(2) or "").replace(".", "").replace(" ", "")
    if sufijo.startswith("e"):
        tipo = "EA"
    elif sufijo:
        tipo = "MV"
    else:
        tipo = "EA" if valor > 5 else "MV"  # sin sufijo: una tasa > 5% casi siempre es anual
    return valor, tipo


def extraer_plazo(norm: str) -> int | None:
    m = re.search(r"plazo[^\d]{0,30}(\d{1,3})\s*(?:meses|cuotas|mensualidades)?", norm)
    if m:
        plazo = int(m.group(1))
        return plazo if 1 <= plazo <= 360 else None
    return None


_ETIQUETAS_CONVENIO = r"convenio|pagaduria|entidad pagadora|empresa pagadora"


def extraer_convenio(norm: str) -> str | None:
    for m in re.finditer(
        rf"(?:{_ETIQUETAS_CONVENIO})\s*[:\-]?\s*"
        r"([a-z0-9][a-z0-9 .&\-]{2,60}?)"
        r"(?=\s*(?:nit\b|ciudad|monto|valor|plazo|tasa|linea|cargo|fecha|nombre|cedula|para\b|[,;:]|$))",
        norm,
    ):
        valor = m.group(1).strip()
        if not re.fullmatch(_ETIQUETAS_CONVENIO, valor):
            return valor.upper()
    return None


def extraer_tipo_contrato(norm: str) -> str | None:
    for clave, nombre in [
        ("termino indefinido", "INDEFINIDO"), ("termino fijo", "FIJO"),
        ("obra o labor", "OBRA_LABOR"), ("prestacion de servicios", "PRESTACION_SERVICIOS"),
        ("carrera administrativa", "CARRERA_ADMINISTRATIVA"), ("libre nombramiento", "LIBRE_NOMBRAMIENTO"),
        ("pensionado", "PENSIONADO"),
    ]:
        if clave in norm:
            return nombre
    return None


def extraer_cargo(norm: str) -> str | None:
    m = re.search(
        r"cargo\s*(?:de|como)?\s*:?\s*([a-z][a-z ]{2,40}?)"
        r"(?=\s*(?:,|\.|con |desde|devengando|mediante|y |tipo|salario|asignacion|$))",
        norm,
    )
    return m.group(1).strip().upper() if m else None


def extraer_fecha_ingreso(norm: str) -> date | None:
    m = re.search(r"(?:fecha de ingreso|desde el|labora desde|vinculad[oa] desde)\s*:?\s*(.{0,40})", norm)
    if m:
        fechas = buscar_fechas(m.group(1))
        return fechas[0] if fechas else None
    return None


def fecha_documento(norm: str, hoy: date | None = None) -> date | None:
    """Fecha de expedición estimada: la fecha más reciente que no esté en el futuro."""
    hoy = hoy or date.today()
    fechas = [f for f in buscar_fechas(norm) if f <= hoy]
    return max(fechas) if fechas else None


def extraer_campos(tipo: str, texto: str, hoy: date | None = None) -> dict:
    norm = normalizar(texto)
    campos: dict = {"cedula": extraer_cedula(norm), "nombre": extraer_nombre(norm)}

    if tipo == "solicitud":
        campos["monto"] = _monto_con_etiqueta(
            norm, ["monto solicitado", "valor solicitado", "monto del credito", "valor del credito", "monto", "valor"]
        )
        tasa = extraer_tasa(norm)
        if tasa:
            campos["tasa"], campos["tipo_tasa"] = tasa
        campos["plazo_meses"] = extraer_plazo(norm)
        campos["convenio"] = extraer_convenio(norm)
        campos["cuota"] = _monto_con_etiqueta(norm, ["valor de la cuota", "cuota mensual", "valor cuota"])
        campos["producto"] = "libranza" if "libranza" in norm else None

    elif tipo == "desprendible_nomina":
        campos["salario_basico"] = _monto_con_etiqueta(norm, ["salario basico", "sueldo basico", "basico"])
        campos["total_devengado"] = _monto_con_etiqueta(norm, ["total devengado", "total devengos", "devengado"])
        campos["total_deducciones"] = _monto_con_etiqueta(
            norm, ["total deducciones", "total descuentos", "total deducido", "deducciones"]
        )
        campos["neto_pagar"] = _monto_con_etiqueta(norm, ["neto a pagar", "neto pagado", "total a pagar", "neto"])
        campos["fecha_documento"] = fecha_documento(norm, hoy)

    elif tipo == "certificado_laboral":
        campos["salario"] = _monto_con_etiqueta(
            norm, ["salario", "asignacion basica", "devengando", "sueldo", "remuneracion"], ventana=60
        )
        campos["cargo"] = extraer_cargo(norm)
        campos["tipo_contrato"] = extraer_tipo_contrato(norm)
        campos["fecha_ingreso"] = extraer_fecha_ingreso(norm)
        campos["empresa"] = extraer_convenio(norm)
        campos["fecha_documento"] = fecha_documento(norm, hoy)

    elif tipo == "pagare":
        campos["monto"] = _monto_con_etiqueta(
            norm, ["la suma de", "suma de", "por valor de", "cantidad de", "valor de"], ventana=80
        )

    elif tipo == "autorizacion_libranza":
        campos["cuota"] = _monto_con_etiqueta(
            norm, ["valor de la cuota", "cuota mensual", "suma mensual", "descontar", "valor cuota"], ventana=60
        )
        campos["convenio"] = extraer_convenio(norm)
        campos["plazo_meses"] = extraer_plazo(norm)

    return {k: v for k, v in campos.items() if v is not None}
