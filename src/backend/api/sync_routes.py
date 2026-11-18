"""API administrativa de sincronización automática (loopback exclusivamente)."""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings import BASE_DIR
from src.backend.sync.engine import AutoSync

router = APIRouter(prefix="/api/sync", tags=["Sincronización automática"])
_engine_lock = threading.RLock()
_engine: AutoSync | None = None


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            root = Path(os.getenv("LOCALSYNC_SYNC_DIR", str(BASE_DIR / "carpeta_sincronizada")))
            root = root.resolve()
            if root == BASE_DIR or root == Path.home().resolve():
                raise ValueError("Configura una subcarpeta dedicada para la sincronización")
            _engine = AutoSync(
                root,
                Path(os.getenv("LOCALSYNC_SYNC_DB", str(BASE_DIR / "datos_locales" / "sync.db"))),
                Path(os.getenv("LOCALSYNC_VERSIONS_DIR", str(BASE_DIR / "datos_locales" / "versiones"))),
            )
        return _engine


class ParNuevo(BaseModel):
    host: str = Field(max_length=64)
    port: int = Field(default=9001, ge=1024, le=65535)
    token: str = Field(min_length=16, max_length=256)


class InicioSync(BaseModel):
    propagate_deletes: bool = False


class VersionRestore(BaseModel):
    version_id: int = Field(ge=1)


def _host(host: str):
    try:
        ip = ipaddress.ip_address(host.strip())
    except ValueError:
        raise HTTPException(400, "Utiliza la IPv4 privada del otro equipo")
    if not isinstance(ip, ipaddress.IPv4Address) or (
        ip.is_unspecified or ip.is_multicast or ip.is_reserved or
        not (ip.is_private or ip.is_loopback)
    ):
        raise HTTPException(400, "Solo direcciones IPv4 privadas")
    return str(ip)


@router.get("/estado")
def estado():
    return get_engine().status()


@router.post("/pares")
def agregar_par(p: ParNuevo):
    host = _host(p.host)
    try:
        identity = get_engine().add_peer(host,p.port,p.token)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    return {"id":identity,"host":host,"port":p.port,"autorizado":True,
            "mensaje":"Par guardado; el token solo permanece en memoria por seguridad."}


@router.delete("/pares/{peer_id}")
def eliminar_par(peer_id: int):
    get_engine().remove_peer(peer_id)
    return {"eliminado":True}


@router.post("/iniciar")
def iniciar(p: InicioSync):
    try:
        engine = get_engine()
        result=engine.start(propagate_deletes=p.propagate_deletes)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    return {"activo":True,"iniciado":result, "mensaje":"Vigilancia y cola activas."}


@router.post("/detener")
def detener():
    get_engine().stop()
    return {"activo":False}


@router.get("/versiones")
def versiones(path: str | None = None):
    return {"versiones":get_engine().db.versions(path)}


@router.post("/restaurar")
def restaurar(data: VersionRestore):
    try:
        path=get_engine().restore(data.version_id)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    return {"restaurado":True,"ruta":path}


@router.post("/escanear")
def escanear():
    engine=get_engine()
    engine.scan()
    return engine.status()
