"""Cliente TCP LocalSync: PING, transferencia individual y envío de carpetas."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import socket
import ssl
import time

from src.backend.core.engine import calcular_sha256
from .p2p_socket import DEFAULT_PORT, NodoP2PTCP, _es_loopback
from .transferencia import MAX_FILE_SIZE


def _validar_destino(host: str, puerto: int, timeout: float) -> None:
    if not host or not host.strip():
        raise ValueError("Debe indicar la IP o el nombre del receptor.")
    if not isinstance(puerto, int) or not 1024 <= puerto <= 65535:
        raise ValueError("El puerto debe estar entre 1024 y 65535.")
    if timeout <= 0:
        raise ValueError("El tiempo de espera debe ser positivo.")


@contextmanager
def _conectar(host: str, puerto: int, timeout: float, tls_ca: str | None = None,
              tls_server_name: str | None = None):
    conexion = socket.create_connection((host.strip(), puerto), timeout=timeout)
    with conexion:
        conexion.settimeout(timeout)
        if tls_ca:
            contexto = ssl.create_default_context(cafile=tls_ca)
            contexto.minimum_version = ssl.TLSVersion.TLSv1_2
            with contexto.wrap_socket(conexion, server_hostname=tls_server_name or host.strip()) as segura:
                yield segura
        else:
            yield conexion


def _autenticar(conexion, protocolo: NodoP2PTCP, token: str | None) -> None:
    if not token:
        return
    protocolo.enviar_trama(conexion, protocolo.crear_mensaje_control("AUTH_INIT", "", "0" * 64, 0))
    reto = protocolo.decodificar_mensaje_control(protocolo.recibir_trama(conexion))
    if reto["operacion"] != "AUTH_CHALLENGE":
        raise PermissionError("El receptor no admite o rechazó la autenticación solicitada.")
    try:
        nonce = bytes.fromhex(reto["ruta_relativa"])
    except ValueError as exc:
        raise ValueError("El reto de autenticación es inválido.") from exc
    if len(nonce) != 32:
        raise ValueError("El reto de autenticación no tiene longitud válida.")
    firma = hmac.new(token.encode("utf-8"), nonce, hashlib.sha256).hexdigest()
    protocolo.enviar_trama(conexion, protocolo.crear_mensaje_control("AUTH_RESPONSE", "", firma, 0))
    respuesta = protocolo.decodificar_mensaje_control(protocolo.recibir_trama(conexion))
    if respuesta["operacion"] != "ACK":
        raise PermissionError("El receptor rechazó la autenticación.")


def _validar_ack(protocolo: NodoP2PTCP, conexion) -> dict:
    respuesta = protocolo.decodificar_mensaje_control(protocolo.recibir_trama(conexion))
    if respuesta["operacion"] == "ERROR":
        raise ValueError(f"El receptor rechazó la operación: {respuesta['ruta_relativa']}")
    if respuesta["operacion"] != "ACK":
        raise ValueError("El receptor no devolvió confirmación ACK.")
    return respuesta


def comprobar_conexion(host: str, puerto: int = DEFAULT_PORT, timeout: float = 3.0,
                       *, auth_token: str | None = None, tls_ca: str | None = None,
                       tls_server_name: str | None = None) -> bool:
    """Comprueba conectividad de extremo a extremo con un nodo autenticado o local."""
    _validar_destino(host, puerto, timeout)
    protocolo = NodoP2PTCP(host="127.0.0.1", port=puerto)
    with _conectar(host, puerto, timeout, tls_ca, tls_server_name) as conexion:
        _autenticar(conexion, protocolo, auth_token if auth_token is not None else os.getenv("LOCALSYNC_AUTH_TOKEN"))
        protocolo.enviar_trama(conexion, protocolo.crear_mensaje_control("PING", "", "0" * 64, 0))
        _validar_ack(protocolo, conexion)
    return True


def enviar_archivo(ruta_archivo: str | Path, host: str, puerto: int = DEFAULT_PORT,
                   timeout: float = 5.0, *, auth_token: str | None = None,
                   tls_ca: str | None = None, tls_server_name: str | None = None,
                   ruta_remota: str | None = None, reintentos: int = 0) -> bool:
    """Envía un archivo por bloques, autentica opcionalmente y valida el ACK.

    Los reintentos repiten el archivo completo. El receptor evita duplicados
    idénticos y guarda versiones conflictivas cuando los contenidos difieren.
    """
    _validar_destino(host, puerto, timeout)
    if not isinstance(reintentos, int) or not 0 <= reintentos <= 10:
        raise ValueError("reintentos debe estar entre 0 y 10.")
    ruta = Path(ruta_archivo)
    if ruta.is_symlink() or not ruta.is_file():
        raise FileNotFoundError(f"No es un archivo regular permitido: {ruta}")
    tamano = ruta.stat().st_size
    if tamano > MAX_FILE_SIZE:
        raise ValueError("El archivo supera el límite de 100 MiB.")
    nombre_remoto = ruta_remota if ruta_remota is not None else ruta.name
    protocolo = NodoP2PTCP(host="127.0.0.1", port=puerto)
    sha = calcular_sha256(ruta)
    cabecera = protocolo.crear_mensaje_control("CREATE", nombre_remoto, sha, tamano)

    for intento in range(reintentos + 1):
        try:
            with _conectar(host, puerto, timeout, tls_ca, tls_server_name) as conexion:
                _autenticar(conexion, protocolo, auth_token if auth_token is not None else os.getenv("LOCALSYNC_AUTH_TOKEN"))
                protocolo.enviar_trama(conexion, cabecera)
                with ruta.open("rb") as origen:
                    while bloque := origen.read(65536):
                        conexion.sendall(bloque)
                respuesta = _validar_ack(protocolo, conexion)
                if respuesta["hash_sha256"] not in {sha, "0" * 64}:
                    raise ValueError("ACK con SHA-256 diferente al del archivo enviado.")
                print(f"[LocalSync][ENVIO_OK] archivo={ruta.name!r} destino={respuesta['ruta_relativa']!r} "
                      f"bytes={tamano} sha256={sha}", flush=True)
                return True
        except (OSError, ConnectionError, TimeoutError) as exc:
            if intento >= reintentos:
                raise
            print(f"[LocalSync][REINTENTO] {intento + 1}/{reintentos}: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(min(0.5 * (2 ** intento), 3.0))
    return False


def enviar_carpeta(directorio: str | Path, host: str, puerto: int = DEFAULT_PORT,
                   *, timeout: float = 15.0, auth_token: str | None = None,
                   tls_ca: str | None = None, tls_server_name: str | None = None,
                   prefijo_remoto: str = "", reintentos: int = 1) -> tuple[int, int]:
    """Envía recursivamente archivos normales preservando rutas relativas.

    No propaga eliminaciones ni observa cambios en tiempo real.
    """
    base = Path(directorio)
    if not base.is_dir() or base.is_symlink():
        raise ValueError("Debe indicar una carpeta regular existente.")
    correctos = errores = 0
    for ruta in sorted(base.rglob("*")):
        if ruta.is_symlink() or not ruta.is_file():
            continue
        relativa = ruta.relative_to(base).as_posix()
        remota = f"{prefijo_remoto.strip('/')}/{relativa}" if prefijo_remoto else relativa
        try:
            enviar_archivo(ruta, host, puerto, timeout, auth_token=auth_token,
                           tls_ca=tls_ca, tls_server_name=tls_server_name,
                           ruta_remota=remota, reintentos=reintentos)
            correctos += 1
        except (OSError, ValueError, ConnectionError, PermissionError) as exc:
            errores += 1
            print(f"[LocalSync][ENVIO_ERROR] archivo={relativa!r} error={exc}", flush=True)
    return correctos, errores


def main() -> int:
    parser = argparse.ArgumentParser(description="Cliente TCP LocalSync: PING, archivo o carpeta")
    parser.add_argument("--host", default="127.0.0.1", help="IP o hostname del receptor")
    parser.add_argument("--port", type=int, default=int(os.getenv("LOCALSYNC_P2P_PORT", DEFAULT_PORT)))
    parser.add_argument("--timeout", type=float, default=15.0)
    origen = parser.add_mutually_exclusive_group()
    origen.add_argument("--file", help="Ruta local al archivo")
    origen.add_argument("--directory", help="Carpeta que se enviará recursivamente")
    parser.add_argument("--remote-path", help="Ruta relativa en el receptor (solo --file)")
    parser.add_argument("--remote-prefix", default="", help="Subcarpeta en el receptor (solo --directory)")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--auth-token", default=os.getenv("LOCALSYNC_AUTH_TOKEN"),
                        help="Preferir variable de entorno LOCALSYNC_AUTH_TOKEN")
    parser.add_argument("--tls-ca", help="Certificado PEM confiable del servidor")
    parser.add_argument("--tls-server-name", help="Nombre/IP presente en el certificado TLS")
    parser.add_argument("--insecure-lan", action="store_true", help="Permitir conexión sin autenticación (NO recomendado)")
    args = parser.parse_args()
    if args.remote_path and not args.file:
        parser.error("--remote-path solo se usa con --file")
    if args.remote_prefix and not args.directory:
        parser.error("--remote-prefix solo se usa con --directory")
    if not _es_loopback(args.host) and not args.auth_token and not args.insecure_lan:
        parser.error("Para conexiones LAN proporcione LOCALSYNC_AUTH_TOKEN (o --insecure-lan en red aislada)")
    try:
        if args.directory:
            bien, mal = enviar_carpeta(args.directory, args.host, args.port, timeout=args.timeout,
                                      auth_token=args.auth_token, tls_ca=args.tls_ca,
                                      tls_server_name=args.tls_server_name,
                                      prefijo_remoto=args.remote_prefix, reintentos=args.retries)
            print(f"[LocalSync][RESUMEN] enviados={bien} errores={mal}")
            return 1 if mal else 0
        if args.file:
            enviar_archivo(args.file, args.host, args.port, timeout=args.timeout,
                           auth_token=args.auth_token, tls_ca=args.tls_ca,
                           tls_server_name=args.tls_server_name,
                           ruta_remota=args.remote_path, reintentos=args.retries)
            print(f"[LocalSync] ACK recibido: archivo enviado {args.file}")
        else:
            comprobar_conexion(args.host, args.port, timeout=args.timeout,
                               auth_token=args.auth_token, tls_ca=args.tls_ca,
                               tls_server_name=args.tls_server_name)
            print(f"[LocalSync] Conexión exitosa con {args.host}:{args.port} (ACK recibido)")
    except (OSError, ValueError, ConnectionError, PermissionError, ssl.SSLError) as error:
        print(f"[LocalSync][ERROR] {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
