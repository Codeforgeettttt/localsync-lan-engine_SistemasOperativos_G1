"""Publicación segura de archivos recibidos por TCP.

El flujo es: validar cabecera y ruta -> recibir a temporal -> validar SHA-256
-> publicar atómicamente. No reemplaza archivos distintos sin una política explícita.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
from pathlib import Path, PurePosixPath

from src.backend.core.engine import calcular_sha256, validar_ruta_segura

BUFFER_SIZE = 65536
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MiB por archivo
_PUBLICATION_LOCK = threading.RLock()
POLITICAS_CONFLICTO = {"keep-both", "reject", "overwrite"}


def _ruta_segura(base: Path, relativa: str) -> Path:
    """Restringe todas las rutas recibidas a la carpeta autorizada."""
    if not isinstance(relativa, str) or not relativa or "\x00" in relativa or "\\" in relativa:
        raise ValueError("Ruta de archivo no autorizada.")
    if any(part.startswith((".localsync-", ".localsync_"))
           for part in relativa.split("/")):
        raise ValueError("Ruta reservada para datos internos de LocalSync.")
    ruta_posix = PurePosixPath(relativa)
    if ruta_posix.is_absolute() or any(p in {".", ".."} for p in relativa.split("/")):
        raise ValueError("Ruta de archivo no autorizada.")
    if re.match(r"^[a-zA-Z]:", relativa) or not validar_ruta_segura(base, relativa):
        raise ValueError("Ruta de archivo no autorizada.")
    destino = base / Path(*ruta_posix.parts)
    if destino == base:
        raise ValueError("Se requiere un nombre de archivo.")
    # Evitar seguir enlaces simbólicos preexistentes, también en subdirectorios.
    actual = base
    for parte in ruta_posix.parts:
        actual = actual / parte
        if actual.is_symlink():
            raise ValueError("No se permiten enlaces simbólicos en la ruta de destino.")
    return destino


def _destino_conflicto(destino: Path, sha_nuevo: str) -> Path:
    """Nombre estable, legible y sin sobrescritura para archivos en conflicto."""
    sufijo = f".conflict-{sha_nuevo[:12]}"
    candidato = destino.with_name(f"{destino.stem}{sufijo}{destino.suffix}")
    numero = 2
    while candidato.exists() or candidato.is_symlink():
        if candidato.is_file() and calcular_sha256(candidato) == sha_nuevo:
            return candidato  # idempotencia: ya se recibió esta versión.
        candidato = destino.with_name(f"{destino.stem}{sufijo}-{numero}{destino.suffix}")
        numero += 1
    return candidato


def recibir_archivo(conexion, mensaje: dict, carpeta_autorizada: str | Path,
                    on_conflict: str = "keep-both", on_before_overwrite=None) -> Path:
    """Recibe el contenido exacto, valida SHA-256 y publica sin pérdida silenciosa.

    En caso de un nombre existente con hash distinto, guarda una copia .conflict-*
    por defecto. Si ocurre un error, no modifica el archivo original ni deja temporales.
    """
    if on_conflict not in POLITICAS_CONFLICTO:
        raise ValueError("Política de conflicto desconocida.")
    base = Path(carpeta_autorizada).resolve()
    base.mkdir(parents=True, exist_ok=True)
    tamano = mensaje.get("tamano_bytes")
    esperado = mensaje.get("hash_sha256")
    if not isinstance(tamano, int) or isinstance(tamano, bool) or not 0 <= tamano <= MAX_FILE_SIZE:
        raise ValueError("Tamaño de archivo inválido o superior a 100 MiB.")
    if not isinstance(esperado, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", esperado):
        raise ValueError("SHA-256 inválido.")
    destino = _ruta_segura(base, mensaje.get("ruta_relativa"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Revalidar después de crear los directorios.
    destino = _ruta_segura(base, mensaje["ruta_relativa"])

    temporal = None
    try:
        with tempfile.NamedTemporaryFile(dir=destino.parent, prefix=".localsync-", delete=False) as salida:
            temporal = Path(salida.name)
            digest = hashlib.sha256()
            restante = tamano
            while restante:
                bloque = conexion.recv(min(BUFFER_SIZE, restante))
                if not bloque:
                    raise ConnectionError("Transferencia interrumpida antes de completar el archivo.")
                salida.write(bloque)
                digest.update(bloque)
                restante -= len(bloque)
        sha_recibido = digest.hexdigest()
        if sha_recibido != esperado.lower():
            raise ValueError("SHA-256 no coincide: archivo rechazado.")

        with _PUBLICATION_LOCK:
            destino = _ruta_segura(base, mensaje["ruta_relativa"])
            if destino.exists() or destino.is_symlink():
                if not destino.is_file() or destino.is_symlink():
                    raise ValueError("El destino existe y no es un archivo regular.")
                if destino.stat().st_size == tamano and calcular_sha256(destino) == sha_recibido:
                    return destino  # recepción repetida sin modificar el archivo.
                if on_conflict == "reject":
                    raise FileExistsError("Archivo distinto con el mismo nombre; envío rechazado.")
                if on_conflict == "overwrite" and on_before_overwrite is not None:
                    on_before_overwrite(destino)
                if on_conflict == "keep-both":
                    destino = _destino_conflicto(destino, sha_recibido)
                    if destino.is_file() and calcular_sha256(destino) == sha_recibido:
                        return destino
            os.replace(temporal, destino)
            temporal = None
            return destino
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)



def recibir_reanudable(conexion, mensaje: dict, carpeta_autorizada: str | Path,
                       *, on_conflict: str = "keep-both",
                       on_before_overwrite=None, on_offset=None) -> Path:
    """Reanuda un archivo incompleto tras caída TCP usando un .part persistente.

    Requiere el mismo hash y ruta; nunca confía en bytes recibidos antes de
    verificar SHA-256 final. Los temporales incompletos quedan en la carpeta
    interna para poder continuar después de reiniciar el servidor.
    """
    if on_conflict not in POLITICAS_CONFLICTO:
        raise ValueError("Política de conflicto desconocida")
    base = Path(carpeta_autorizada).resolve()
    base.mkdir(parents=True, exist_ok=True)
    size = mensaje.get("tamano_bytes")
    expected = mensaje.get("hash_sha256")
    if not isinstance(size, int) or isinstance(size,bool) or not 0 <= size <= MAX_FILE_SIZE:
        raise ValueError("Tamaño inválido")
    if not isinstance(expected,str) or not re.fullmatch(r"[0-9a-fA-F]{64}",expected):
        raise ValueError("Hash SHA-256 inválido")
    expected=expected.lower()
    dest=_ruta_segura(base,mensaje.get("ruta_relativa"))
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest=_ruta_segura(base,mensaje["ruta_relativa"])
    part_dir=base/".localsync_partials"
    part_dir.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256((mensaje["ruta_relativa"]+"|"+expected).encode("utf-8")).hexdigest()
    partial=part_dir/(key+".part")

    # El bloqueo impide que sesiones simultáneas modifiquen el mismo temporal.
    # CREATE convencional continúa usando su propia recepción concurrente.
    with _PUBLICATION_LOCK:
        if partial.is_symlink() or (partial.exists() and not partial.is_file()):
            raise ValueError("Temporal de reanudación inseguro")
        offset=partial.stat().st_size if partial.exists() else 0
        if offset>size:
            partial.unlink()
            offset=0
        if on_offset is not None:
            on_offset(offset)
        remaining=size-offset
        with partial.open("ab") as out:
            while remaining:
                chunk=conexion.recv(min(BUFFER_SIZE,remaining))
                if not chunk:
                    raise ConnectionError("Transferencia interrumpida: temporal guardado para reanudar")
                out.write(chunk)
                remaining-=len(chunk)
        digest=calcular_sha256(partial)
        if digest!=expected:
            partial.unlink(missing_ok=True)
            raise ValueError("SHA-256 no coincide; temporal de reanudación descartado")

        dest=_ruta_segura(base,mensaje["ruta_relativa"])
        if dest.exists() or dest.is_symlink():
            if dest.is_symlink() or not dest.is_file():
                raise ValueError("El destino es un archivo inseguro")
            if dest.stat().st_size==size and calcular_sha256(dest)==digest:
                partial.unlink(missing_ok=True)
                return dest
            if on_conflict=="reject":
                partial.unlink(missing_ok=True)
                raise FileExistsError("Archivo diferente con el mismo nombre")
            if on_conflict=="keep-both":
                dest=_destino_conflicto(dest,digest)
                if dest.is_file() and calcular_sha256(dest)==digest:
                    partial.unlink(missing_ok=True)
                    return dest
            elif on_before_overwrite is not None:
                on_before_overwrite(dest)
        os.replace(partial,dest)
        return dest
