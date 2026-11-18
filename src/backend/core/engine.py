"""
Módulo Core: Funciones base de Integridad (SHA-256), Seguridad de Rutas y Estructura del Observador.
Proyecto: LocalSync - Sistemas Operativos (Grupo G1)
Integrantes Oficiales:
  - Valery Michell Herrera Roca
  - Daniel Felipe Rojas Gonzales
"""
import hashlib
import os
from pathlib import Path
from typing import Dict, Any


def calcular_sha256(ruta_archivo: str | Path, tamano_bloque: int = 65536) -> str:
    ruta = Path(ruta_archivo)
    if not ruta.exists():
        raise FileNotFoundError(f"El archivo no existe: {ruta}")
    if not ruta.is_file():
        raise ValueError(f"La ruta especificada no es un archivo regular: {ruta}")
    if tamano_bloque <= 0:
        raise ValueError("El tamaño de bloque debe ser mayor que cero.")

    sha256 = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(tamano_bloque), b""):
            sha256.update(bloque)
    return sha256.hexdigest()


def validar_ruta_segura(directorio_base: str | Path, ruta_relativa_objetivo: str | Path) -> bool:
    try:
        ruta_rel_str = str(ruta_relativa_objetivo).strip()
        if not ruta_rel_str or chr(0) in ruta_rel_str:
            return False
        if os.path.isabs(ruta_rel_str):
            return False

        base = Path(directorio_base).resolve()
        objetivo = (base / ruta_rel_str).resolve()
        return base == objetivo or base in objetivo.parents
    except (OSError, RuntimeError, ValueError):
        return False


class MotorSincronizacionLocal:
    def __init__(self, directorio_autorizado: str | Path | None = None) -> None:
        self.directorio_autorizado = Path(directorio_autorizado).resolve() if directorio_autorizado else None
        self.sincronizacion_pausada: bool = False
        self.watchdog_implementado: bool = True

    def obtener_estado_motor(self) -> Dict[str, Any]:
        # Consulta diferida para no crear un ciclo de imports durante FastAPI.
        # El estado del motor nuevo es independiente del estado legado de Fase 1.
        try:
            from src.backend.api.sync_routes import get_engine
            actual = get_engine().status()
        except (OSError, ValueError, RuntimeError):
            actual = {"activo": False, "watchdog_activo": False}
        return {
            "fase_actual": "Motor de sincronización y transferencia LAN integrado",
            "watchdog_activo": bool(actual.get("watchdog_activo")),
            "watchdog_estado_desarrollo": "Implementado con respaldo de escaneo",
            "sha256_operativo": True,
            "validador_rutas_operativo": True,
            "sincronizacion_pausada": self.sincronizacion_pausada,
            "sincronizacion_automatica_activa": bool(actual.get("activo")),
            "directorio_autorizado": actual.get("carpeta") or (
                str(self.directorio_autorizado) if self.directorio_autorizado else None),
        }
