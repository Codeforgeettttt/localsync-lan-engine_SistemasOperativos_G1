"""Servidor P2P TCP de LocalSync: recepción verificable y autenticación opcional.

Autenticación por reto HMAC-SHA256. Para confidencialidad use TLS: sin TLS el
contenido de los archivos viaja en texto claro por la LAN.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import struct
import threading
from typing import Any, Dict

DEFAULT_PORT = 9001
BUFFER_SIZE = 65536
MAX_MESSAGE_SIZE = 1024 * 1024
OPERACIONES_VALIDAS = {
    "CREATE", "MODIFY", "DELETE", "PING", "ACK", "ERROR",
    "AUTH_INIT", "AUTH_CHALLENGE", "AUTH_RESPONSE",
}


def _es_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class NodoP2PTCP:
    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                 carpeta_autorizada=None, *, auth_token: str | None = None,
                 insecure_lan: bool = False, tls_cert: str | None = None,
                 tls_key: str | None = None, on_conflict: str = "keep-both",
                 max_workers: int = 8) -> None:
        if not (1024 <= int(port) <= 65535):
            raise ValueError("El puerto TCP debe estar entre 1024 y 65535.")
        if (tls_cert is None) != (tls_key is None):
            raise ValueError("TLS requiere ambos archivos: certificado y clave privada.")
        if max_workers < 1 or max_workers > 64:
            raise ValueError("max_workers debe estar entre 1 y 64.")
        if on_conflict not in {"keep-both", "reject", "overwrite"}:
            raise ValueError("Política de conflictos inválida.")
        if auth_token is not None and len(auth_token) < 16:
            raise ValueError("El token compartido debe tener al menos 16 caracteres.")
        if not _es_loopback(host) and not auth_token and not insecure_lan:
            raise ValueError("Para aceptar conexiones LAN configure LOCALSYNC_AUTH_TOKEN o --insecure-lan (no recomendado).")
        self.host = host
        self.port = int(port)
        self.carpeta_autorizada = carpeta_autorizada
        self.auth_token = auth_token
        self.insecure_lan = insecure_lan
        self.tls_cert = tls_cert
        self.tls_key = tls_key
        self.on_conflict = on_conflict
        self.max_workers = max_workers
        self.transporte_tcp_activo = False
        self.tls_activo = bool(tls_cert)

    def crear_mensaje_control(self, operacion: str, ruta_relativa: str,
                              sha256: str, tamano_bytes: int) -> bytes:
        op = operacion.upper().strip()
        if op not in OPERACIONES_VALIDAS:
            raise ValueError(f"Operación no válida: {operacion}")
        if op in {"CREATE", "MODIFY", "DELETE"} and not ruta_relativa.strip():
            raise ValueError("La ruta relativa no puede estar vacía.")
        if not isinstance(sha256, str) or len(sha256) != 64 or any(x not in "0123456789abcdefABCDEF" for x in sha256):
            raise ValueError("El SHA-256 debe tener exactamente 64 caracteres hexadecimales.")
        if not isinstance(tamano_bytes, int) or isinstance(tamano_bytes, bool) or tamano_bytes < 0:
            raise ValueError("El tamaño en bytes debe ser un entero no negativo.")
        payload: Dict[str, Any] = {
            "protocolo": "LOCALSYNC_P2P_V1",
            "operacion": op,
            "ruta_relativa": ruta_relativa,
            "hash_sha256": sha256.lower(),
            "tamano_bytes": tamano_bytes,
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def decodificar_mensaje_control(datos: bytes) -> Dict[str, Any]:
        try:
            mensaje = json.loads(datos.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("Cabecera de control no válida.") from exc
        campos = {"protocolo", "operacion", "ruta_relativa", "hash_sha256", "tamano_bytes"}
        if not isinstance(mensaje, dict) or not campos.issubset(mensaje):
            raise ValueError("Estructura LOCALSYNC_P2P_V1 inválida.")
        if mensaje["protocolo"] != "LOCALSYNC_P2P_V1":
            raise ValueError("Versión de protocolo incompatible.")
        if mensaje["operacion"] not in OPERACIONES_VALIDAS:
            raise ValueError("Operación P2P no válida.")
        if not isinstance(mensaje["ruta_relativa"], str):
            raise ValueError("La ruta relativa debe ser un texto.")
        if not isinstance(mensaje["hash_sha256"], str) or len(mensaje["hash_sha256"]) != 64:
            raise ValueError("Hash inválido.")
        if not isinstance(mensaje["tamano_bytes"], int) or isinstance(mensaje["tamano_bytes"], bool):
            raise ValueError("Tamaño inválido.")
        return mensaje

    @staticmethod
    def _recibir_exacto(conexion: socket.socket, cantidad: int) -> bytes:
        partes = bytearray()
        while len(partes) < cantidad:
            bloque = conexion.recv(min(BUFFER_SIZE, cantidad - len(partes)))
            if not bloque:
                raise ConnectionError("Conexión cerrada antes de completar el mensaje.")
            partes.extend(bloque)
        return bytes(partes)

    @classmethod
    def recibir_trama(cls, conexion: socket.socket) -> bytes:
        longitud = struct.unpack("!I", cls._recibir_exacto(conexion, 4))[0]
        if not 0 < longitud <= MAX_MESSAGE_SIZE:
            raise ValueError("Longitud de mensaje TCP inválida.")
        return cls._recibir_exacto(conexion, longitud)

    @staticmethod
    def enviar_trama(conexion: socket.socket, datos: bytes) -> None:
        if not 0 < len(datos) <= MAX_MESSAGE_SIZE:
            raise ValueError("Longitud de mensaje TCP inválida.")
        conexion.sendall(struct.pack("!I", len(datos)) + datos)

    def _autenticar(self, conexion: socket.socket) -> None:
        if not self.auth_token:
            return
        inicio = self.decodificar_mensaje_control(self.recibir_trama(conexion))
        if inicio["operacion"] != "AUTH_INIT":
            raise PermissionError("El nodo requiere autenticación.")
        nonce = secrets.token_hex(32)
        self.enviar_trama(conexion, self.crear_mensaje_control("AUTH_CHALLENGE", nonce, "0" * 64, 0))
        respuesta = self.decodificar_mensaje_control(self.recibir_trama(conexion))
        esperado = hmac.new(self.auth_token.encode("utf-8"), bytes.fromhex(nonce), hashlib.sha256).hexdigest()
        if respuesta["operacion"] != "AUTH_RESPONSE" or not hmac.compare_digest(respuesta["hash_sha256"], esperado):
            raise PermissionError("Autenticación P2P fallida.")
        self.enviar_trama(conexion, self.crear_mensaje_control("ACK", "autenticado", "0" * 64, 0))

    def atender_conexion(self, conexion: socket.socket) -> None:
        """Autentica y atiende una solicitud PING o CREATE por conexión."""
        conexion.settimeout(15)
        self._autenticar(conexion)
        mensaje = self.decodificar_mensaje_control(self.recibir_trama(conexion))
        if mensaje["operacion"] == "PING":
            self.enviar_trama(conexion, self.crear_mensaje_control("ACK", "pong", "0" * 64, 0))
        elif mensaje["operacion"] == "CREATE" and self.carpeta_autorizada is not None:
            from .transferencia import recibir_archivo
            destino = recibir_archivo(conexion, mensaje, self.carpeta_autorizada,
                                     on_conflict=self.on_conflict)
            self.enviar_trama(conexion, self.crear_mensaje_control(
                "ACK", str(destino.relative_to(Path(self.carpeta_autorizada).resolve()).as_posix()),
                mensaje["hash_sha256"], mensaje["tamano_bytes"],
            ))
            print(f"[LocalSync][RECEPCION_OK] archivo={destino.name!r} "
                  f"bytes={mensaje['tamano_bytes']} sha256={mensaje['hash_sha256']}", flush=True)
        else:
            raise ValueError("Operación no admitida o recepción deshabilitada.")

    def _manejar_cliente(self, conexion: socket.socket, tls_context) -> None:
        with conexion:
            try:
                conexion.settimeout(15)
                if tls_context is not None:
                    with tls_context.wrap_socket(conexion, server_side=True) as segura:
                        self._procesar(segura)
                else:
                    self._procesar(conexion)
            except (OSError, ValueError, PermissionError, ConnectionError, ssl.SSLError) as exc:
                print(f"[LocalSync][CONEXION_RECHAZADA] {type(exc).__name__}: {exc}", flush=True)

    def _procesar(self, conexion) -> None:
        try:
            self.atender_conexion(conexion)
        except (OSError, ValueError, PermissionError, ConnectionError, FileExistsError) as exc:
            # Los errores de validación no deben derribar el servidor.
            try:
                detalle = str(exc)[:400]
                self.enviar_trama(conexion, self.crear_mensaje_control("ERROR", detalle, "0" * 64, 0))
            except OSError:
                pass
            raise

    def servir(self, detener=None, listo=None) -> None:
        """Atiende varios clientes simultáneos; se detiene limpiamente por evento."""
        detener = detener if detener is not None else threading.Event()
        tls_context = None
        if self.tls_cert:
            tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
            tls_context.load_cert_chain(self.tls_cert, self.tls_key)
        if self.carpeta_autorizada is not None:
            Path(self.carpeta_autorizada).mkdir(parents=True, exist_ok=True)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
            servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            servidor.bind((self.host, self.port))
            servidor.listen(32)
            servidor.settimeout(0.2)
            self.transporte_tcp_activo = True
            if listo is not None:
                listo.set()
            print(f"[LocalSync][SERVIDOR_LISTO] {self.host}:{self.port} "
                  f"TLS={'SI' if tls_context else 'NO'} AUTH={'SI' if self.auth_token else 'NO'}", flush=True)
            cupos = threading.BoundedSemaphore(self.max_workers * 2)
            try:
                with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="localsync-p2p") as pool:
                    while not detener.is_set():
                        try:
                            conexion, _ = servidor.accept()
                        except socket.timeout:
                            continue
                        if not cupos.acquire(blocking=False):
                            conexion.close()
                            continue
                        try:
                            futuro = pool.submit(self._manejar_cliente, conexion, tls_context)
                            futuro.add_done_callback(lambda _: cupos.release())
                        except Exception:
                            cupos.release()
                            conexion.close()
                            raise
            finally:
                self.transporte_tcp_activo = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Servidor receptor TCP LocalSync")
    parser.add_argument("--host", default="127.0.0.1", help="127.0.0.1 (local) o 0.0.0.0 (LAN)")
    parser.add_argument("--port", type=int, default=int(os.getenv("LOCALSYNC_P2P_PORT", DEFAULT_PORT)))
    parser.add_argument("--directory", default=None, help="Carpeta receptora autorizada")
    parser.add_argument("--auth-token", default=os.getenv("LOCALSYNC_AUTH_TOKEN"),
                        help="Token compartido (preferir variable LOCALSYNC_AUTH_TOKEN)")
    parser.add_argument("--insecure-lan", action="store_true", help="Permite LAN sin autenticación (solo laboratorio aislado)")
    parser.add_argument("--tls-cert", help="Certificado PEM del servidor")
    parser.add_argument("--tls-key", help="Clave PEM del servidor")
    parser.add_argument("--on-conflict", choices=["keep-both", "reject", "overwrite"], default="keep-both")
    args = parser.parse_args()
    try:
        nodo = NodoP2PTCP(args.host, args.port, args.directory, auth_token=args.auth_token,
                          insecure_lan=args.insecure_lan, tls_cert=args.tls_cert,
                          tls_key=args.tls_key, on_conflict=args.on_conflict)
        nodo.servir()
    except (OSError, ValueError) as exc:
        print(f"[LocalSync][ERROR] {exc}", flush=True)
        return 1
    except KeyboardInterrupt:
        print("\n[LocalSync] Servidor detenido", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
