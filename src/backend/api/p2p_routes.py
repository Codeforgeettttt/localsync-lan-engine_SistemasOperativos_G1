"""Endpoints locales para controlar el cliente TCP desde el panel web."""
from pathlib import Path
from ipaddress import IPv4Address, IPv4Network
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.backend.network.cliente_tcp import comprobar_conexion, enviar_archivo

router = APIRouter(prefix="/api/p2p", tags=["P2P TCP"])
CARPETA_ENVIO = Path("archivos_para_enviar").resolve()


def validar_destino(host: str, puerto: int):
    try:
        ip = IPv4Address(host)
    except ValueError as exc:
        raise HTTPException(400, "Introduce una dirección IPv4 válida.") from exc
    if not 1024 <= puerto <= 65535:
        raise HTTPException(400, "Puerto fuera de rango.")
    if ip == IPv4Address("127.0.0.1"):
        return
    redes = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    if not any(ip in IPv4Network(red) for red in redes):
        raise HTTPException(400, "Solo se permiten direcciones LAN privadas.")
    if os.environ.get("LOCALSYNC_PAR_LAN") != str(ip):
        raise HTTPException(403, "Par LAN no autorizado por la configuración local.")


class SolicitudArchivo(BaseModel):
    host: str = "127.0.0.1"
    puerto: int = 9001
    nombre: str = Field(min_length=1, max_length=255)


@router.get("/conexion")
def consultar_conexion(host: str = "127.0.0.1", puerto: int = 9001):
    validar_destino(host, puerto)
    """Consulta el servidor TCP local, sin iniciar servicios ni exponer la LAN."""
    try:
        comprobar_conexion(host, puerto, timeout=2.0)
    except (OSError, ValueError, ConnectionError) as exc:
        return {"conectado": False, "detalle": str(exc)}
    return {"conectado": True, "detalle": "Servidor TCP disponible (ACK)."}


@router.post("/enviar")
def enviar_archivo_local(solicitud: SolicitudArchivo):
    """Envía exclusivamente archivos directos de la carpeta de pruebas."""
    validar_destino(solicitud.host, solicitud.puerto)
    nombre = solicitud.nombre
    if nombre in {".", ".."} or Path(nombre).name != nombre or "/" in nombre or "\\" in nombre or "\x00" in nombre:
        raise HTTPException(status_code=400, detail="Nombre de archivo no permitido.")
    ruta = CARPETA_ENVIO / nombre
    if not ruta.is_file() or ruta.is_symlink():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en archivos_para_enviar.")
    try:
        enviar_archivo(ruta, solicitud.host, solicitud.puerto, timeout=5.0)
    except (OSError, ValueError, ConnectionError) as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo transferir: {exc}") from exc
    return {"enviado": True, "archivo": nombre, "detalle": "Archivo confirmado por el receptor (ACK)."}
