@echo off
setlocal
cd /d "%~dp0"
title LocalSync - Centro de control LAN
echo.
echo ==============================================================
echo    LOCAlSYNC - PANEL WEB LOCAL (Windows)
echo ==============================================================
echo.
where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python no esta instalado o no se encontro py.exe.
  echo Instala Python 3.10+ y marca Add Python to PATH.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creando entorno virtual Python...
  py -3 -m venv .venv
  if errorlevel 1 (echo ERROR creando entorno virtual & pause & exit /b 1)
)
if not exist ".venv\.localsync-deps-ok" (
  echo [2/3] Instalando dependencias...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (echo ERROR instalando dependencias & pause & exit /b 1)
  echo installed > ".venv\.localsync-deps-ok"
)
echo [3/3] Iniciando panel local en http://127.0.0.1:8080/
echo.
echo NOTA: abre Docker Desktop antes de iniciar la simulacion virtual.
echo La GUI escucha SOLO en localhost. Para transferir a otro
echo computador, usa el receptor TCP en modo LAN con token.
echo.
start "" "http://127.0.0.1:8080/"
".venv\Scripts\python.exe" -m uvicorn src.backend.api.routes:app --host 127.0.0.1 --port 8080
if errorlevel 1 (
  echo.
  echo El panel no pudo iniciarse. Revisa si el puerto 8080 esta ocupado.
  pause
)
