# Power Automate Desktop: descargar los documentos del caso desde Bizagi

Con este flujo de escritorio, **Power Automate Desktop (PAD)** entra al portal de Bizagi, abre el
caso, descarga sus documentos en una carpeta con el nombre del caso y deja todo listo para que
Python lo valide. El auxiliar ya no tiene que descargar ni mover archivos.

¿Por qué Power Automate *Desktop* y no Power Automate en la nube? Bizagi está en un servidor de
la empresa y solo se usa por el portal web. Un flujo en la nube no puede entrar a ese portal; PAD
sí, porque corre en un equipo de la red y maneja el navegador como lo haría una persona.

## Qué debe quedar en disco

PAD crea esta estructura. Python solo procesa la carpeta cuando existe `LISTO.txt`:

```
C:\Desembolsos\casos\              ← debe ser la misma ruta de rutas.casos en config/config.yaml
└── 123456\                        ← número (o nombre) del caso en Bizagi
    ├── documentos\                ← todos los PDF / imágenes descargados del caso
    ├── caso.json                  ← datos del caso leídos del portal (opcional pero recomendado)
    └── LISTO.txt                  ← se crea AL FINAL, cuando terminaron todas las descargas
```

`caso.json` admite los valores tal como se ven en el portal. Python los interpreta:

```json
{
  "producto": "Libranza",
  "convenio": "EJEMPLO UNO S.A.S.",
  "cedula": "1.020.304.050",
  "nombre": "MARIA FERNANDA LOPEZ RUIZ",
  "monto": "$ 15.000.000",
  "tasa": "1,45",
  "tipo_tasa": "M.V.",
  "plazo_meses": "60"
}
```

Los campos que falten se toman de la solicitud de crédito. Si están presentes, Python los compara
con los documentos (monto contra pagaré, tasa contra solicitud, cédula contra todos).

## Preparación (una sola vez)

1. **Instalar Power Automate Desktop.** Viene con Windows 10 y 11; si no, se descarga de Microsoft.
   Ejecutarlo manualmente desde la consola de PAD no requiere licencia adicional.
2. **Instalar la extensión de Power Automate para Microsoft Edge** (PAD → *Herramientas* →
   *Extensiones de explorador* → *Microsoft Edge*).
3. **Carpeta de descargas exclusiva para el robot.** En Edge → *Configuración* → *Descargas*:
   - Ubicación: `C:\Desembolsos\descargas_bizagi`
   - Desactive *Preguntar dónde guardar cada archivo*.

   Así los archivos del robot no se mezclan con los demás archivos de *Descargas*.
4. **Inicio de sesión en Bizagi.**
   - Si Bizagi usa la autenticación de Windows (común en servidores internos), no hay que hacer nada.
   - Si pide usuario y clave, **no** los escriba en texto plano dentro del flujo. Use una
     variable sensible de PAD o las credenciales de Power Automate, y consúltelo con TI.

## Flujo paso a paso

Nombre sugerido: `Descargar caso Bizagi`. Variable de entrada: `NumeroCaso` (texto).

