# Automatización de desembolsos: préstamo personal y libranza

Herramienta en Python que hace la validación documental que hoy hace el auxiliar a mano:
documentación, tasa, monto, convenio y condiciones. Después envía el caso al gestor para que
lo apruebe en **Teams / Outlook** mediante **Power Automate**.

## Proceso

| # | Hoy (manual) | Con la automatización |
|---|---|---|
| 1 | El auxiliar descarga los documentos del caso desde Bizagi | Igual: los documentos quedan en *Descargas* |
| 2 | Abre cada PDF o imagen y lo revisa | `procesar` los mueve al expediente del caso y los lee (OCR para escaneados e imágenes) |
| 3 | Verifica documentación, tasa, monto, convenio y condiciones | Se validan las reglas de `config/` y se genera un resumen en Excel con OK / ALERTA / ERROR |
| 4 | Envía al gestor | `enviar` crea la aprobación en Teams + Outlook (Power Automate) |
| 5 | El gestor revisa y aprueba | El gestor aprueba o rechaza desde Teams u Outlook. El auxiliar recibe la respuesta por correo |
| 6 | Desembolso en Bizagi | Manual (fase 2: Power Automate Desktop) |

Bizagi solo se usa a través de su portal web. La herramienta **no** entra a Bizagi: trabaja con
los archivos que el auxiliar ya descarga.

## Qué valida

| Regla | Detalle | Configuración |
|---|---|---|
| Documentación | Documentos requeridos por producto; avisa de los que no se pudieron clasificar | `productos.*.documentos_requeridos` |
| Identidad | La misma cédula en todos los documentos y en el caso | — |
| Vigencia | Certificado laboral ≤ 30 días, desprendible ≤ 60 días | `reglas.vigencia_dias` |
| Convenio | Existe y permite el producto | `config/convenios.yaml` |
| Monto | Dentro del rango del convenio; igual en Bizagi, solicitud y pagaré | `monto_min/max`, `tolerancia_monto` |
| Tasa | ≤ tasa del convenio y ≤ usura; convierte entre M.V. y E.A. | `tasa_max`, `reglas.tasa_usura_ea` |
| Plazo | ≤ plazo máximo del convenio | `plazo_max_meses` |
| Capacidad de pago | (deducciones + cuota estimada) ≤ 50% del devengado en libranza (Ley 1527 de 2012); porcentaje configurable en préstamo personal | `productos.*.capacidad_max_pct` |

Resultado: `LISTO_PARA_APROBACION`, `REVISAR_ALERTAS` o `REQUIERE_CORRECCION`. Un caso con
errores no se envía al gestor, salvo que el auxiliar use `--forzar` y deje observaciones.

## Instalación (Windows, en el equipo del auxiliar)

1. **Python 3.10 o superior**: <https://www.python.org/downloads/> (marque *Add python.exe to PATH*).
2. **Tesseract OCR** (lee PDF escaneados e imágenes): instale el paquete de UB Mannheim
   (<https://github.com/UB-Mannheim/tesseract/wiki>) y marque el idioma **Spanish** durante la
   instalación. La ruta por defecto ya está en `config/config.yaml` (`ocr.tesseract_cmd`).
3. Desde una terminal en la carpeta del proyecto:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Ajuste `config/config.yaml` (correos, tasa de usura del mes, carpeta del expediente) y
   reemplace los convenios de ejemplo de `config/convenios.yaml` por los reales.

Si su equipo no permite instalar programas, pida a TI que instale Python y Tesseract.

## Uso

Descargue de Bizagi **solo** los documentos del caso y ejecute:

```bat
python -m desembolsos procesar 123456 --producto libranza --convenio CONV-001 ^
    --cedula 1020304050 --monto 15.000.000 --tasa 1,45 --tipo-tasa MV --plazo 60
```

- Antes de mover los archivos de *Descargas*, la herramienta muestra la lista y pide confirmación.
- Los datos que no escriba (convenio, monto, tasa...) se toman de la solicitud de crédito, y el
  resumen indica de dónde salió cada dato. Si los escribe tal como aparecen en Bizagi, la
  herramienta los compara con los documentos.
- Revise el resultado en `casos/123456/resumen_123456.xlsx` y envíe al gestor:

```bat
python -m desembolsos enviar 123456 --observaciones "Cliente con 5 años de antigüedad"
```

`scripts\procesar_caso.bat` hace lo mismo preguntando dato por dato (útil como acceso directo
en el escritorio). Con `-v` se ve el detalle de cada documento.

### Qué queda en cada caso

```
casos/123456/
├── documentos/              # los archivos traídos de Descargas
├── textos/                  # texto leído de cada documento (auditoría y ajuste de reglas)
├── resultado.json           # resultado completo de la validación
└── resumen_123456.xlsx      # hojas Resumen, Hallazgos y Documentos
casos/control_desembolsos.xlsx   # una fila por caso: estado, errores, si se envió al gestor
```

## Power Automate (Teams + Outlook)

Siga la guía [`power_automate/GUIA_FLUJO.md`](power_automate/GUIA_FLUJO.md). Hay dos formas de
conectar la herramienta con el flujo:

- **Carpeta de OneDrive/SharePoint** (conector estándar): configure `power_automate.carpeta_solicitudes`.
- **HTTP** (conector premium): guarde la URL del flujo en la variable de entorno
  `PA_URL_APROBACION_DESEMBOLSO`.

## Ajuste con documentos reales

Las palabras clave (`desembolsos/clasificador.py`) y las expresiones regulares
(`desembolsos/extractores.py`) se probaron con formatos típicos. Para adaptarlas a los formatos
de la entidad:

1. Procese algunos casos reales y revise `casos/<caso>/textos/*.txt` para ver qué leyó el OCR.
2. Agregue palabras clave o etiquetas (p. ej. cómo llama su pagaduría al "total devengado").
3. Agregue un caso de prueba en `tests/` con un texto de ejemplo **anonimizado** y ejecute `pytest`.

## Seguridad y datos personales

- Los documentos, textos y reportes de clientes quedan en `casos/` y **nunca** se suben a git
  (ver `.gitignore`).
- En Teams y Outlook solo se muestran los últimos 4 dígitos de la cédula.
- Los datos personales se tratan bajo la Ley 1581 de 2012. Valide con Seguridad de la Información
  dónde se ubica la carpeta `casos` y quién tiene acceso a ella.

## Desarrollo

```bash
pip install -r requirements.txt
pytest            # la prueba de OCR se omite si Tesseract no está instalado
```
