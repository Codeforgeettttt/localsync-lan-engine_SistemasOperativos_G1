#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "LocalSync — Iniciando panel web local..."
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
if [ ! -f .venv/.localsync-deps-ok ]; then
  python -m pip install -r requirements.txt
  touch .venv/.localsync-deps-ok
fi
echo "Panel: http://127.0.0.1:8080/"
echo "Abre Docker Engine antes de usar el laboratorio virtual."
echo "Ctrl+C para detener el panel."
python -m uvicorn src.backend.api.routes:app --host 127.0.0.1 --port 8080
