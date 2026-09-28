@echo off
REM Acceso directo para el auxiliar: pide el número de caso y los datos de Bizagi,
REM recoge los documentos de Descargas y muestra el resultado de la validación.
chcp 65001 >nul
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

set /p CASO=Numero de caso Bizagi:
set /p PRODUCTO=Producto (libranza / prestamo_personal):
set /p CONVENIO=Convenio (codigo o nombre):
set /p CEDULA=Cedula del cliente:
set /p MONTO=Monto (ej. 15.000.000):
set /p TASA=Tasa (ej. 1,45):
set /p TIPOTASA=Tipo de tasa (MV / EA):
set /p PLAZO=Plazo en meses:

python -m desembolsos procesar %CASO% --producto %PRODUCTO% --convenio "%CONVENIO%" --cedula %CEDULA% --monto %MONTO% --tasa %TASA% --tipo-tasa %TIPOTASA% --plazo %PLAZO%

echo.
set /p ENVIAR=Enviar al gestor para aprobacion? (s/n):
if /i "%ENVIAR%"=="s" (
    set /p OBS=Observaciones para el gestor:
    call python -m desembolsos enviar %CASO% --observaciones "%%OBS%%"
)
pause
