"""API de control LAN y laboratorio Docker, exclusivamente para uso LOCAL.

Los endpoints trabajan con carpetas bajo la raíz de LocalSync y no exponen
rutas arbitrarias del sistema. FastAPI debe escucharse en 127.0.0.1.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import ipaddress
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from config.settings import BASE_DIR
from src.backend.core.engine import calcular_sha256
from src.backend.network.cliente_tcp import comprobar_conexion, enviar_archivo, enviar_carpeta
from src.backend.network.p2p_socket import NodoP2PTCP
from src.backend.network.transferencia import MAX_FILE_SIZE

router = APIRouter(prefix="/api/lan", tags=["Control LAN y laboratorio virtual"])
ENVIO = BASE_DIR / "archivos_para_enviar"
RECIBIDOS = BASE_DIR / "archivos_recibidos"
DEMO = BASE_DIR / "simulacion" / "demo.py"
DEMO_LOCAL = BASE_DIR / "simulacion" / "demo_local.py"

_mutex = threading.RLock()
_receiver: dict = {"nodo": None, "thread": None, "stop": None, "host": None, "port": None, "error": ""}
_history = deque(maxlen=60)
_demo_lock = threading.RLock()
_demo_state = {"estado": "sin_ejecutar", "inicio": None, "fin": None, "codigo": None,
               "salida": deque(maxlen=260), "accion": None}


class NodoDestino(BaseModel):
    host: str = Field(default="127.0.0.1", max_length=64)
    puerto: int = Field(default=9001, ge=1024, le=65535)
    token: str = Field(default="", max_length=256)


class Envio(NodoDestino):
    ruta: str = Field(min_length=1, max_length=512)
    reintentos: int = Field(default=1, ge=0, le=3)


class EnvioCarpeta(NodoDestino):
    subcarpeta: str = Field(default="", max_length=512)
    prefijo: str = Field(default="", max_length=128)


class GestionArchivo(BaseModel):
    bandeja: Literal["envios", "recibidos"] = "envios"
    ruta: str = Field(min_length=1, max_length=512)


class RenombrarArchivo(GestionArchivo):
    nuevo_nombre: str = Field(min_length=1, max_length=255)


class InicioReceptor(BaseModel):
    permitir_borrado: bool = False
    modo_lan: bool = False
    puerto: int = Field(default=9001, ge=1024, le=65535)
    token: str = Field(default="", max_length=256)


def _evento(tipo: str, detalle: str) -> None:
    with _mutex:
        _history.appendleft({
            "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tipo": tipo, "detalle": detalle[:240],
        })


def _dentro(base: Path, ruta: str, *, permitir_base: bool = False) -> Path:
    """Ruta POSIX relativa, sin traversal, symlinks ni archivos fuera del directorio."""
    if not isinstance(ruta, str) or "\x00" in ruta or "\\" in ruta or ":" in ruta:
        raise HTTPException(400, "Ruta no válida.")
    if not ruta and permitir_base:
        return base
    partes = ruta.split("/")
    if not ruta or any(p in {"", ".", ".."} for p in partes) or len(ruta) > 512:
        raise HTTPException(400, "Ruta relativa no permitida.")
    if PurePosixPath(ruta).is_absolute():
        raise HTTPException(400, "No se admiten rutas absolutas.")
    destino = base.joinpath(*partes)
    actual = base
    for parte in partes:
        actual = actual / parte
        if actual.is_symlink():
            raise HTTPException(400, "No se permiten enlaces simbólicos.")
    if not destino.resolve().is_relative_to(base.resolve()):
        raise HTTPException(400, "Ruta fuera de carpeta autorizada.")
    return destino


def _host_privado(host: str) -> str:
    host = host.strip()
    if host.lower() == "localhost":
        return "127.0.0.1"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise HTTPException(400, "Indica una IP privada o localhost (no se permiten dominios).")
    if not isinstance(ip, ipaddress.IPv4Address):
        raise HTTPException(400, "Por ahora utiliza una dirección IPv4 de tu red local.")
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved or not (ip.is_loopback or ip.is_private):
        raise HTTPException(400, "Usa una dirección IPv4 privada válida, por ejemplo 192.168.1.25.")
    return str(ip)


def _listado(base: Path, limite: int = 150) -> list[dict]:
    base.mkdir(parents=True, exist_ok=True)
    resultado = []
    for ruta in sorted(base.rglob("*")):
        if len(resultado) >= limite:
            break
        if ruta.is_symlink() or not ruta.is_file() or ruta.name.startswith(".localsync-"):
            continue
        try:
            resultado.append({"ruta": ruta.relative_to(base).as_posix(),
                              "tamano": ruta.stat().st_size})
        except OSError:
            continue
    return resultado


@router.get("/estado")
def estado_lan():
    with _mutex:
        hilo = _receiver["thread"]
        activo = bool(hilo and hilo.is_alive())
        return {"receptor": {"activo": activo, "host": _receiver["host"] if activo else None,
                             "puerto": _receiver["port"] if activo else None,
                             "error": _receiver["error"]},
                "envios": len(_listado(ENVIO)),
                "recibidos": len(_listado(RECIBIDOS)),
                "historial": list(_history),
                "tls_ca_configurada": bool(os.getenv("LOCALSYNC_TLS_CA"))}


@router.get("/archivos")
def listar_archivos():
    return {"envios": _listado(ENVIO), "recibidos": _listado(RECIBIDOS)}


@router.get("/descargar")
def descargar_recibido(ruta: str):
    archivo = _dentro(RECIBIDOS, ruta)
    if not archivo.is_file():
        raise HTTPException(404, "El archivo recibido no existe.")
    return FileResponse(archivo, filename=archivo.name, media_type="application/octet-stream")


def _carpeta_bandeja(bandeja: str) -> Path:
    return ENVIO if bandeja == "envios" else RECIBIDOS


@router.get("/archivo/verificar")
def verificar_archivo(ruta: str, bandeja: Literal["envios", "recibidos"] = "recibidos"):
    archivo = _dentro(_carpeta_bandeja(bandeja), ruta)
    if archivo.is_symlink() or not archivo.is_file():
        raise HTTPException(404, "No se encontró un archivo regular para verificar.")
    try:
        return {"ruta": ruta, "bandeja": bandeja, "sha256": calcular_sha256(archivo),
                "tamano": archivo.stat().st_size}
    except OSError as exc:
        raise HTTPException(500, f"No se pudo verificar el archivo: {exc}") from exc


@router.delete("/archivo")
def eliminar_archivo(datos: GestionArchivo):
    base = _carpeta_bandeja(datos.bandeja)
    archivo = _dentro(base, datos.ruta)
    with _mutex:
        if archivo.is_symlink() or not archivo.is_file():
            raise HTTPException(404, "Archivo no encontrado o ya eliminado.")
        try:
            archivo.unlink()
        except OSError as exc:
            raise HTTPException(409, f"No se puede eliminar este archivo: {exc}") from exc
    _evento("ARCHIVO_ELIMINADO", f"{datos.bandeja}: {datos.ruta}")
    return {"eliminado": True, "ruta": datos.ruta, "bandeja": datos.bandeja}


@router.patch("/archivo")
def renombrar_archivo(datos: RenombrarArchivo):
    if "/" in datos.nuevo_nombre or "\\" in datos.nuevo_nombre:
        raise HTTPException(400, "Escribe un nombre de archivo, sin carpetas ni barras.")
    base = _carpeta_bandeja(datos.bandeja)
    origen = _dentro(base, datos.ruta)
    destino = _dentro(base, (Path(datos.ruta).parent / datos.nuevo_nombre).as_posix()
                     if "/" in datos.ruta else datos.nuevo_nombre)
    with _mutex:
        if origen.is_symlink() or not origen.is_file():
            raise HTTPException(404, "Archivo de origen no encontrado.")
        if destino != origen:
            if destino.exists() or destino.is_symlink():
                raise HTTPException(409, "Ya existe un archivo con ese nombre.")
            try:
                origen.rename(destino)
            except OSError as exc:
                raise HTTPException(409, f"No se pudo renombrar el archivo: {exc}") from exc
    relativa = destino.relative_to(base).as_posix()
    _evento("ARCHIVO_RENOMBRADO", f"{datos.bandeja}: {datos.ruta} → {relativa}")
    return {"renombrado": True, "ruta": relativa, "bandeja": datos.bandeja}


@router.get("/red")
def informacion_red():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private and not ip.is_loopback and not ip.is_link_local:
                ips.add(str(ip))
    except OSError:
        pass
    return {"ips_locales": sorted(ips), "puerto_sugerido": 9001,
            "nota": "Usa la IP del adaptador conectado a la misma red que el otro equipo."}


@router.post("/archivos")
async def cargar_archivo(archivo: Annotated[UploadFile, File()],
                        ruta: Annotated[str, Form()] = ""):
    """Sube un archivo a la bandeja de envíos sin permitir traversal ni sobrescritura."""
    relativa = ruta or Path(archivo.filename or "").name
    destino = _dentro(ENVIO, relativa)
    if not destino.name or destino.suffix == ".part":
        raise HTTPException(400, "Nombre de archivo no permitido.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    cantidad = 0
    try:
        with tempfile.NamedTemporaryFile(dir=destino.parent, prefix=".localsync-", delete=False) as out:
            temporal = Path(out.name)
            while chunk := await archivo.read(65536):
                cantidad += len(chunk)
                if cantidad > MAX_FILE_SIZE:
                    raise HTTPException(413, "Máximo 100 MiB por archivo.")
                out.write(chunk)
        with _mutex:
            # La bandeja no sobrescribe silenciosamente archivos que hayan cambiado.
            if destino.exists():
                if destino.is_symlink() or not destino.is_file():
                    raise HTTPException(409, "Destino ocupado.")
                if calcular_sha256(destino) == calcular_sha256(temporal):
                    return {"ruta": destino.relative_to(ENVIO).as_posix(), "tamano": cantidad,
                            "mensaje": "El archivo ya estaba preparado."}
                destino = destino.with_name(f"{destino.stem}-copia-{secrets.token_hex(4)}{destino.suffix}")
            temporal.replace(destino)
            temporal = None
        _evento("ARCHIVO_PREPARADO", destino.relative_to(ENVIO).as_posix())
        return {"ruta": destino.relative_to(ENVIO).as_posix(), "tamano": cantidad,
                "mensaje": "Archivo listo para enviar."}
    finally:
        await archivo.close()
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def _token(texto: str) -> str | None:
    return texto or os.getenv("LOCALSYNC_AUTH_TOKEN") or None


def _tls_kwargs(host: str) -> dict:
    ca = os.getenv("LOCALSYNC_TLS_CA") or None
    return {"tls_ca": ca, "tls_server_name": os.getenv("LOCALSYNC_TLS_SERVER_NAME") or host}


def _mensaje_red(exc: Exception, host: str, puerto: int) -> str:
    if isinstance(exc, ConnectionRefusedError) or getattr(exc, "winerror", None) == 10061:
        return f"Conexión rechazada en {host}:{puerto}. Inicia el receptor TCP en el otro equipo y revisa el puerto."
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return f"Tiempo de espera agotado hacia {host}:{puerto}. Revisa IP, red Wi-Fi/LAN y firewall."
    if isinstance(exc, PermissionError):
        return "Autenticación rechazada: comprueba que ambos equipos usan el mismo token."
    if isinstance(exc, ValueError):
        return str(exc)[:200]
    return f"No fue posible conectar con {host}:{puerto}: {str(exc)[:140]}"


@router.post("/conexion")
def probar_conexion(datos: NodoDestino):
    host = _host_privado(datos.host)
    try:
        comprobar_conexion(host, datos.puerto, timeout=4,
                           auth_token=_token(datos.token), **_tls_kwargs(host))
    except (OSError, ValueError, PermissionError) as exc:
        _evento("CONEXION_FALLIDA", f"{host}:{datos.puerto}")
        return {"conectado": False, "detalle": _mensaje_red(exc, host, datos.puerto)}
    _evento("CONEXION_OK", f"{host}:{datos.puerto}")
    return {"conectado": True, "detalle": f"ACK recibido desde {host}:{datos.puerto}"}


@router.post("/enviar")
def enviar(datos: Envio):
    host = _host_privado(datos.host)
    fuente = _dentro(ENVIO, datos.ruta)
    if not fuente.is_file():
        raise HTTPException(404, "No se encuentra el archivo en la bandeja de envíos.")
    try:
        enviar_archivo(fuente, host, datos.puerto, timeout=12,
                       auth_token=_token(datos.token), ruta_remota=datos.ruta,
                       reintentos=datos.reintentos, **_tls_kwargs(host))
    except (OSError, ValueError, PermissionError) as exc:
        detalle = _mensaje_red(exc, host, datos.puerto)
        _evento("ENVIO_ERROR", f"{datos.ruta}: {detalle}")
        raise HTTPException(502, f"Transferencia no completada: {detalle}") from exc
    digest = calcular_sha256(fuente)
    _evento("ENVIO_OK", f"{datos.ruta} → {host}:{datos.puerto}")
    return {"enviado": True, "archivo": datos.ruta, "sha256": digest,
            "mensaje": "Archivo transferido, ACK confirmado."}


@router.post("/enviar-carpeta")
def enviar_carpeta_completa(datos: EnvioCarpeta):
    host = _host_privado(datos.host)
    fuente = _dentro(ENVIO, datos.subcarpeta, permitir_base=True)
    if not fuente.is_dir():
        raise HTTPException(404, "La carpeta no existe.")
    if not _listado(fuente):
        raise HTTPException(400, "No hay archivos para transferir.")
    if datos.prefijo:
        _dentro(ENVIO, datos.prefijo)
    try:
        correctos, errores = enviar_carpeta(
            fuente, host, datos.puerto, timeout=12,
            auth_token=_token(datos.token), prefijo_remoto=datos.prefijo,
            reintentos=1, **_tls_kwargs(host))
    except (OSError, ValueError, PermissionError) as exc:
        raise HTTPException(502, f"Error enviando carpeta: {exc}") from exc
    _evento("CARPETA_ENVIADA", f"{correctos} correctos, {errores} fallidos")
    return {"correctos": correctos, "errores": errores,
            "mensaje": f"Transferidos {correctos} archivos; errores: {errores}."}


def _worker_receptor(nodo: NodoP2PTCP, detener: threading.Event, listo: threading.Event):
    try:
        nodo.servir(detener, listo)
    except Exception as exc:
        with _mutex:
            _receiver["error"] = str(exc)[:180]
        _evento("RECEPTOR_ERROR", type(exc).__name__)


@router.post("/receptor/iniciar")
def iniciar_receptor(datos: InicioReceptor):
    with _mutex:
        if _receiver["thread"] and _receiver["thread"].is_alive():
            raise HTTPException(409, "El receptor ya está encendido.")
        host = "0.0.0.0" if datos.modo_lan else "127.0.0.1"
        token = _token(datos.token)
        if datos.permitir_borrado and (not token or len(token) < 16):
            raise HTTPException(400, "Borrado remoto requiere token de al menos 16 caracteres")
        if datos.modo_lan and (not token or len(token) < 16):
            raise HTTPException(400, "Para habilitar LAN configura un token compartido de al menos 16 caracteres.")
        try:
            nodo = NodoP2PTCP(
                host, datos.puerto, RECIBIDOS, auth_token=token,
                allow_delete=datos.permitir_borrado,
                on_received=lambda destino, msg: _evento(
                    "RECEPCION_OK",
                    f"{destino.name} · {msg['tamano_bytes']} bytes · SHA-256 {msg['hash_sha256'][:16]}…"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        detener, listo = threading.Event(), threading.Event()
        _receiver.update({"nodo": nodo, "stop": detener, "host": host,
                          "port": datos.puerto, "error": "", "thread": None})
        hilo = threading.Thread(target=_worker_receptor, args=(nodo, detener, listo),
                                name="localsync-receptor-ui", daemon=True)
        _receiver["thread"] = hilo
        hilo.start()
    if not listo.wait(2):
        with _mutex:
            problema = _receiver["error"] or "No se pudo abrir el puerto TCP."
        raise HTTPException(503, problema)
    _evento("RECEPTOR_INICIADO", f"{host}:{datos.puerto}")
    return {"activo": True, "host": host, "puerto": datos.puerto}


@router.post("/receptor/detener")
def detener_receptor():
    with _mutex:
        hilo, evento = _receiver["thread"], _receiver["stop"]
    if not hilo or not hilo.is_alive() or evento is None:
        return {"activo": False}
    evento.set()
    hilo.join(timeout=5)
    if hilo.is_alive():
        raise HTTPException(503, "El receptor sigue deteniéndose.")
    _evento("RECEPTOR_DETENIDO", "Detenido desde el panel.")
    return {"activo": False}


def _demo_snapshot():
    with _demo_lock:
        return {"estado": _demo_state["estado"], "inicio": _demo_state["inicio"],
                "fin": _demo_state["fin"], "codigo": _demo_state["codigo"],
                "accion": _demo_state["accion"], "salida": list(_demo_state["salida"])}


@router.get("/simulacion/estado")
def estado_demo():
    snapshot = _demo_snapshot()
    snapshot["docker_disponible"] = bool(shutil.which("docker"))
    return snapshot


def _ejecutar_demo(accion: str):
    env = os.environ.copy()
    env.setdefault("LOCALSYNC_AUTH_TOKEN", secrets.token_hex(32))
    script = DEMO_LOCAL if accion == "local" else DEMO
    comando = [sys.executable, "-u", str(script)]
    if accion == "limpiar":
        comando.append("--cleanup")
    try:
        with subprocess.Popen(comando, cwd=str(BASE_DIR), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", bufsize=1) as proceso:
            assert proceso.stdout is not None
            for linea in proceso.stdout:
                with _demo_lock:
                    _demo_state["salida"].append(linea.rstrip()[:600])
            codigo = proceso.wait(timeout=20)
        with _demo_lock:
            _demo_state["codigo"] = codigo
            _demo_state["estado"] = (
                "sin_ejecutar" if accion == "limpiar" and codigo == 0
                else "aprobado" if codigo == 0 else "fallido"
            )
    except Exception as exc:
        with _demo_lock:
            _demo_state["estado"] = "fallido"
            _demo_state["codigo"] = -1
            _demo_state["salida"].append(f"Error del controlador: {type(exc).__name__}: {exc}")
    finally:
        with _demo_lock:
            _demo_state["fin"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iniciar_demo(accion: str):
    if accion != "local" and not shutil.which("docker"):
        raise HTTPException(503, "Docker no está disponible. Inicia Docker Desktop o usa la prueba local sin Docker.")
    if accion != "local":
        try:
            motor = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, timeout=5, check=False,
            )
            if motor.returncode != 0:
                raise HTTPException(503,
                    "Docker está instalado, pero su motor no responde. Abre Docker Desktop, "
                    "comprueba el modo Linux y vuelve a intentarlo; también puedes usar la prueba local.")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(503,
                "No se puede comunicar con Docker. Inicia Docker Desktop o usa la prueba local.") from exc
    script = DEMO_LOCAL if accion == "local" else DEMO
    if not script.is_file():
        raise HTTPException(500, "No se encontró el programa de simulación.")
    with _demo_lock:
        if _demo_state["estado"] == "ejecutando":
            raise HTTPException(409, "Ya hay una operación Docker en curso.")
        _demo_state.update({"estado": "ejecutando",
                            "inicio": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "fin": None, "codigo": None, "accion": accion})
        _demo_state["salida"].clear()
        hilo = threading.Thread(target=_ejecutar_demo, args=(accion,),
                                name="localsync-auditoria-docker", daemon=True)
        hilo.start()
    return {"iniciado": True, "accion": accion}


@router.post("/simulacion/iniciar")
def iniciar_demo():
    return _iniciar_demo("ejecutar")


@router.post("/simulacion/local")
def iniciar_demo_local():
    return _iniciar_demo("local")


@router.post("/simulacion/limpiar")
def limpiar_demo():
    return _iniciar_demo("limpiar")


@router.get("/simulacion/evidencia")
def evidencia_demo():
    estado = _demo_snapshot()
    if estado["estado"] == "sin_ejecutar":
        raise HTTPException(404, "Todavía no se ha ejecutado una simulación.")
    encabezado = (f"LocalSync — Registro de auditoría virtual\n"
                  f"Acción: {estado['accion']}\nInicio: {estado['inicio']}\n"
                  f"Fin: {estado['fin']}\nEstado: {estado['estado']}\n\n")
    cuerpo = encabezado + "\n".join(estado["salida"]) + "\n"
    return Response(content=cuerpo, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="localsync-evidencia-simulacion.txt"'})
