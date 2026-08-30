@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\chollo-radar.exe" (
  echo Primero ejecuta 1_configurar_windows.bat.
  pause
  exit /b 1
)

echo Chollo Radar Bot se mantendra activo mientras esta ventana siga abierta.
echo Pulsa Ctrl+C para detenerlo.
echo.
".venv\Scripts\chollo-radar.exe" run --config config.json
pause

