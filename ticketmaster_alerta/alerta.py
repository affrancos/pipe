"""Alertas por ntfy para un evento de Ticketmaster Colombia.

No compra ni hace clics por ti: abre un navegador normal con tu sesión, vigila la página
del evento y la fila virtual, y te avisa por ntfy cuando algo cambia o cuando es tu turno.
Tú entras a la fila y compras a mano, igual que cualquier fan.

Uso:
    python alerta.py vigilar --topic mi-topic-secreto   # antes de la venta
    python alerta.py fila --topic mi-topic-secreto      # ya dentro de la fila
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import Page, sync_playwright

EVENTO = "https://www.ticketmaster.co/event/bts-world-tour-army-membership-viernes-2-octubre"
PERFIL = Path(__file__).with_name("perfil_navegador")
MIN_INTERVALO = 30  # segundos entre recargas; más rápido solo te hace ver como bot y te bloquean

# Textos que indican el estado de la página (en minúsculas).
SENALES = {
    "fila": ["fila virtual", "sala de espera", "estás en la fila", "you are now in line", "waiting room"],
    "agotado": ["agotado", "sold out", "no hay boletas disponibles"],
    "venta": ["comprar", "buscar boletas", "find tickets", "selecciona tus boletas"],
    "proximamente": ["próximamente", "a la venta el", "la venta inicia", "on sale"],
}
POSICION_RE = re.compile(
    r"(?:número en la fila|posición en la fila|personas delante de ti|usuarios delante de ti|"
    r"your number in line|people ahead of you)\D{0,40}?([\d.,]+)",
    re.IGNORECASE,
)


def notificar(topic: str, titulo: str, mensaje: str, prioridad: str = "default",
              tags: str = "ticket", servidor: str = "https://ntfy.sh", click: str = EVENTO) -> None:
    try:
        requests.post(
            f"{servidor.rstrip('/')}/{topic}",
            data=mensaje.encode("utf-8"),
            headers={"Title": titulo, "Priority": prioridad, "Tags": tags, "Click": click},
            timeout=10,
        )
    except requests.RequestException as exc:
        print(f"[ntfy] no se pudo enviar: {exc}")


def estado(page: Page) -> str:
    url = page.url.lower()
    if "queue-it" in url or "/queue" in url:
        return "fila"
    texto = page.inner_text("body").lower()
    for nombre, frases in SENALES.items():
        if any(f in texto for f in frases):
            return nombre
    return "desconocido"


def posicion(page: Page) -> int | None:
    m = POSICION_RE.search(page.inner_text("body"))
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def abrir(p):
    # Perfil persistente: inicias sesión en Ticketmaster una vez y queda guardada.
    ctx = p.chromium.launch_persistent_context(PERFIL, headless=False, locale="es-CO")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page


def vigilar(args) -> None:
    """Recarga la página del evento y avisa cuando cambia de estado (p. ej. abre la fila)."""
    intervalo = max(args.intervalo, MIN_INTERVALO)
    with sync_playwright() as p:
        ctx, page = abrir(p)
        page.goto(args.url, wait_until="domcontentloaded")
        input("Inicia sesión en Ticketmaster en la ventana si no lo has hecho y pulsa Enter aquí... ")
        anterior = None
        while True:
            try:
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                actual = estado(page)
            except Exception as exc:  # red caída, página lenta, etc.
                print(f"error leyendo la página: {exc}")
                actual = anterior
            print(time.strftime("%H:%M:%S"), actual)
            if actual != anterior and anterior is not None:
                urgente = actual in ("fila", "venta")
                notificar(args.topic, f"Ticketmaster: {actual.upper()}",
                          f"El evento pasó de '{anterior}' a '{actual}'. ¡Entra ya!",
                          prioridad="urgent" if urgente else "default",
                          tags="rotating_light" if urgente else "ticket",
                          servidor=args.servidor, click=page.url)
            if actual == "fila":
                print("Se abrió la fila. Esta ventana ya quedó dentro: no la cierres. Pasando a modo fila.")
                seguir_fila(page, args)
                break
            anterior = actual
            time.sleep(intervalo)
        ctx.close()


def seguir_fila(page: Page, args) -> None:
    """No recarga (recargar en la fila puede costarte el puesto). Solo lee la posición."""
    ultima_pos, ultimo_aviso = None, 0.0
    notificar(args.topic, "Ticketmaster: estas en la fila",
              "Te aviso de tu posición y cuando sea tu turno.", servidor=args.servidor, click=page.url)
    while True:
        page.wait_for_timeout(10_000)
        try:
            actual, pos = estado(page), posicion(page)
        except Exception as exc:
            print(f"error leyendo la fila: {exc}")
            continue
        print(time.strftime("%H:%M:%S"), actual, pos)
        if actual != "fila":
            notificar(args.topic, "Ticketmaster: ES TU TURNO",
                      "Saliste de la fila. Ve al computador y compra ahora.",
                      prioridad="urgent", tags="rotating_light,tada",
                      servidor=args.servidor, click=page.url)
            input("Compra en la ventana del navegador. Pulsa Enter aquí para cerrar... ")
            return
        cambio_grande = pos is not None and ultima_pos is not None and pos <= ultima_pos // 2
        if pos is not None and (time.time() - ultimo_aviso > args.cada or cambio_grande or pos <= 100):
            notificar(args.topic, f"Fila: posicion {pos:,}".replace(",", "."),
                      f"Personas delante de ti: {pos:,}".replace(",", "."),
                      prioridad="high" if pos <= 100 else "low", servidor=args.servidor, click=page.url)
            ultima_pos, ultimo_aviso = pos, time.time()


def fila(args) -> None:
    with sync_playwright() as p:
        ctx, page = abrir(p)
        page.goto(args.url, wait_until="domcontentloaded")
        input("Entra a la fila en la ventana del navegador y pulsa Enter aquí... ")
        seguir_fila(page, args)
        ctx.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["vigilar", "fila", "prueba"])
    ap.add_argument("--topic", required=True, help="topic de ntfy (usa uno difícil de adivinar)")
    ap.add_argument("--servidor", default="https://ntfy.sh")
    ap.add_argument("--url", default=EVENTO)
    ap.add_argument("--intervalo", type=int, default=60, help=f"segundos entre recargas (mín. {MIN_INTERVALO})")
    ap.add_argument("--cada", type=int, default=300, help="segundos entre avisos de posición en la fila")
    args = ap.parse_args()
    if args.modo == "prueba":
        notificar(args.topic, "Prueba ntfy", "Si ves esto, las alertas funcionan.", servidor=args.servidor)
    elif args.modo == "vigilar":
        vigilar(args)
    else:
        fila(args)


if __name__ == "__main__":
    main()
