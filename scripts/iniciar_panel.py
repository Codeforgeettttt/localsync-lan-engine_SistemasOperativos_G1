"""Inicia FastAPI y abre el navegador solo cuando la GUI responde HTTP 200."""
from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

URL = "http://127.0.0.1:8080/"


def _abrir_cuando_responda():
    for _ in range(80):
        try:
            with urllib.request.urlopen(URL, timeout=0.5) as respuesta:
                if respuesta.status == 200:
                    webbrowser.open(URL, new=2)
                    print(f"[LocalSync] Panel disponible: {URL}", flush=True)
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.25)


if __name__ == "__main__":
    print("[LocalSync] Iniciando panel local. Docker Desktop es opcional para la simulación.", flush=True)
    threading.Thread(target=_abrir_cuando_responda, daemon=True).start()
    uvicorn.run("src.backend.api.routes:app", host="127.0.0.1", port=8080, log_level="info")
