"""
Módulo Storage: Gestión de Persistencia Local en SQLite 3.
Proyecto: LocalSync - Sistemas Operativos (Grupo G1)
Integrantes Oficiales:
  - Valery Michell Herrera Roca
  - Daniel Felipe Rojas Gonzales
"""
import sqlite3
from pathlib import Path
from typing import Dict, Any


class GestorBaseDatosLocal:
    def __init__(self, db_path: str | Path = "localsync_meta.db") -> None:
        self.db_path = Path(db_path)

    def _conectar(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def inicializar_esquema(self, sql_script_path: str | Path) -> None:
        ruta_sql = Path(sql_script_path)
        if not ruta_sql.exists():
            raise FileNotFoundError(f"No se encontró el archivo de esquema SQL: {ruta_sql}")
        script = ruta_sql.read_text(encoding="utf-8")
        with self._conectar() as conn:
            conn.executescript(script)
            conn.commit()

    def registrar_carpeta_autorizada(
        self,
        ruta_absoluta_linux: str,
        alias_carpeta: str,
        permisos_posix: str = "0750",
    ) -> int:
        with self._conectar() as conn:
            cursor = conn.execute(
                """
                INSERT INTO carpetas_autorizadas (ruta_absoluta_linux, alias_carpeta, permisos_posix)
                VALUES (?, ?, ?)
                """,
                (ruta_absoluta_linux, alias_carpeta, permisos_posix),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def registrar_archivo_sincronizado(
        self,
        id_carpeta: int,
        ruta_relativa: str,
        hash_sha256: str,
        tamano_bytes: int,
        fecha_modificacion: float,
        estado_actual: str = "SINCRONIZADO",
        es_tombstone: int = 0,
    ) -> int:
        with self._conectar() as conn:
            cursor = conn.execute(
                """
                INSERT INTO archivos_sincronizados (
                    id_carpeta, ruta_relativa, hash_sha256, tamano_bytes,
                    fecha_modificacion, estado_actual, es_tombstone
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id_carpeta,
                    ruta_relativa,
                    hash_sha256,
                    tamano_bytes,
                    fecha_modificacion,
                    estado_actual,
                    es_tombstone,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def obtener_resumen_bd(self) -> Dict[str, Any]:
        if not self.db_path.exists():
            return {
                "bd_inicializada": False,
                "ruta_bd": str(self.db_path),
                "tablas_detectadas": [],
                "conteo_registros": {},
            }
        try:
            with self._conectar() as conn:
                tablas_rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
                ).fetchall()
                tablas = [r["name"] for r in tablas_rows]
                conteos: Dict[str, int] = {}
                for t in tablas:
                    c = conn.execute(f"SELECT COUNT(*) AS total FROM {t};").fetchone()
                    conteos[t] = int(c["total"]) if c else 0
                return {
                    "bd_inicializada": len(tablas) > 0,
                    "ruta_bd": str(self.db_path),
                    "tablas_detectadas": tablas,
                    "conteo_registros": conteos,
                }
        except sqlite3.Error as exc:
            return {
                "bd_inicializada": False,
                "ruta_bd": str(self.db_path),
                "error_sqlite": str(exc),
                "tablas_detectadas": [],
                "conteo_registros": {},
            }
