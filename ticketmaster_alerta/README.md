# Alertas de Ticketmaster Colombia por ntfy

Vigila la página del evento y la fila virtual en **tu propio navegador** y te avisa al celular
por [ntfy](https://ntfy.sh). No compra ni hace clics por ti: tú entras a la fila y compras.

## Instalación

```bash
pip install -r requirements.txt
playwright install chromium
```

En el celular instala la app **ntfy** y suscríbete a un topic difícil de adivinar
(p. ej. `bts-pipe-8f3k2`); cualquiera que conozca el topic ve tus avisos.

```bash
python alerta.py prueba --topic bts-pipe-8f3k2     # debe llegarte una notificación
```

## Uso

**Antes de la venta** — recarga la página cada 60 s (mín. 30 s) y avisa cuando cambia el estado
(próximamente → fila → venta / agotado). Cuando se abre la fila, esa misma ventana queda dentro
y pasa sola al modo fila:

```bash
python alerta.py vigilar --topic bts-pipe-8f3k2
```

**Ya dentro de la fila** — no recarga (recargar puede costarte el puesto); lee tu posición cada
10 s, te la envía cada 5 min (o al bajar a la mitad, o bajo 100) y te avisa con prioridad
urgente cuando sales de la fila:

```bash
python alerta.py fila --topic bts-pipe-8f3k2
```

La primera vez inicia sesión en Ticketmaster en la ventana que se abre; la sesión queda
guardada en `perfil_navegador/` (no se sube al repositorio).

## Consejos para quedar bien en la fila

- En Queue-it (la fila de Ticketmaster) el puesto se **sortea entre todos los que están en la
  sala de espera antes de la hora de venta**. Entrar 1 s antes o 20 min antes da lo mismo; llegar
  tarde sí te manda al final. Entra 10–15 min antes.
- Usa **una sola pestaña y un solo dispositivo por cuenta**: varias pestañas o recargas pueden
  invalidar tu turno o marcarte como bot.
- Ten la sesión iniciada, la membresía ARMY / código de preventa y el medio de pago listos
  (datos guardados en Ticketmaster), y buena conexión por cable.
- Si los textos de la página no coinciden con los de `SENALES` / `POSICION_RE` en `alerta.py`,
  ajústalos: la consola imprime el estado detectado en cada lectura.
