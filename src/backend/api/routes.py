"""
Módulo API Local: Endpoints REST en FastAPI para diagnóstico, estructura inicial y modo demostración.
Proyecto: LocalSync - Sistemas Operativos (Grupo G1)
Integrantes Oficiales:
  - Valery Michell Herrera Roca
  - Daniel Felipe Rojas Gonzales
"""
import platform
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config.settings import DEFAULT_DB_PATH, SCHEMA_SQL_PATH, P2P_PORT, MODO_DEMOSTRACION
from src.backend.core.engine import MotorSincronizacionLocal
from src.backend.storage.db_manager import GestorBaseDatosLocal

app = FastAPI(
    title="LocalSync Local Control API (Prototipo Fase 1)",
    description=(
        "API local de estructuración inicial para LocalSync (Grupo G1). "
        "Diferencia explícitamente entre componentes verificados y datos de demostración."
    ),
    version="0.1.0-fase1",
)

motor_local = MotorSincronizacionLocal()
gestor_bd = GestorBaseDatosLocal(DEFAULT_DB_PATH)


class SolicitudPausa(BaseModel):
    pausar: bool


@app.get("/api/estado")
def obtener_estado_nodo():
    resumen_bd = gestor_bd.obtener_resumen_bd()
    estado_motor = motor_local.obtener_estado_motor()

    return {
        "proyecto": "LocalSync",
        "grupo": "G1",
        "integrantes": [
            "Valery Michell Herrera Roca",
            "Daniel Felipe Rojas Gonzales",
        ],
        "fase_proyecto": "Fase 1 - Estructuración, Documentación y Base Verificable",
        "es_simulacion": MODO_DEMOSTRACION,
        "advertencia_estado": (
            "Prototipo en Fase 1: La API FastAPI, el esquema SQLite, el cálculo SHA-256 y el validador "
            "anti-Path Traversal son reales y verificables. La transferencia P2P por sockets TCP, "
            "el canal TLS y el observador Watchdog en segundo plano están planificados para las Fases 3 a 7."
        ),
        "entorno_real_detectado": {
            "hostname": platform.node() or "nodo-local-no-identificado",
            "sistema_operativo": f"{platform.system()} {platform.release()}",
            "python_version": platform.python_version(),
        },
        "componentes_implementados": {
            "api_fastapi": "IMPLEMENTADO (Operativo en ejecución local)",
            "calculo_sha256": "IMPLEMENTADO Y PROBADO (src/backend/core/engine.py)",
            "validacion_rutas_seguras": "IMPLEMENTADO Y PROBADO (src/backend/core/engine.py)",
            "esquema_sqlite3": "IMPLEMENTADO Y PROBADO (src/bd/schema.sql)",
            "serializador_mensajes_p2p": "IMPLEMENTADO Y PROBADO (src/backend/network/p2p_socket.py)",
        },
        "componentes_pendientes": {
            "transporte_sockets_tcp_lan": "PENDIENTE (Planificado para Fase 3)",
            "monitoreo_watchdog_inotify": "PENDIENTE (Planificado para Fase 4)",
            "reconciliacion_y_tombstones": "PENDIENTE (Planificado para Fase 5)",
            "seguridad_tls_y_autenticacion": "PENDIENTE (Planificado para Fase 7)",
        },
        "estado_motor_local": estado_motor,
        "estado_base_datos_sqlite": resumen_bd,
        "datos_demostracion_ui": {
            "nota": "DATOS SIMULADOS DE DEMOSTRACIÓN PARA PREVISUALIZACIÓN DE LA INTERFAZ WEB",
            "par_ejemplo": f"Nodo-Par-Demo (192.168.10.22:{P2P_PORT}) [SIMULADO - SIN CONEXIÓN REAL]",
            "eventos_ejemplo": [
                "[SIMULACIÓN UI] Ejemplo de visualización: recepción de metadatos por protocolo LOCALSYNC_P2P_V1.",
                "[SIMULACIÓN UI] Ejemplo de visualización: carpeta /home/ubuntu/LocalSync_Compartida pendiente de monitoreo Watchdog.",
            ],
        },
    }


@app.post("/api/inicializar-bd")
def inicializar_base_datos():
    try:
        gestor_bd.inicializar_esquema(SCHEMA_SQL_PATH)
        return {
            "mensaje": "Base de datos SQLite inicializada correctamente con el esquema real.",
            "estado_base_datos_sqlite": gestor_bd.obtener_resumen_bd(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al inicializar SQLite: {exc}") from exc


@app.post("/api/control/pausa")
def cambiar_estado_pausa(solicitud: SolicitudPausa):
    motor_local.sincronizacion_pausada = solicitud.pausar
    return {
        "sincronizacion_pausada": motor_local.sincronizacion_pausada,
        "alcance_accion": (
            "Estado actualizado en memoria de la API. La vinculación con el demonio Watchdog "
            "y el socket TCP real se implementará en las Fases 3 y 4."
        ),
    }


FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def servir_panel_web():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
