import shutil
from datetime import date

import pymupdf
import pytest

from desembolsos import expediente, notificador, reporte
from desembolsos.config import cargar_config
from desembolsos.validador import ERROR, DatosCaso, Documento, estado_resultado, validar

from .test_texto_extractores import CERTIFICADO, DESPRENDIBLE, SOLICITUD

HOY = date(2026, 9, 28)

AUTORIZACION = """AUTORIZACIÓN DE DESCUENTO POR NÓMINA - LIBRANZA
Yo, MARIA FERNANDA LOPEZ RUIZ con C.C. 1020304050 autorizo irrevocablemente a la pagaduría
Convenio: EJEMPLO UNO S.A.S. para descontar de mi salario la cuota mensual de $ 360.000 durante 60 meses."""

PAGARE = """PAGARÉ No. 998877
Yo, MARIA FERNANDA LOPEZ RUIZ, identificada con C.C. 1020304050, me obligo a pagar incondicionalmente
a la orden de la entidad la suma de $ 15.000.000 junto con la carta de instrucciones."""

CEDULA = """REPUBLICA DE COLOMBIA
IDENTIFICACION PERSONAL
CEDULA DE CIUDADANIA
NUMERO 1.020.304.050
LOPEZ RUIZ
MARIA FERNANDA
FECHA DE NACIMIENTO 12-MAR-1990"""


@pytest.fixture
def config(tmp_path):
    cfg = cargar_config()
    cfg["rutas"]["casos"] = tmp_path / "casos"
    cfg["rutas"]["control_excel"] = tmp_path / "casos" / "control.xlsx"
    cfg["power_automate"]["carpeta_solicitudes"] = tmp_path / "salida_pa"
    cfg["ocr"]["tesseract_cmd"] = None
    return cfg


def _docs_validos():
    return [
        Documento("sol.pdf", "solicitud", 9, False, {"cedula": "1020304050", "monto": 15e6, "tasa": 1.45,
                                                      "tipo_tasa": "MV", "plazo_meses": 60}),
        Documento("cc.jpg", "cedula", 9, True, {"cedula": "1020304050"}),
        Documento("des.pdf", "desprendible_nomina", 9, False,
                  {"cedula": "1020304050", "total_devengado": 4.2e6, "total_deducciones": 9e5,
                   "fecha_documento": date(2026, 9, 15)}),
        Documento("cert.pdf", "certificado_laboral", 9, False, {"fecha_documento": date(2026, 9, 10)}),
        Documento("aut.pdf", "autorizacion_libranza", 9, False, {"cuota": 360_000}),
        Documento("pag.pdf", "pagare", 9, False, {"monto": 15e6}),
    ]


def _datos(**cambios):
    base = dict(caso="1", producto="libranza", convenio="CONV-001", cedula="1020304050",
                monto=15e6, tasa=1.45, tipo_tasa="MV", plazo_meses=60)
    base.update(cambios)
    return DatosCaso(**base)


def _errores(hallazgos):
    return [h for h in hallazgos if h.nivel == ERROR]


def test_caso_valido_queda_listo(config):
    hallazgos = validar(_datos(), _docs_validos(), config, HOY)
    assert _errores(hallazgos) == []
    assert estado_resultado(hallazgos) == "LISTO_PARA_APROBACION"


@pytest.mark.parametrize("cambios,regla", [
    ({"tasa": 1.9}, "Tasa"),                    # supera tasa del convenio
    ({"tasa": 2.5}, "Tasa"),                    # supera usura
    ({"monto": 90e6}, "Monto"),                 # fuera del rango del convenio
    ({"plazo_meses": 150}, "Plazo"),
    ({"convenio": "NO EXISTE"}, "Convenio"),
    ({"producto": "prestamo_personal"}, "Convenio"),  # convenio no permite el producto
    ({"cedula": "999999999"}, "Identidad"),
])
def test_reglas_detectan_errores(config, cambios, regla):
    reglas_con_error = {h.regla for h in _errores(validar(_datos(**cambios), _docs_validos(), config, HOY))}
    assert regla in reglas_con_error


def test_documento_faltante_y_vencido(config):
    docs = [d for d in _docs_validos() if d.tipo != "pagare"]
    docs[3].campos["fecha_documento"] = date(2026, 7, 1)
    detalles = [h.detalle for h in _errores(validar(_datos(), docs, config, HOY))]
    assert any("Pagaré" in d for d in detalles)
    assert any("Certificado laboral" in d and "supera 30 días" in d for d in detalles)


def test_capacidad_de_pago_excedida(config):
    docs = _docs_validos()
    docs[2].campos["total_deducciones"] = 1.9e6  # (1.9M + cuota) > 50% de 4.2M
    assert "Capacidad de pago" in {h.regla for h in _errores(validar(_datos(), docs, config, HOY))}


def _pdf_texto(ruta, texto):
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), texto, fontsize=11)
    doc.save(ruta)


