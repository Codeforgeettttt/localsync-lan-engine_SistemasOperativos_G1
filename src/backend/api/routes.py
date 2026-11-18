"""LocalSync — API local y panel de control.

El panel HTTP solo está permitido desde el equipo local. La recepción LAN real
se realiza por sockets TCP autenticados en el puerto configurado.
"""
from __future__ import annotations

import ipaddress
import platform
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import DEFAULT_DB_PATH, SCHEMA_SQL_PATH
from src.backend.core.engine import MotorSincronizacionLocal
from src.backend.storage.db_manager import GestorBaseDatosLocal
from src.backend.api.p2p_routes import router as p2p_router
from src.backend.api.lan_routes import router as lan_router
from src.backend.api.sync_routes import router as sync_router, get_engine

app = FastAPI(
    title="LocalSync — Control LAN",
    description="Control local FastAPI, transferencia TCP entre nodos y laboratorio Docker.",
    version="0.4.0-sync",
)
app.include_router(p2p_router)
app.include_router(lan_router)
app.include_router(sync_router)

motor_local = MotorSincronizacionLocal()
gestor_bd = GestorBaseDatosLocal(DEFAULT_DB_PATH)


@app.middleware("http")
async def solo_panel_local(request: Request, call_next):
    """Nunca exponer las acciones del panel HTTP sin autenticación sobre la LAN."""
    origen_remoto = request.client.host if request.client else ""
    if origen_remoto not in {"testclient", "localhost"}:
        try:
            if not ipaddress.ip_address(origen_remoto).is_loopback:
                return JSONResponse({"detail": "Panel web disponible solo desde localhost."}, status_code=403)
        except ValueError:
            return JSONResponse({"detail": "Origen del panel no autorizado."}, status_code=403)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower():
            return JSONResponse({"detail": "Acción bloqueada: origen web diferente."}, status_code=403)
    return await call_next(request)


class SolicitudPausa(BaseModel):
    pausar: bool


@app.get("/api/estado")
def obtener_estado_nodo():
    resumen_bd = gestor_bd.obtener_resumen_bd()
    return {
        "proyecto": "LocalSync",
        "grupo": "G1",
        "integrantes": ["Valery Michell Herrera Roca", "Daniel Felipe Rojas Gonzales"],
        "fase_proyecto": "Sincronización incremental opt-in + transferencia TCP LAN",
        "es_simulacion": False,
        "advertencia_estado": (
            "Transferencia de archivos TCP, SHA-256, HMAC, TLS opcional y laboratorio Docker implementados. "
            "Watchdog, cola SQLite, reanudación por offset, versiones y réplica bidireccional opt-in disponibles; "
            "no hay consenso distribuido de ediciones concurrentes ni limpieza automática de parciales."
        ),
        "entorno_real_detectado": {
            "hostname": platform.node() or "nodo-local",
            "sistema_operativo": f"{platform.system()} {platform.release()}",
            "python_version": platform.python_version(),
        },
        "componentes_implementados": {
            "api_fastapi": "OPERATIVO",
            "transferencia_tcp_manual": "IMPLEMENTADO Y PROBADO",
            "carpetas_recursivas": "IMPLEMENTADO Y PROBADO",
            "calculo_sha256": "IMPLEMENTADO Y PROBADO",
            "validacion_rutas_seguras": "IMPLEMENTADO Y PROBADO",
            "hmac": "IMPLEMENTADO",
            "tls_opcional": "IMPLEMENTADO (requiere certificado y configuración)",
            "pruebas_docker_dos_nodos": "IMPLEMENTADO Y VALIDADO EN CI",
            "esquema_sqlite3": "IMPLEMENTADO",
            "autosync_cola_sqlite": "IMPLEMENTADO (opt-in)",
            "versiones_locales": "IMPLEMENTADO",
            "borrado_remoto": "IMPLEMENTADO (opt-in + papelera)",
            "watchdog": "IMPLEMENTADO con escaneo de respaldo",
            "reanudacion_por_offset": "IMPLEMENTADO con SHA-256",
            "descubrimiento_lan": "IMPLEMENTADO UDP/HMAC",
            "sincronizacion_bidireccional": "IMPLEMENTADO (opt-in con respaldo de versiones)",
            "autostart_linux": "IMPLEMENTADO (plantilla systemd + variables protegidas)",
        },
        "componentes_pendientes": {
            "consenso_ediciones_concurrentes": "PENDIENTE (último cambio aplicado + respaldo)",
            "limpieza_automatica_parciales": "PENDIENTE",
            "auditoria_seguridad_externa": "PENDIENTE",
        },
        "estado_motor_local": motor_local.obtener_estado_motor(),
        "estado_motor_autosync": get_engine().status(),
        "estado_base_datos_sqlite": resumen_bd,
    }


@app.post("/api/inicializar-bd")
def inicializar_base_datos():
    try:
        gestor_bd.inicializar_esquema(SCHEMA_SQL_PATH)
        return {"mensaje": "Base SQLite inicializada.",
                "estado_base_datos_sqlite": gestor_bd.obtener_resumen_bd()}
    except Exception as exc:
        raise HTTPException(500, "Error al inicializar SQLite.") from exc


@app.post("/api/control/pausa")
def cambiar_estado_pausa(solicitud: SolicitudPausa):
    motor_local.sincronizacion_pausada = solicitud.pausar
    if solicitud.pausar:
        get_engine().stop()
    return {
        "sincronizacion_pausada": motor_local.sincronizacion_pausada,
        "alcance_accion": "Pausa la vigilancia automática local; no detiene el receptor TCP manual.",
    }



@app.on_event("startup")
def despliegue_automatico_configurado():
    """Arranque opcional por variables de entorno, sin exponer HTTP en la LAN."""
    import os
    if os.getenv("LOCALSYNC_AUTOSTART", "0") != "1":
        return
    from src.backend.api.lan_routes import InicioReceptor, iniciar_receptor
    from src.backend.api.sync_routes import _host
    token = os.getenv("LOCALSYNC_AUTH_TOKEN", "")
    peer = os.getenv("LOCALSYNC_SYNC_PEER", "").strip()
    port = int(os.getenv("LOCALSYNC_SYNC_PEER_PORT", "9001"))
    listen_port = int(os.getenv("LOCALSYNC_P2P_PORT", "9001"))
    if len(token) < 16 or not peer:
        raise RuntimeError(
            "LOCALSYNC_AUTOSTART requiere LOCALSYNC_AUTH_TOKEN (16+ caracteres) "
            "y LOCALSYNC_SYNC_PEER (IPv4 privada)."
        )
    peer = _host(peer)
    delete = os.getenv("LOCALSYNC_ALLOW_REMOTE_DELETE", "0") == "1"
    engine = get_engine()
    engine.add_peer(peer, port, token)
    iniciar_receptor(InicioReceptor(modo_lan=True, carpeta_compartida=True,
                                    permitir_borrado=delete, puerto=listen_port,
                                    token=token))
    engine.start(propagate_deletes=delete)


@app.on_event("shutdown")
def detener_servicios_en_cierre():
    from src.backend.api.lan_routes import detener_receptor
    get_engine().stop()
    detener_receptor()


FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def servir_panel_web():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
