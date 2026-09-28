# Flujo de Power Automate: aprobación del desembolso (Teams + Outlook)

Este flujo recibe la solicitud que genera `python -m desembolsos enviar <caso>`, pide la
aprobación al gestor en **Teams** (aplicación Aprobaciones) y por **Outlook** (correo con botones),
y avisa al auxiliar del resultado.

```
Python (auxiliar) ──► Disparador ──► Analizar JSON ──► Iniciar y esperar una aprobación (gestor)
                                                           │
                                   ┌───────── Aprobado ────┴──── Rechazado ─────────┐
                                   ▼                                                 ▼
                     Correo al auxiliar: "Proceder con            Correo al auxiliar con los
                     el desembolso en Bizagi"                     comentarios del gestor
                     Mensaje en canal de Teams                    Registro en Excel/Lista
                     Registro en Excel/Lista
```

## 1. Elegir el disparador

| Opción | Acción en Power Automate | Licencia | Configuración en `config/config.yaml` |
|---|---|---|---|
| **A. Carpeta de OneDrive/SharePoint** (recomendada para empezar) | OneDrive para la Empresa → *Cuando se crea un archivo* + *Obtener contenido de archivo* | Estándar (incluida en Microsoft 365) | `carpeta_solicitudes: "C:/Users/<usuario>/OneDrive - Entidad/Desembolsos/Solicitudes"` |
| **B. HTTP** | *Cuando se recibe una solicitud HTTP* | **Premium** | Guardar la URL del disparador en la variable de entorno `PA_URL_APROBACION_DESEMBOLSO` |

En la opción B, la URL contiene una clave de acceso. No la pegue en el repositorio ni la comparta por correo.

## 2. Pasos del flujo

1. **Disparador** (opción A o B).
   - Opción A: agregue *Obtener contenido de archivo* con el identificador del archivo creado.
2. **Analizar JSON** (*Parse JSON*)
   - Contenido: el cuerpo de la solicitud (B) o el contenido del archivo (A).
   - Esquema: copie el contenido de [`esquema_solicitud.json`](esquema_solicitud.json).
3. **Condición opcional**: si `estado_validacion` es `REQUIERE_CORRECCION`, el auxiliar forzó el
   envío con `--forzar`. Anteponga `⚠️ CON ERRORES` al título de la aprobación.
4. **Iniciar y esperar una aprobación** (*Start and wait for an approval*)
   - Tipo: *Aprobar o rechazar: el primero en responder*
   - Título: `Desembolso caso @{body('Analizar_JSON')?['caso']} - @{body('Analizar_JSON')?['cliente']}`
   - Asignado a: `correo_gestor`
   - Detalles (admite Markdown):
     ```
     @{body('Analizar_JSON')?['resumen_markdown']}

     **Observaciones del auxiliar:** @{body('Analizar_JSON')?['observaciones_auxiliar']}
     ```
   - Vínculo del elemento: enlace a la carpeta del caso en SharePoint, si `casos` está sincronizada.
   - El gestor la recibe en **Teams → Aprobaciones** y por **Outlook**, y puede aprobar desde cualquiera de los dos.
5. **Condición**: `outputs('Iniciar_y_esperar_una_aprobación')?['body/outcome']` es igual a `Approve`
   - **Sí (aprobado)**
     - Outlook → *Enviar un correo electrónico (V2)* a `correo_auxiliar`:
       "Caso X aprobado por <respondiente>. Proceder con el desembolso en Bizagi."
     - Teams → *Publicar mensaje en un chat o canal* (canal del equipo de desembolsos).
   - **No (rechazado)**
     - Outlook → correo a `correo_auxiliar` con los comentarios del gestor
       (`responses` → `comments`) para que corrija el caso.
6. **Registro** (en ambas ramas): Excel Online → *Agregar una fila a una tabla* o SharePoint →
   *Crear elemento*, con los campos caso, resultado, gestor, fecha y comentarios. Así queda la
   trazabilidad para auditoría.

## 3. Probar

1. Configure `correo_gestor` y `correo_auxiliar` en `config/config.yaml` con su propio correo.
2. Procese un caso de prueba: `python -m desembolsos procesar 999 --sin-recoger ...`
3. Ejecute `python -m desembolsos enviar 999` y verifique que la aprobación llegue a Teams.

## 4. Siguiente fase (opcional)

Como Bizagi solo está disponible por el portal web, el paso final (registrar el desembolso en
Bizagi) sigue siendo manual. Más adelante se puede automatizar con **Power Automate Desktop**
(automatización de la interfaz web) disparado desde este mismo flujo después de la aprobación,
siempre con autorización de TI y Seguridad.
