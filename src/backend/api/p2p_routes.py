"""Endpoints locales para controlar el cliente TCP desde el panel web."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.backend.network.cliente_tcp import comprobar_conexion, enviar_archivo

router = APIRouter(prefix="/api/p2p", tags=["P2P TCP"])
CARPETA_ENVIO = Path("archivos_para_enviar").resolve()


class SolicitudArchivo(BaseModel):
    nombre: str = Field(min_length=1, max_length=255)


@router.get("/conexion")
def consultar_conexion():
    """Consulta el servidor TCP local, sin iniciar servicios ni exponer la LAN."""
    try:
        comprobar_conexion("127.0.0.1", 9001, timeout=2.0)
    except (OSError, ValueError, ConnectionError) as exc:
        return {"conectado": False, "detalle": str(exc)}
    return {"conectado": True, "detalle": "Servidor TCP local disponible (ACK)."}


@router.post("/enviar")
def enviar_archivo_local(solicitud: SolicitudArchivo):
    """Envía exclusivamente archivos directos de la carpeta de pruebas."""
    nombre = solicitud.nombre
    if nombre in {".", ".."} or Path(nombre).name != nombre or "/" in nombre or "\\" in nombre or "\x00" in nombre:
        raise HTTPException(status_code=400, detail="Nombre de archivo no permitido.")
    ruta = CARPETA_ENVIO / nombre
    if not ruta.is_file() or ruta.is_symlink():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en archivos_para_enviar.")
    try:
        enviar_archivo(ruta, "127.0.0.1", 9001, timeout=5.0)
    except (OSError, ValueError, ConnectionError) as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo transferir: {exc}") from exc
    return {"enviado": True, "archivo": nombre, "detalle": "Archivo confirmado por el receptor (ACK)."}
