"""Reglas de validación que hoy revisa el auxiliar: documentación, tasa, monto, convenio y condiciones."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

from .texto import a_ea, a_mv, cuota_fija, normalizar, pesos

ERROR, ALERTA, OK = "ERROR", "ALERTA", "OK"

NOMBRES_DOCUMENTO = {
    "solicitud": "Solicitud de crédito",
    "cedula": "Cédula",
    "desprendible_nomina": "Desprendible de nómina",
    "certificado_laboral": "Certificado laboral",
    "autorizacion_libranza": "Autorización de libranza",
    "pagare": "Pagaré",
}


@dataclass
class Hallazgo:
    nivel: str
    regla: str
    detalle: str


@dataclass
class DatosCaso:
    """Datos del caso tal como aparecen en Bizagi. Los vacíos se completan con la solicitud."""

    caso: str
    producto: str | None = None  # libranza | prestamo_personal
    convenio: str | None = None
    cedula: str | None = None
    nombre: str | None = None
    monto: float | None = None
    tasa: float | None = None
    tipo_tasa: str | None = None  # MV | EA
    plazo_meses: int | None = None
    fuentes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Documento:
    archivo: str
    tipo: str
    puntaje: int
    uso_ocr: bool
    campos: dict


def buscar_convenio(nombre_o_codigo: str | None, convenios: list[dict]) -> dict | None:
    if not nombre_o_codigo:
        return None
    buscado = normalizar(nombre_o_codigo)
    for conv in convenios:
        nombres = [conv.get("codigo", ""), conv.get("nombre", ""), *conv.get("alias", [])]
        for n in filter(None, map(normalizar, nombres)):
            if buscado == n or n in buscado or buscado in n:
                return conv
    return None


def _primero(documentos: list[Documento], tipo: str) -> Documento | None:
    return next((d for d in documentos if d.tipo == tipo), None)


def completar_datos_caso(datos: DatosCaso, documentos: list[Documento]) -> DatosCaso:
    """Rellena lo que no vino de Bizagi con lo leído en la solicitud (y registra la fuente)."""
    solicitud = _primero(documentos, "solicitud")
    for campo in ("producto", "convenio", "cedula", "nombre", "monto", "tasa", "tipo_tasa", "plazo_meses"):
        if getattr(datos, campo) is not None:
            datos.fuentes.setdefault(campo, "bizagi")
        elif solicitud and solicitud.campos.get(campo) is not None:
            setattr(datos, campo, solicitud.campos[campo])
            datos.fuentes[campo] = "solicitud"
    if datos.cedula is None:
        cedula = next((d.campos["cedula"] for d in documentos if d.campos.get("cedula")), None)
        if cedula:
            datos.cedula, datos.fuentes["cedula"] = cedula, "documentos"
    if datos.tasa is not None and datos.tipo_tasa is None:
        datos.tipo_tasa = "EA" if datos.tasa > 5 else "MV"
    return datos


def validar(datos: DatosCaso, documentos: list[Documento], config: dict, hoy: date | None = None) -> list[Hallazgo]:
    hoy = hoy or date.today()
    reglas = config.get("reglas", {})
    h: list[Hallazgo] = []

    # 1. Producto y documentos requeridos -------------------------------------------------
    producto_cfg = config.get("productos", {}).get(datos.producto or "")
    if not producto_cfg:
        h.append(Hallazgo(ERROR, "Producto", f"Producto no identificado o no configurado: {datos.producto!r}"))
    else:
        tipos = {d.tipo for d in documentos}
        for requerido in producto_cfg.get("documentos_requeridos", []):
            nombre = NOMBRES_DOCUMENTO.get(requerido, requerido)
            if requerido in tipos:
                h.append(Hallazgo(OK, "Documentación", f"{nombre}: presente"))
            else:
                h.append(Hallazgo(ERROR, "Documentación", f"{nombre}: no se encontró en el expediente"))
    for d in documentos:
        if d.tipo == "desconocido":
            h.append(Hallazgo(ALERTA, "Documentación", f"No se pudo clasificar '{d.archivo}'; revisar manualmente"))

    # 2. Identidad consistente -------------------------------------------------------------
    cedulas = {d.archivo: d.campos["cedula"] for d in documentos if d.campos.get("cedula")}
    if datos.cedula:
        distintas = {a: c for a, c in cedulas.items() if c != datos.cedula}
        if distintas:
            detalle = ", ".join(f"{a} ({c})" for a, c in distintas.items())
            h.append(Hallazgo(ERROR, "Identidad", f"Cédula distinta a la del caso ({datos.cedula}) en: {detalle}"))
        elif cedulas:
            h.append(Hallazgo(OK, "Identidad", f"Cédula {datos.cedula} coincide en {len(cedulas)} documento(s)"))
        else:
            h.append(Hallazgo(ALERTA, "Identidad", "No se pudo leer la cédula en ningún documento"))
    else:
        h.append(Hallazgo(ALERTA, "Identidad", "El caso no tiene cédula para comparar"))

    # 3. Vigencia de documentos -----------------------------------------------------------
    for tipo, dias_max in reglas.get("vigencia_dias", {}).items():
        doc = _primero(documentos, tipo)
        if not doc:
            continue
        nombre = NOMBRES_DOCUMENTO.get(tipo, tipo)
        fecha = doc.campos.get("fecha_documento")
        if not fecha:
            h.append(Hallazgo(ALERTA, "Vigencia", f"{nombre}: no se pudo leer la fecha de expedición"))
        elif (hoy - fecha).days > dias_max:
            h.append(Hallazgo(ERROR, "Vigencia", f"{nombre}: expedido el {fecha:%d/%m/%Y}, supera {dias_max} días"))
        else:
            h.append(Hallazgo(OK, "Vigencia", f"{nombre}: expedido el {fecha:%d/%m/%Y}"))

    # 4. Convenio -------------------------------------------------------------------------
    convenio = buscar_convenio(datos.convenio, config.get("convenios", []))
    if not convenio:
        h.append(Hallazgo(ERROR, "Convenio", f"Convenio no encontrado en convenios.yaml: {datos.convenio!r}"))
    elif datos.producto and datos.producto not in convenio.get("productos", []):
        h.append(Hallazgo(ERROR, "Convenio", f"El convenio {convenio['codigo']} no permite {datos.producto}"))
    else:
        h.append(Hallazgo(OK, "Convenio", f"{convenio['codigo']} - {convenio['nombre']}"))

    # 5. Monto ----------------------------------------------------------------------------
    tol = reglas.get("tolerancia_monto", 0)
    if datos.monto is None:
        h.append(Hallazgo(ERROR, "Monto", "No se encontró el monto del crédito"))
    else:
        if convenio:
            mn, mx = convenio.get("monto_min", 0), convenio.get("monto_max", float("inf"))
            if not mn <= datos.monto <= mx:
                h.append(Hallazgo(ERROR, "Monto", f"{pesos(datos.monto)} fuera del rango del convenio ({pesos(mn)} - {pesos(mx)})"))
            else:
                h.append(Hallazgo(OK, "Monto", f"{pesos(datos.monto)} dentro del rango del convenio"))
        for tipo in ("solicitud", "pagare"):
            doc = _primero(documentos, tipo)
            if doc and doc.campos.get("monto") is not None and datos.fuentes.get("monto") != tipo:
                if abs(doc.campos["monto"] - datos.monto) > tol:
                    h.append(Hallazgo(ERROR, "Monto",
                                      f"{NOMBRES_DOCUMENTO[tipo]} indica {pesos(doc.campos['monto'])} y el caso {pesos(datos.monto)}"))

    # 6. Tasa -----------------------------------------------------------------------------
    tasa_mv = tasa_ea = None
    if datos.tasa is None:
        h.append(Hallazgo(ERROR, "Tasa", "No se encontró la tasa del crédito"))
    else:
        tasa_mv, tasa_ea = a_mv(datos.tasa, datos.tipo_tasa), a_ea(datos.tasa, datos.tipo_tasa)
        usura = reglas.get("tasa_usura_ea")
        if usura and tasa_ea > usura:
            h.append(Hallazgo(ERROR, "Tasa", f"{tasa_ea:.2f}% E.A. supera la tasa de usura ({usura:.2f}% E.A.)"))
        if convenio and convenio.get("tasa_max") is not None:
            max_mv = a_mv(convenio["tasa_max"], convenio.get("tipo_tasa", "MV"))
            if tasa_mv > max_mv + reglas.get("tolerancia_tasa", 0):
                h.append(Hallazgo(ERROR, "Tasa",
                                  f"{tasa_mv:.4f}% M.V. supera la del convenio ({max_mv:.4f}% M.V.)"))
            else:
                h.append(Hallazgo(OK, "Tasa", f"{tasa_mv:.4f}% M.V. ({tasa_ea:.2f}% E.A.) dentro del convenio"))
        solicitud = _primero(documentos, "solicitud")
        if solicitud and "tasa" in solicitud.campos and datos.fuentes.get("tasa") != "solicitud":
            doc_mv = a_mv(solicitud.campos["tasa"], solicitud.campos.get("tipo_tasa", "MV"))
            if abs(doc_mv - tasa_mv) > reglas.get("tolerancia_tasa", 0):
                h.append(Hallazgo(ERROR, "Tasa", f"La solicitud indica {doc_mv:.4f}% M.V. y el caso {tasa_mv:.4f}% M.V."))

    # 7. Plazo ----------------------------------------------------------------------------
    if datos.plazo_meses is None:
        h.append(Hallazgo(ERROR, "Plazo", "No se encontró el plazo del crédito"))
    elif convenio and datos.plazo_meses > convenio.get("plazo_max_meses", 10**6):
        h.append(Hallazgo(ERROR, "Plazo", f"{datos.plazo_meses} meses supera el máximo del convenio ({convenio['plazo_max_meses']})"))
    else:
        h.append(Hallazgo(OK, "Plazo", f"{datos.plazo_meses} meses"))

    # 8. Capacidad de pago ----------------------------------------------------------------
    h.extend(_validar_capacidad(datos, documentos, producto_cfg, tasa_mv))
    return h


def _validar_capacidad(datos, documentos, producto_cfg, tasa_mv) -> list[Hallazgo]:
    if not producto_cfg or not producto_cfg.get("capacidad_max_pct"):
        return []
    pct = producto_cfg["capacidad_max_pct"]
    desprendible = _primero(documentos, "desprendible_nomina")
    certificado = _primero(documentos, "certificado_laboral")
    campos = desprendible.campos if desprendible else {}
    devengado = campos.get("total_devengado") or campos.get("salario_basico") or (
        certificado.campos.get("salario") if certificado else None)
    deducciones = campos.get("total_deducciones")
    if devengado is None or deducciones is None:
        return [Hallazgo(ALERTA, "Capacidad de pago",
                         "Faltan devengado o deducciones del desprendible; calcular manualmente")]
    if None in (datos.monto, tasa_mv, datos.plazo_meses):
        return [Hallazgo(ALERTA, "Capacidad de pago", "Faltan monto, tasa o plazo para calcular la cuota")]

    cuota = cuota_fija(datos.monto, tasa_mv, datos.plazo_meses)
    compromiso = (deducciones + cuota) / devengado * 100
    detalle = (f"Cuota estimada {pesos(cuota)}; deducciones + cuota = {compromiso:.1f}% "
               f"del devengado ({pesos(devengado)}); máximo {pct}%")
    hallazgos = [Hallazgo(ERROR if compromiso > pct else OK, "Capacidad de pago", detalle)]

    autorizacion = _primero(documentos, "autorizacion_libranza")
    if autorizacion and autorizacion.campos.get("cuota"):
        cuota_doc = autorizacion.campos["cuota"]
        if abs(cuota_doc - cuota) / cuota > 0.05:  # los seguros suelen explicar diferencias pequeñas
            hallazgos.append(Hallazgo(ALERTA, "Capacidad de pago",
                                      f"La autorización indica cuota {pesos(cuota_doc)} vs estimada {pesos(cuota)}"))
    return hallazgos


def estado_resultado(hallazgos: list[Hallazgo]) -> str:
    niveles = {x.nivel for x in hallazgos}
    if ERROR in niveles:
        return "REQUIERE_CORRECCION"
    if ALERTA in niveles:
        return "REVISAR_ALERTAS"
    return "LISTO_PARA_APROBACION"
