""" Definición del protocolo de mensajes P2P sobre Sockets TCP en Red LAN. """
import json
import socket
import struct
import threading
from typing import Dict, Any

DEFAULT_PORT = 9001
BUFFER_SIZE = 65536
MAX_MESSAGE_SIZE = 1024 * 1024
OPERACIONES_VALIDAS = {"CREATE", "MODIFY", "DELETE", "PING", "ACK"}


class NodoP2PTCP:
    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> None:
        if not (1024 <= int(port) <= 65535):
            raise ValueError("El puerto TCP debe estar entre 1024 y 65535.")
        self.host: str = host
        self.port: int = int(port)
        self.transporte_tcp_activo: bool = False
        self.tls_activo: bool = False

    def crear_mensaje_control(
        self,
        operacion: str,
        ruta_relativa: str,
        sha256: str,
        tamano_bytes: int,
    ) -> bytes:
        op_upper = operacion.upper().strip()
        if op_upper not in OPERACIONES_VALIDAS:
            raise ValueError(f"Operación no válida: {operacion}")
        if operacion.upper().strip() not in {"PING", "ACK"} and (not ruta_relativa or not ruta_relativa.strip()):
            raise ValueError("La ruta relativa no puede estar vacía.")
        if len(sha256) != 64 or any(d not in "0123456789abcdefABCDEF" for d in sha256):
            raise ValueError("El hash SHA-256 debe tener exactamente 64 caracteres hexadecimales.")
        if tamano_bytes < 0:
            raise ValueError("El tamaño en bytes no puede ser negativo.")

        payload: Dict[str, Any] = {
            "protocolo": "LOCALSYNC_P2P_V1",
            "operacion": op_upper,
            "ruta_relativa": ruta_relativa.strip(),
            "hash_sha256": sha256.lower(),
            "tamano_bytes": int(tamano_bytes),
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def decodificar_mensaje_control(datos: bytes) -> Dict[str, Any]:
        mensaje = json.loads(datos.decode("utf-8"))
        campos_requeridos = {"protocolo", "operacion", "ruta_relativa", "hash_sha256", "tamano_bytes"}
        if not isinstance(mensaje, dict) or not campos_requeridos.issubset(mensaje.keys()):
            raise ValueError("El mensaje recibido no cumple la estructura LOCALSYNC_P2P_V1.")
        if mensaje["protocolo"] != "LOCALSYNC_P2P_V1":
            raise ValueError("Versión de protocolo P2P incompatible.")
        if mensaje["operacion"] not in OPERACIONES_VALIDAS:
            raise ValueError("Operación P2P no válida.")
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

    def atender_conexion(self, conexion: socket.socket) -> None:
        """Atiende un mensaje PING y devuelve ACK."""
        conexion.settimeout(5)
        mensaje = self.decodificar_mensaje_control(self.recibir_trama(conexion))
        if mensaje["operacion"] != "PING":
            raise ValueError("El servidor inicial solo admite PING.")
        self.enviar_trama(conexion, self.crear_mensaje_control("ACK", "", "0" * 64, 0))

    def servir(self, detener=None, listo=None) -> None:
        """Escucha conexiones hasta activar el evento opcional detener."""
        detener = detener if detener is not None else threading.Event()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
            servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            servidor.bind((self.host, self.port))
            servidor.listen(5)
            servidor.settimeout(0.2)
            self.transporte_tcp_activo = True
            if listo is not None:
                listo.set()
            try:
                while not detener.is_set():
                    try:
                        conexion, _ = servidor.accept()
                    except socket.timeout:
                        continue
                    with conexion:
                        try:
                            self.atender_conexion(conexion)
                        except (ConnectionError, TimeoutError, OSError, ValueError):
                            continue
            finally:
                self.transporte_tcp_activo = False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Servidor TCP LocalSync PING/ACK")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    nodo = NodoP2PTCP(args.host, args.port)
    print(f"[LocalSync] Servidor TCP escuchando en {args.host}:{args.port}", flush=True)
    try:
        nodo.servir()
    except KeyboardInterrupt:
        print("\n[LocalSync] Servidor detenido")
