@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo No se ha encontrado Python. Instala Python 3.11 o superior y vuelve a intentarlo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto :error

if not exist "config.json" copy /Y "config.example.json" "config.json" >nul
if not exist ".env" copy /Y ".env.example" ".env" >nul

".venv\Scripts\chollo-radar.exe" check-config --config config.json
if errorlevel 1 goto :error

echo.
echo Configuracion terminada. Ya puedes ejecutar 2_probar_demo_windows.bat.
pause
exit /b 0

:error
echo.
echo La configuracion no se pudo completar. Revisa el mensaje anterior.
pause
exit /b 1

