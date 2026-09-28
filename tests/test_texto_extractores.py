from datetime import date

import pytest

from desembolsos.clasificador import clasificar
from desembolsos.extractores import extraer_campos
from desembolsos.texto import buscar_fechas, cuota_fija, ea_a_mv, mv_a_ea, parse_monto

SOLICITUD = """
SOLICITUD DE CRÉDITO - LIBRANZA
Datos del solicitante
Nombre completo: MARIA FERNANDA LOPEZ RUIZ   Cédula de ciudadanía No. 1.020.304.050
Convenio: EJEMPLO UNO S.A.S.
Monto solicitado: $ 15.000.000   Plazo: 60 meses
Tasa de interés: 1,45% M.V.
"""

DESPRENDIBLE = """
COMPROBANTE DE PAGO DE NÓMINA  Periodo de pago: 01/09/2026 al 15/09/2026
Empleado: MARIA FERNANDA LOPEZ RUIZ   C.C. 1020304050
Salario básico  $ 4.200.000
Total devengado $ 4.200.000
Total deducciones $ 900.000
Neto a pagar $ 3.300.000
"""

CERTIFICADO = """
CERTIFICADO LABORAL
EJEMPLO UNO S.A.S. certifica que la señora MARIA FERNANDA LOPEZ RUIZ, identificada con cédula
de ciudadanía No. 1.020.304.050, labora desde el 3 de febrero de 2019 con contrato a término indefinido,
en el cargo de ANALISTA CONTABLE, devengando un salario básico mensual de $4.200.000.
Se expide en Bogotá a los 10 días del mes de septiembre de 2026.
"""


@pytest.mark.parametrize("texto,esperado", [
    ("$ 1.500.000", 1500000), ("1.500.000,50", 1500000.5), ("1,500,000.00", 1500000),
    ("15000000", 15000000), ("2.500", 2500), ("1,5", 1.5),
])
def test_parse_monto(texto, esperado):
    assert parse_monto(texto) == esperado


def test_fechas_en_letras_y_numeros():
    fechas = buscar_fechas("Bogotá, 10 días del mes de septiembre de 2026 y 01/09/2026")
    assert date(2026, 9, 10) in fechas and date(2026, 9, 1) in fechas


def test_conversion_tasas_y_cuota():
    assert mv_a_ea(1.5) == pytest.approx(19.5618, abs=1e-3)
    assert ea_a_mv(mv_a_ea(1.2)) == pytest.approx(1.2)
    assert cuota_fija(10_000_000, 1.0, 12) == pytest.approx(888_487.88, abs=0.01)


@pytest.mark.parametrize("texto,archivo,tipo", [
    (SOLICITUD, "doc1.pdf", "solicitud"),
    (DESPRENDIBLE, "archivo.pdf", "desprendible_nomina"),
    (CERTIFICADO, "x.pdf", "certificado_laboral"),
    ("texto ilegible", "pagare_firmado.pdf", "pagare"),
    ("nada reconocible", "scan001.jpg", "desconocido"),
])
def test_clasificar(texto, archivo, tipo):
    assert clasificar(texto, archivo)[0] == tipo


def test_extraer_solicitud():
    c = extraer_campos("solicitud", SOLICITUD)
    assert c["cedula"] == "1020304050"
    assert c["nombre"] == "MARIA FERNANDA LOPEZ RUIZ"
    assert c["monto"] == 15_000_000
    assert (c["tasa"], c["tipo_tasa"]) == (1.45, "MV")
    assert c["plazo_meses"] == 60
    assert c["convenio"] == "EJEMPLO UNO S.A.S."
    assert c["producto"] == "libranza"


def test_extraer_desprendible():
    c = extraer_campos("desprendible_nomina", DESPRENDIBLE, hoy=date(2026, 9, 28))
    assert c["cedula"] == "1020304050"
    assert c["total_devengado"] == 4_200_000
    assert c["total_deducciones"] == 900_000
    assert c["neto_pagar"] == 3_300_000
    assert c["fecha_documento"] == date(2026, 9, 15)


def test_extraer_certificado():
    c = extraer_campos("certificado_laboral", CERTIFICADO, hoy=date(2026, 9, 28))
    assert c["cedula"] == "1020304050"
    assert c["nombre"] == "MARIA FERNANDA LOPEZ RUIZ"
    assert c["salario"] == 4_200_000
    assert c["tipo_contrato"] == "INDEFINIDO"
    assert c["cargo"] == "ANALISTA CONTABLE"
    assert c["fecha_ingreso"] == date(2019, 2, 3)
    assert c["fecha_documento"] == date(2026, 9, 10)