def _imagen_escaneada(ruta, texto):
    """Simula un escaneo: la página se convierte en imagen, sin capa de texto."""
    doc = pymupdf.open()
    doc.new_page(width=420, height=260).insert_textbox(pymupdf.Rect(20, 20, 400, 250), texto, fontsize=14)
    doc[0].get_pixmap(dpi=200).save(ruta)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")
def test_flujo_completo_con_pdf_e_imagen(config, tmp_path):
    docs = expediente.carpeta_caso(config, "123456") / "documentos"
    docs.mkdir(parents=True)
    _pdf_texto(docs / "formulario.pdf", SOLICITUD)
    _pdf_texto(docs / "desprendible.pdf", DESPRENDIBLE)
    _pdf_texto(docs / "certificado.pdf", CERTIFICADO)
    _pdf_texto(docs / "autorizacion.pdf", AUTORIZACION)
    _pdf_texto(docs / "pagare.pdf", PAGARE)
    _imagen_escaneada(docs / "foto_documento.png", CEDULA)

    # Solo se conoce el caso y el producto: el resto se toma de la solicitud.
    resultado = expediente.procesar_caso(DatosCaso(caso="123456", producto="libranza"), config, HOY)

    tipos = {d["archivo"]: d["tipo"] for d in resultado["documentos"]}
    assert tipos["foto_documento.png"] == "cedula"
    assert tipos["formulario.pdf"] == "solicitud"
    assert resultado["datos_caso"]["monto"] == 15_000_000
    assert [h for h in resultado["hallazgos"] if h["nivel"] == "ERROR"] == []

    reporte.resumen_caso(resultado, tmp_path / "resumen.xlsx")
    reporte.registrar_control(resultado, config["rutas"]["control_excel"])
    solicitud = notificador.construir_solicitud(resultado, "ok", config)
    assert solicitud["correo_gestor"]
    assert solicitud["cedula_enmascarada"] == "******4050"
    assert "salida_pa" in notificador.enviar(solicitud, config)


def test_datos_desde_dict_acepta_textos_de_bizagi():
    d = expediente.datos_desde_dict("LIB-1", {
        "producto": "Libranza", "cedula": "1.020.304.050", "monto": "$ 15.000.000",
        "tasa": "1,45 %", "tipo_tasa": "M.V.", "plazo_meses": "60 meses", "convenio": "",
    })
    assert (d.producto, d.cedula, d.monto, d.tasa, d.tipo_tasa, d.plazo_meses, d.convenio) == (
        "libranza", "1020304050", 15_000_000, 1.45, "MV", 60, None)
    assert expediente.datos_desde_dict("x", {"tipo_tasa": "E.A."}).tipo_tasa == "EA"


def test_nombre_de_carpeta_valido_en_windows():
    assert expediente.nombre_carpeta("LIB/2026:0001 ") == "LIB_2026_0001"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")
def test_pendientes_procesa_carpetas_de_power_automate_desktop(config):
    import json

    from desembolsos.cli import procesar_pendientes

    raiz = config["rutas"]["casos"]
    # Caso completo, como lo deja PAD: documentos + caso.json + LISTO.txt
    base = raiz / "LIB-0001"
    (base / "documentos").mkdir(parents=True)
    for nombre, texto in [("solicitud.pdf", SOLICITUD), ("desprendible.pdf", DESPRENDIBLE),
                          ("certificado.pdf", CERTIFICADO), ("autorizacion.pdf", AUTORIZACION),
                          ("pagare.pdf", PAGARE)]:
        _pdf_texto(base / "documentos" / nombre, texto)
    (base / "caso.json").write_text(json.dumps({"producto": "libranza", "convenio": "CONV-001",
                                                "monto": "$ 15.000.000", "plazo_meses": "60"}),
                                    encoding="utf-8-sig")
    (base / "LISTO.txt").write_text("ok")
    # Caso marcado como listo pero sin documentos: no debe detener a los demás.
    (raiz / "LIB-0002").mkdir()
    (raiz / "LIB-0002" / "LISTO.txt").write_text("ok")
    # Carpeta aún descargando (sin LISTO.txt): se ignora.
    (raiz / "LIB-0003" / "documentos").mkdir(parents=True)

    assert expediente.casos_pendientes(config) == ["LIB-0001", "LIB-0002"]
    assert procesar_pendientes(config, enviar=True) == 2

    resultado = expediente.cargar_resultado(config, "LIB-0001")
    assert resultado["datos_caso"]["fuentes"]["monto"] == "bizagi"
    # Falta la cédula (solo está la imagen en el otro test), así que queda con error y no se envía.
    assert resultado["estado"] == "REQUIERE_CORRECCION"
    assert not (config["power_automate"]["carpeta_solicitudes"]).exists()
    assert (raiz / "LIB-0002" / "ERROR_PROCESO.txt").exists()
    assert expediente.casos_pendientes(config) == []  # no se reprocesa
