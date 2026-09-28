"""Clasifica cada documento según palabras clave de su contenido y de su nombre de archivo."""

from __future__ import annotations

from .texto import normalizar

# Palabras clave (sin tildes, minúsculas) con su peso. Ajustar con documentos reales.
PALABRAS_CLAVE: dict[str, dict[str, int]] = {
    "cedula": {
        "cedula de ciudadania": 4, "republica de colombia": 2, "identificacion personal": 3,
        "registraduria": 2, "fecha de nacimiento": 2, "lugar de nacimiento": 2,
        "estatura": 2, "g.s. rh": 2, "fecha y lugar de expedicion": 2,
    },
    "desprendible_nomina": {
        "desprendible": 4, "comprobante de pago": 4, "colilla": 4, "volante de pago": 4,
        "devengado": 3, "deducciones": 2, "neto a pagar": 3, "periodo de pago": 2,
        "salario basico": 1, "aporte salud": 1, "aporte pension": 1, "nomina": 1,
    },
    "certificado_laboral": {
        "certificado laboral": 4, "certificacion laboral": 4, "certifica que": 3,
        "a quien interese": 3, "labora en": 2, "presta sus servicios": 2, "tipo de contrato": 2,
        "fecha de ingreso": 2, "termino indefinido": 2, "cargo": 1, "vinculado": 1,
    },
    "pagare": {
        "pagare": 4, "carta de instrucciones": 3, "pagare incondicionalmente": 3,
        "me obligo": 2, "nos obligamos": 2, "espacios en blanco": 2, "a la orden de": 2,
    },
    "autorizacion_libranza": {
        "libranza": 4, "autorizacion de descuento": 4, "autorizo irrevocablemente": 3,
        "pagaduria": 2, "descontar de mi salario": 3, "descuento por nomina": 3, "autorizo": 1,
    },
    "solicitud": {
        "solicitud de credito": 5, "formulario de solicitud": 4, "monto solicitado": 3,
        "valor solicitado": 3, "linea de credito": 2, "referencias personales": 2,
        "referencias familiares": 2, "datos del solicitante": 3, "informacion financiera": 1,
    },
}

# Pistas en el nombre del archivo que descarga Bizagi.
PISTAS_NOMBRE: dict[str, list[str]] = {
    "cedula": ["cedula", "cc_", "documento_identidad", "identificacion"],
    "desprendible_nomina": ["desprendible", "colilla", "nomina", "comprobante"],
    "certificado_laboral": ["certificado_laboral", "certificacion", "cert_lab", "laboral"],
    "pagare": ["pagare"],
    "autorizacion_libranza": ["libranza", "autorizacion"],
    "solicitud": ["solicitud", "formulario"],
}

PUNTAJE_MINIMO = 3


def clasificar(texto: str, nombre_archivo: str = "") -> tuple[str, int]:
    """Devuelve (tipo_documento, puntaje). Tipo 'desconocido' si no alcanza el puntaje mínimo."""
    norm = normalizar(texto)
    nombre = normalizar(nombre_archivo).replace(" ", "_")
    puntajes: dict[str, int] = {}
    for tipo, palabras in PALABRAS_CLAVE.items():
        puntaje = sum(peso for palabra, peso in palabras.items() if palabra in norm)
        if any(pista in nombre for pista in PISTAS_NOMBRE.get(tipo, [])):
            puntaje += 3
        puntajes[tipo] = puntaje
    tipo, puntaje = max(puntajes.items(), key=lambda kv: kv[1])
    return (tipo, puntaje) if puntaje >= PUNTAJE_MINIMO else ("desconocido", puntaje)
