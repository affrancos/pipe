"""Línea de comandos para el auxiliar.

Ejemplos:
    python -m desembolsos procesar 123456 --producto libranza --convenio CONV-001 \
        --cedula 1020304050 --monto 15.000.000 --tasa 1,45 --tipo-tasa MV --plazo 60
    python -m desembolsos enviar 123456 --observaciones "Cliente con antigüedad de 5 años"
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import descargas, expediente, notificador, reporte
from .config import cargar_config
from .texto import parse_monto, parse_numero, solo_digitos
from .validador import DatosCaso

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


def cmd_procesar(args, config) -> int:
    if not args.sin_recoger and not _recoger(args, config):
        return 1
    datos = DatosCaso(
        caso=args.caso, producto=args.producto, convenio=args.convenio,
        cedula=solo_digitos(args.cedula) if args.cedula else None, nombre=args.nombre,
        monto=parse_monto(args.monto) if args.monto else None,
        tasa=parse_numero(args.tasa) if args.tasa else None, tipo_tasa=args.tipo_tasa,
        plazo_meses=args.plazo,
    )
    resultado = expediente.procesar_caso(datos, config)
    base = expediente.carpeta_caso(config, args.caso)
    reporte.resumen_caso(resultado, base / f"resumen_{args.caso}.xlsx")
    reporte.registrar_control(resultado, config["rutas"]["control_excel"])
    _imprimir(resultado)
    print(f"\nResumen: {base / f'resumen_{args.caso}.xlsx'}")
    if args.enviar:
        return _enviar(resultado, args, config)
    print(f"Revise el resultado y envíe al gestor con: python -m desembolsos enviar {args.caso}")
    return 0


def _enviar(resultado: dict, args, config) -> int:
    if resultado["estado"] == "REQUIERE_CORRECCION" and not args.forzar:
        print("\nEl caso tiene ERRORES y no se envió al gestor. Corrija o use --forzar con observaciones.")
        return 2
    solicitud = notificador.construir_solicitud(resultado, args.observaciones or "", config)
    print(notificador.enviar(solicitud, config))
    reporte.registrar_control(resultado, config["rutas"]["control_excel"], enviado=True)
    return 0


def cmd_enviar(args, config) -> int:
    return _enviar(expediente.cargar_resultado(config, args.caso), args, config)


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
