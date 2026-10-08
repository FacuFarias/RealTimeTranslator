@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Comprobando interfaz y modelos locales. No se captura audio personal.
Traductor.exe main.py --self-test --sample "diagnostics\sample.wav" --report "autoprueba.json"
if errorlevel 1 (
  echo La autoprueba encontro un problema. Revisa autoprueba.json.
) else (
  echo Autoprueba completada. Revisa autoprueba.json para los resultados.
)
pause
