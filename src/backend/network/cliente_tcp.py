"""Cliente TCP de LocalSync: prueba de conectividad PING/ACK."""
import argparse
import socket

from .p2p_socket import DEFAULT_PORT, NodoP2PTCP


def comprobar_conexion(host: str, puerto: int = DEFAULT_PORT, timeout: float = 3.0) -> bool:
    """Conecta con un nodo LocalSync y valida su respuesta ACK."""
    if not host or not host.strip():
        raise ValueError("Debe indicar la IP o nombre del servidor.")
    if not 1024 <= puerto <= 65535:
        raise ValueError("El puerto debe estar entre 1024 y 65535.")
    if timeout <= 0:
        raise ValueError("El tiempo de espera debe ser positivo.")

    protocolo = NodoP2PTCP(port=puerto)
    with socket.create_connection((host.strip(), puerto), timeout=timeout) as conexion:
        conexion.settimeout(timeout)
        ping = protocolo.crear_mensaje_control("PING", "", "0" * 64, 0)
        protocolo.enviar_trama(conexion, ping)
        respuesta = protocolo.decodificar_mensaje_control(protocolo.recibir_trama(conexion))
        if respuesta["operacion"] != "ACK":
            raise ValueError("El nodo remoto no respondió con ACK.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Cliente de prueba TCP LocalSync")
    parser.add_argument("--host", default="127.0.0.1", help="IP del servidor")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    try:
        comprobar_conexion(args.host, args.port, args.timeout)
    except (OSError, ValueError, ConnectionError) as error:
        print(f"[LocalSync] Error de conexión: {error}")
        return 1
    print(f"[LocalSync] Conexión exitosa con {args.host}:{args.port} (ACK recibido)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