| # | Acción de PAD | Configuración |
|---|---|---|
| 1 | **Vaciar carpeta** (*Empty folder*) | `C:\Desembolsos\descargas_bizagi` |
| 2 | **Iniciar nuevo Microsoft Edge** | URL del portal de Bizagi. Variable: `Navegador` |
| 3 | **Rellenar campo de texto en la página web** | Buscador de casos del portal → `%NumeroCaso%` |
| 4 | **Hacer clic en el vínculo de la página web** | Botón *Buscar* y luego el caso encontrado |
| 5 | **Obtener detalles del elemento en la página web** (uno por dato) | Producto, convenio, cédula, nombre, monto, tasa, plazo → variables `Producto`, `Convenio`, ... |
| 6 | **Crear carpeta** | `C:\Desembolsos\casos\%NumeroCaso%\documentos` |
| 7 | **Extraer datos de la página web** | Lista de vínculos de los documentos adjuntos → `Adjuntos` |
| 8 | **Para cada** `Adjunto` en `Adjuntos` → **Hacer clic en el vínculo de la página web** | Descarga cada documento en la carpeta del robot |
| 9 | **Esperar** hasta que no queden descargas en curso | Bucle: *Obtener archivos en la carpeta* con filtro `*.crdownload`; si hay alguno, **Esperar** 2 s y repetir |
| 10 | **Mover archivos** | De `C:\Desembolsos\descargas_bizagi\*` a `C:\Desembolsos\casos\%NumeroCaso%\documentos` |
| 11 | **Establecer variable** `DatosCaso` (objeto personalizado) + **Convertir objeto personalizado en JSON** | `{'producto': Producto, 'convenio': Convenio, 'cedula': Cedula, 'nombre': Nombre, 'monto': Monto, 'tasa': Tasa, 'tipo_tasa': TipoTasa, 'plazo_meses': Plazo}` |
| 12 | **Escribir texto en archivo** | `...\casos\%NumeroCaso%\caso.json`, codificación UTF-8, contenido = JSON del paso 11 |
| 13 | **Escribir texto en archivo** | `...\casos\%NumeroCaso%\LISTO.txt` (contenido: la fecha). **Siempre al final** |
| 14 | **Cerrar el explorador web** | `Navegador` |

Recomendaciones:
- **Elementos de la interfaz:** grabe los pasos 3 a 8 con la grabadora de PAD sobre un caso real.
  Después, en los selectores, reemplace el número de caso fijo por `%NumeroCaso%`.
- **Datos del caso:** use JSON (paso 11), no concatene texto, para que un nombre con comillas no
  dañe el archivo.
- **Errores:** envuelva los pasos 3 a 13 en un bloque **En caso de error**. Si algo falla, no se
  debe crear `LISTO.txt`; así Python nunca procesa un caso a medio descargar.

### Procesar varios casos de una vez

En lugar de pedir `NumeroCaso`, el flujo puede abrir la **bandeja de entrada** de Bizagi, extraer
con **Extraer datos de la página web** la tabla de casos en la actividad de desembolso y repetir
los pasos 3 a 13 con **Para cada** caso. Omita los casos que ya tengan carpeta con `LISTO.txt`
(acción **Si existe el archivo**).

## Cómo arranca Python

Elija una de estas dos opciones:

- **A. Desde el mismo flujo de PAD:** al final agregue **Ejecutar aplicación** con
  - Ruta: `C:\Desembolsos\pipe\.venv\Scripts\python.exe`
  - Argumentos: `-m desembolsos pendientes`
  - Carpeta de trabajo: `C:\Desembolsos\pipe`
  - *Esperar a que se complete la aplicación*.
- **B. Vigilante permanente:** deje abierto `scripts\vigilar_casos.bat`. Revisa la carpeta de
  casos cada minuto y procesa los que tengan `LISTO.txt`.

En ambos casos, cada caso procesado queda con su `resultado.json` y su resumen en Excel, y se
registra en el libro de control. Un caso que no se pudo procesar queda con `ERROR_PROCESO.txt`.
Para reprocesar un caso, vuelva a crear su `LISTO.txt`.

Para que los casos sin errores se envíen al gestor de forma automática, agregue `--enviar`
(`-m desembolsos pendientes --enviar`). Sin esa opción, el auxiliar revisa el resumen y envía con
`python -m desembolsos enviar <caso>`.

## Ejecución programada o desde la nube (opcional)

Si el flujo de escritorio se inicia desde un flujo de Power Automate en la nube (por ejemplo, cada
hora o al llegar un correo), se necesita una licencia adicional:
- **Power Automate Premium**, para que corra con el usuario conectado (*attended*).
- **Power Automate Process**, para que corra solo en un servidor o máquina virtual (*unattended*).

Consulte con TI antes de configurarlo.
