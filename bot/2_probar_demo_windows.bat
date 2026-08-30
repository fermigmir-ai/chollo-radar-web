@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\chollo-radar.exe" (
  echo Primero ejecuta 1_configurar_windows.bat.
  pause
  exit /b 1
)

".venv\Scripts\chollo-radar.exe" once --config config.json
echo.
pause

