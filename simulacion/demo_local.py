"""Prueba local de dos nodos TCP sin Docker ni maquinas virtuales.

Valida el protocolo con dos sockets reales en puertos distintos de localhost.
NO equivale a dos computadores fisicos ni a una LAN Docker aislada.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import secrets
import socket
import tempfile
import threading

from src.backend.core.engine import calcular_sha256
from src.backend.network.cliente_tcp import comprobar_conexion, enviar_archivo, enviar_carpeta
from src.backend.network.p2p_socket import NodoP2PTCP


def _puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _iniciar(base: Path, token: str):
    listo = threading.Event()
    detener = threading.Event()
    nodo = NodoP2PTCP("127.0.0.1", _puerto_libre(), base, auth_token=token)
    hilo = threading.Thread(target=nodo.servir, args=(detener, listo), daemon=True)
    hilo.start()
    if not listo.wait(4):
        raise RuntimeError("No se pudo iniciar el servidor TCP local.")
    return nodo, hilo, detener


def _comparar(origen: Path, destino: Path, descripcion: str):
    if not destino.is_file():
        raise AssertionError(f"{descripcion}: no se recibió el archivo esperado.")
    a, b = calcular_sha256(origen), calcular_sha256(destino)
    if a != b:
        raise AssertionError(f"{descripcion}: SHA-256 no coincide.")
    print(f"[OK] {descripcion}: SHA-256 {a}", flush=True)


def ejecutar():
    print("PRUEBA LOCAL TCP — Dos nodos sobre 127.0.0.1 (sin Docker)", flush=True)
    print("Aviso: no es una simulación de dos equipos Linux físicos.", flush=True)
    with tempfile.TemporaryDirectory(prefix="localsync-test-") as temporal:
        raiz = Path(temporal)
        a, b = raiz / "nodo_A", raiz / "nodo_B"
        a.mkdir(); b.mkdir()
        token = secrets.token_hex(32)
        servidores = []
        try:
            nodo_a, hilo_a, detener_a = _iniciar(a, token)
            servidores.append((hilo_a, detener_a))
            nodo_b, hilo_b, detener_b = _iniciar(b, token)
            servidores.append((hilo_b, detener_b))
            print("[1/6] Dos servidores TCP iniciados en puertos distintos.", flush=True)
            assert comprobar_conexion("127.0.0.1", nodo_a.port, auth_token=token)
            assert comprobar_conexion("127.0.0.1", nodo_b.port, auth_token=token)
            print("[2/6] Conexiones autenticadas PING/ACK verificadas.", flush=True)

            origen_a = raiz / "origen_a.txt"
            origen_a.write_text("LocalSync A -> B\n", encoding="utf-8")
            assert enviar_archivo(origen_a, "127.0.0.1", nodo_b.port, auth_token=token)
            _comparar(origen_a, b / origen_a.name, "A -> B")
            print("[3/6] Archivo A hacia B verificado.", flush=True)

            origen_b = raiz / "origen_b.bin"
            origen_b.write_bytes(bytes(range(256)) * 40)
            assert enviar_archivo(origen_b, "127.0.0.1", nodo_a.port, auth_token=token)
            _comparar(origen_b, a / origen_b.name, "B -> A")
            print("[4/6] Archivo binario B hacia A verificado.", flush=True)

            carpeta = raiz / "carpeta" / "documentos"
            carpeta.mkdir(parents=True)
            archivo = carpeta / "manual.txt"
            archivo.write_text("Subcarpeta LocalSync\n", encoding="utf-8")
            correctos, fallidos = enviar_carpeta(raiz / "carpeta", "127.0.0.1",
               nodo_b.port, auth_token=token, prefijo_remoto="carpeta")
            if (correctos, fallidos) != (1, 0):
                raise AssertionError(f"Error enviando carpeta: {(correctos, fallidos)}")
            _comparar(archivo, b / "carpeta" / "documentos" / "manual.txt", "Carpeta")
            print("[5/6] Subcarpeta preservada correctamente.", flush=True)

            sha_original = calcular_sha256(b / origen_a.name)
            origen_a.write_text("LocalSync A -> B (nueva versión)\n", encoding="utf-8")
            assert enviar_archivo(origen_a, "127.0.0.1", nodo_b.port, auth_token=token)
            assert enviar_archivo(origen_a, "127.0.0.1", nodo_b.port, auth_token=token)
            if sha_original != calcular_sha256(b / origen_a.name):
                raise AssertionError("Se sobrescribió la versión original.")
            conflictos = list(b.glob("origen_a.conflict-*.txt"))
            if len(conflictos) != 1:
                raise AssertionError("Debe conservarse una única versión conflictiva.")
            _comparar(origen_a, conflictos[0], "Archivo conflictivo")
            print("[6/6] Conflictos e idempotencia verificados.", flush=True)
            print("PRUEBA LOCAL APROBADA. Todos los archivos coinciden.", flush=True)
        finally:
            for hilo, detener in servidores:
                detener.set()
            for hilo, detener in servidores:
                hilo.join(timeout=5)


if __name__ == "__main__":
    ejecutar()
