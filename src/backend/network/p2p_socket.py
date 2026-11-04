"""
Módulo Network: Definición del protocolo de mensajes P2P sobre Sockets TCP en Red LAN.
Proyecto: LocalSync - Sistemas Operativos (Grupo G1)
Integrantes Oficiales:
  - Valery Michell Herrera Roca
  - Daniel Felipe Rojas Gonzales
"""
import json
from typing import Dict, Any

DEFAULT_PORT = 9001
BUFFER_SIZE = 65536
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
        if not ruta_relativa or not ruta_relativa.strip():
            raise ValueError("La ruta relativa no puede estar vacía.")
        if len(sha256) != 64:
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
        return mensaje
