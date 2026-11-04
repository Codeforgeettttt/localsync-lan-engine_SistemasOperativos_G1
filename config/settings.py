"""
Configuración central del prototipo LocalSync (Fase 1 - Estructuración).
Integrantes: Valery Michell Herrera Roca, Daniel Felipe Rojas Gonzales.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = os.getenv("LOCALSYNC_DB_PATH", str(BASE_DIR / "src" / "bd" / "localsync_meta.db"))
SCHEMA_SQL_PATH = os.getenv("LOCALSYNC_SCHEMA_PATH", str(BASE_DIR / "src" / "bd" / "schema.sql"))
API_HOST = os.getenv("LOCALSYNC_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("LOCALSYNC_API_PORT", "8080"))
P2P_PORT = int(os.getenv("LOCALSYNC_P2P_PORT", "9001"))
MODO_DEMOSTRACION = os.getenv("LOCALSYNC_DEMO_MODE", "true").lower() == "true"
