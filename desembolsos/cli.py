"""Línea de comandos para el auxiliar.

Ejemplos:
    python -m desembolsos procesar 123456 --producto libranza --convenio CONV-001 \
        --cedula 1020304050 --monto 15.000.000 --tasa 1,45 --tipo-tasa MV --plazo 60
    python -m desembolsos enviar 123456 --observaciones "Cliente con antigüedad de 5 años"
    python -m desembolsos pendientes --vigilar 60     # casos que deja Power Automate Desktop
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import descargas, expediente, notificador, reporte
from .config import cargar_config

ICONOS = {"ERROR": "[X]", "ALERTA": "[!]", "OK": "[OK]"}


def _recoger(args, config) -> bool:
    origen = config["rutas"]["descargas"]
    cfg = config.get("descargas", {})
    if en_curso := descargas.descargas_en_curso(origen):
        print(f"Hay descargas sin terminar en {origen}: {[p.name for p in en_curso]}. Espere a que terminen.")
        return False
    archivos = descargas.archivos_recientes(origen, cfg.get("extensiones", [".pdf"]), cfg.get("ventana_minutos", 60))
    if not archivos:
        print(f"No hay documentos nuevos en {origen} (últimos {cfg.get('ventana_minutos', 60)} min).")
        return True
    print(f"Documentos encontrados en Descargas para el caso {args.caso}:")
    for a in archivos:
        print(f"  - {a.name}")
    if not args.si and input("¿Pertenecen todos a este caso? (s/n): ").strip().lower() != "s":
        print("Cancelado. Deje en Descargas solo los documentos del caso, o use --sin-recoger.")
        return False
    destino = expediente.carpeta_caso(config, args.caso) / "documentos"
    descargas.mover_a_expediente(archivos, destino, copiar=args.copiar)
    print(f"{len(archivos)} documento(s) {'copiados' if args.copiar else 'movidos'} a {destino}")
    return True


def _imprimir(resultado: dict) -> None:
    print(f"\n=== Caso {resultado['caso']}: {resultado['estado']} ===")
    for d in resultado["documentos"]:
        print(f"  {d['archivo']}: {d['tipo']}{' (OCR)' if d['uso_ocr'] else ''}")
    print()
    for h in resultado["hallazgos"]:
        print(f"  {ICONOS.get(h['nivel'], '')} {h['regla']}: {h['detalle']}")


def _validar_y_reportar(caso: str, valores: dict, config: dict) -> dict:
    """Valida el caso con los datos de caso.json, sobrescritos por los que se pasen en `valores`."""
    datos = expediente.datos_desde_dict(caso, {**expediente.leer_datos_caso(config, caso), **valores})
    resultado = expediente.procesar_caso(datos, config)
    base = expediente.carpeta_caso(config, caso)
    reporte.resumen_caso(resultado, base / f"resumen_{expediente.nombre_carpeta(caso)}.xlsx")
    reporte.registrar_control(resultado, config["rutas"]["control_excel"])
    _imprimir(resultado)
    return resultado


def cmd_procesar(args, config) -> int:
    if not args.sin_recoger and not _recoger(args, config):
        return 1
    valores = {
        "producto": args.producto, "convenio": args.convenio, "cedula": args.cedula, "nombre": args.nombre,
        "monto": args.monto, "tasa": args.tasa, "tipo_tasa": args.tipo_tasa, "plazo_meses": args.plazo,
    }
    resultado = _validar_y_reportar(args.caso, {k: v for k, v in valores.items() if v is not None}, config)
    print(f"\nResumen en: {expediente.carpeta_caso(config, args.caso)}")
    if args.enviar:
        return _enviar(resultado, config, args.forzar, args.observaciones)
    print(f"Revise el resultado y envíe al gestor con: python -m desembolsos enviar {args.caso}")
    return 0


def _enviar(resultado: dict, config: dict, forzar: bool = False, observaciones: str | None = None) -> int:
    if resultado["estado"] == "REQUIERE_CORRECCION" and not forzar:
        print("\nEl caso tiene ERRORES y no se envió al gestor. Corrija o use --forzar con observaciones.")
        return 2
    solicitud = notificador.construir_solicitud(resultado, observaciones or "", config)
    print(notificador.enviar(solicitud, config))
    reporte.registrar_control(resultado, config["rutas"]["control_excel"], enviado=True)
    return 0


def cmd_enviar(args, config) -> int:
    return _enviar(expediente.cargar_resultado(config, args.caso), config, args.forzar, args.observaciones)


def procesar_pendientes(config: dict, enviar: bool = False) -> int:
    """Procesa cada carpeta marcada con LISTO.txt. Devuelve cuántos casos procesó."""
    pendientes = expediente.casos_pendientes(config)
    for caso in pendientes:
        base = expediente.carpeta_caso(config, caso)
        try:
            resultado = _validar_y_reportar(caso, {}, config)
        except Exception as e:  # un caso con problemas no detiene los demás
            logging.exception("Error procesando el caso %s", caso)
            (base / expediente.MARCA_ERROR).write_text(f"{type(e).__name__}: {e}\n", encoding="utf-8")
            print(f"Caso {caso}: no se pudo procesar ({e}). Detalle en {expediente.MARCA_ERROR}")
            continue
        if enviar and resultado["estado"] != "REQUIERE_CORRECCION":
            _enviar(resultado, config)
    return len(pendientes)


def cmd_pendientes(args, config) -> int:
    if not args.vigilar:
        if procesar_pendientes(config, args.enviar) == 0:
            print(f"No hay casos pendientes en {config['rutas']['casos']}")
        return 0
    print(f"Vigilando {config['rutas']['casos']} cada {args.vigilar} s (Ctrl+C para detener)...")
    try:
        while True:
            procesar_pendientes(config, args.enviar)
            time.sleep(args.vigilar)
    except KeyboardInterrupt:
        print("Detenido.")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="desembolsos", description="Validación de desembolsos (libranza / préstamo personal)")
    p.add_argument("-v", "--verbose", action="store_true", help="Mostrar el detalle de cada documento")
    sub = p.add_subparsers(dest="comando", required=True)

    pr = sub.add_parser("procesar", help="Recoger documentos de Descargas y validar el caso")
    pr.add_argument("caso", help="Número de caso en Bizagi")
    pr.add_argument("--producto", choices=["libranza", "prestamo_personal"])
    pr.add_argument("--convenio", help="Código o nombre del convenio")
    pr.add_argument("--cedula")
    pr.add_argument("--nombre")
    pr.add_argument("--monto", help="Ej: 15.000.000")
    pr.add_argument("--tasa", help="Ej: 1,45")
    pr.add_argument("--tipo-tasa", choices=["MV", "EA"])
    pr.add_argument("--plazo", type=int, help="Plazo en meses")
    pr.add_argument("--sin-recoger", action="store_true", help="No tomar archivos de Descargas; usar los ya ubicados en el caso")
    pr.add_argument("--copiar", action="store_true", help="Copiar en lugar de mover desde Descargas")
    pr.add_argument("--si", action="store_true", help="No pedir confirmación de los archivos")
    pr.add_argument("--enviar", action="store_true", help="Enviar al gestor al terminar si no hay errores")
    pr.add_argument("--forzar", action="store_true", help="Enviar aunque haya errores")
    pr.add_argument("--observaciones", help="Comentario del auxiliar para el gestor")
    pr.set_defaults(func=cmd_procesar)

    en = sub.add_parser("enviar", help="Enviar un caso ya procesado al gestor (Power Automate)")
    en.add_argument("caso")
    en.add_argument("--forzar", action="store_true", help="Enviar aunque haya errores")
    en.add_argument("--observaciones", help="Comentario del auxiliar para el gestor")
    en.set_defaults(func=cmd_enviar)

    pe = sub.add_parser("pendientes", help="Procesar los casos que Power Automate Desktop dejó listos (LISTO.txt)")
    pe.add_argument("--vigilar", type=int, metavar="SEGUNDOS", help="Seguir revisando la carpeta cada N segundos")
    pe.add_argument("--enviar", action="store_true", help="Enviar al gestor los casos que no tengan errores")
    pe.set_defaults(func=cmd_pendientes)
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    config = cargar_config()
    try:
        return args.func(args, config)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
