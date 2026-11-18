@echo off
setlocal
cd /d "%~dp0"
title LocalSync - Centro de control LAN
echo.
echo ==============================================================
echo    LOCAlSYNC - PANEL WEB LOCAL (Windows)
echo ==============================================================
echo.
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Se requiere Python 3.12 con el lanzador py.
  echo Instala Python 3.12 desde https://www.python.org/downloads/
  pause
  exit /b 1
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
  if errorlevel 1 (
    echo El entorno virtual existente no usa Python 3.12 o esta danado.
    echo Recreando entorno virtual...
    rmdir /s /q ".venv"
    if exist ".venv" (echo ERROR eliminando entorno virtual & pause & exit /b 1)
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creando entorno virtual Python 3.12...
  py -3.12 -m venv .venv
  if errorlevel 1 (echo ERROR creando entorno virtual & pause & exit /b 1)
  if exist ".venv\.localsync-deps-ok" del /q ".venv\.localsync-deps-ok"
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
".venv\Scripts\python.exe" -m scripts.iniciar_panel
if errorlevel 1 (
  echo.
  echo El panel no pudo iniciarse. Revisa el error de Python mostrado arriba.
  echo Si indica Address already in use, entonces revisa el puerto 8080.
  pause
)
