"""Transferencia TCP de archivos para LocalSync (prototipo LAN sin autenticación)."""
import hashlib
import os
from pathlib import Path
import tempfile

from src.backend.core.engine import validar_ruta_segura
from .p2p_socket import BUFFER_SIZE, NodoP2PTCP

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MiB por transferencia


def recibir_archivo(conexion, mensaje: dict, carpeta_autorizada: str | Path) -> Path:
    """Recibe bytes exactos, verifica SHA-256 y publica el archivo atómicamente."""
    base = Path(carpeta_autorizada).resolve()
    ruta_relativa = mensaje["ruta_relativa"]
    tamano = mensaje["tamano_bytes"]
    hash_esperado = mensaje["hash_sha256"]
    if not isinstance(tamano, int) or isinstance(tamano, bool) or not 0 <= tamano <= MAX_FILE_SIZE:
        raise ValueError("Tamaño de archivo inválido o superior al límite de 100 MiB.")
    if not isinstance(ruta_relativa, str) or not validar_ruta_segura(base, ruta_relativa):
        raise ValueError("Ruta de archivo no autorizada.")
    if not isinstance(hash_esperado, str) or len(hash_esperado) != 64 or any(
        c not in "0123456789abcdefABCDEF" for c in hash_esperado
    ):
        raise ValueError("SHA-256 inválido.")
    destino = (base / ruta_relativa).resolve()
    if destino == base:
        raise ValueError("Se requiere un nombre de archivo.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Volver a comprobar la ruta después de crear directorios.
    if not validar_ruta_segura(base, ruta_relativa):
        raise ValueError("Ruta de archivo no autorizada.")

    temporal = None
    try:
        with tempfile.NamedTemporaryFile(dir=destino.parent, prefix=".localsync-", delete=False) as salida:
            temporal = Path(salida.name)
            sha = hashlib.sha256()
            restante = tamano
            while restante:
                bloque = conexion.recv(min(BUFFER_SIZE, restante))
                if not bloque:
                    raise ConnectionError("Transferencia interrumpida.")
                salida.write(bloque)
                sha.update(bloque)
                restante -= len(bloque)
        if sha.hexdigest() != hash_esperado.lower():
            raise ValueError("SHA-256 no coincide: archivo rechazado.")
        os.replace(temporal, destino)
        temporal = None
        return destino
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
