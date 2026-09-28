@echo off
REM Revisa la carpeta de casos cada 60 segundos y valida los que Power Automate Desktop
REM dejó listos (carpetas con LISTO.txt). Cierre la ventana o presione Ctrl+C para detener.
chcp 65001 >nul
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

python -m desembolsos pendientes --vigilar 60
pause
