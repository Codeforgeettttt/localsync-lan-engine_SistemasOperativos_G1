-- ============================================================================
-- LOCALSYNC - ESQUEMA RELACIONAL DE BASE DE DATOS LOCAL (SQLite 3)
-- Universidad Manuela Beltrán | Asignatura: Sistemas Operativos | Grupo G1
-- Integrantes Oficiales:
--   * Valery Michell Herrera Roca
--   * Daniel Felipe Rojas Gonzales
-- ============================================================================

PRAGMA foreign_keys = ON;

-- 1. Tabla de Nodos Pares Autorizados en la Red LAN (RF-01)
CREATE TABLE IF NOT EXISTS nodos_pares (
    id_par TEXT PRIMARY KEY,
    nombre_nodo TEXT NOT NULL,
    ip_lan TEXT NOT NULL UNIQUE,
    puerto_tcp INTEGER NOT NULL DEFAULT 9001 CHECK(puerto_tcp BETWEEN 1024 AND 65535),
    token_auth_hash TEXT NOT NULL,
    estado_autorizacion TEXT NOT NULL DEFAULT 'PENDIENTE'
        CHECK(estado_autorizacion IN ('PENDIENTE', 'AUTORIZADO', 'BLOQUEADO')),
    ultima_conexion DATETIME
);

-- 2. Tabla de Carpetas Locales Autorizadas (RF-02, RNF-04)
CREATE TABLE IF NOT EXISTS carpetas_autorizadas (
    id_carpeta INTEGER PRIMARY KEY AUTOINCREMENT,
    ruta_absoluta_linux TEXT NOT NULL UNIQUE,
    alias_carpeta TEXT NOT NULL,
    permisos_posix TEXT NOT NULL DEFAULT '0750',
    sincronizacion_activa INTEGER NOT NULL DEFAULT 1 CHECK(sincronizacion_activa IN (0, 1)),
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabla de Metadatos de Archivos Sincronizados y Tombstones (RF-03, RF-05)
-- Corrección aplicada: Restricción UNIQUE compuesta (id_carpeta, ruta_relativa)
CREATE TABLE IF NOT EXISTS archivos_sincronizados (
    id_archivo INTEGER PRIMARY KEY AUTOINCREMENT,
    id_carpeta INTEGER NOT NULL,
    ruta_relativa TEXT NOT NULL,
    hash_sha256 TEXT NOT NULL CHECK(length(hash_sha256) = 64),
    tamano_bytes INTEGER NOT NULL DEFAULT 0 CHECK(tamano_bytes >= 0),
    fecha_modificacion REAL NOT NULL,
    estado_actual TEXT NOT NULL DEFAULT 'SINCRONIZADO'
        CHECK(estado_actual IN ('SINCRONIZADO', 'MODIFICADO', 'CONFLICTO', 'ELIMINADO')),
    es_tombstone INTEGER NOT NULL DEFAULT 0 CHECK(es_tombstone IN (0, 1)),
    FOREIGN KEY (id_carpeta) REFERENCES carpetas_autorizadas(id_carpeta) ON DELETE CASCADE,
    CONSTRAINT uq_carpeta_ruta_relativa UNIQUE (id_carpeta, ruta_relativa)
);

-- 4. Tabla de Historial de Versiones y Respaldo de Conflictos (RF-06, RF-07)
CREATE TABLE IF NOT EXISTS historial_versiones (
    id_version INTEGER PRIMARY KEY AUTOINCREMENT,
    id_archivo INTEGER NOT NULL,
    hash_sha256_previo TEXT NOT NULL CHECK(length(hash_sha256_previo) = 64),
    ruta_respaldo_local TEXT NOT NULL,
    origen_nodo TEXT NOT NULL,
    es_conflicto INTEGER NOT NULL DEFAULT 0 CHECK(es_conflicto IN (0, 1)),
    fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_archivo) REFERENCES archivos_sincronizados(id_archivo) ON DELETE CASCADE
);

-- 5. Tabla de Cola Persistente de Operaciones ante Desconexión (RF-08, RF-09, RNF-06)
CREATE TABLE IF NOT EXISTS cola_sincronizacion (
    id_operacion INTEGER PRIMARY KEY AUTOINCREMENT,
    id_archivo INTEGER NOT NULL,
    id_par_destino TEXT NOT NULL,
    tipo_evento TEXT NOT NULL CHECK(tipo_evento IN ('CREATE', 'MODIFY', 'DELETE')),
    intentos_envio INTEGER NOT NULL DEFAULT 0 CHECK(intentos_envio >= 0),
    estado_cola TEXT NOT NULL DEFAULT 'PENDIENTE'
        CHECK(estado_cola IN ('PENDIENTE', 'EN_PROCESO', 'COMPLETADO', 'ERROR')),
    timestamp_evento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_archivo) REFERENCES archivos_sincronizados(id_archivo) ON DELETE CASCADE,
    FOREIGN KEY (id_par_destino) REFERENCES nodos_pares(id_par) ON DELETE CASCADE
);

-- 6. Tabla de Logs y Auditoría de Eventos del Sistema (RF-10, RF-11, RNF-07)
CREATE TABLE IF NOT EXISTS logs_auditoria (
    id_log INTEGER PRIMARY KEY AUTOINCREMENT,
    nivel TEXT NOT NULL CHECK(nivel IN ('INFO', 'WARN', 'ERROR', 'SECURITY')),
    modulo_origen TEXT NOT NULL,
    mensaje_detalle TEXT NOT NULL,
    ip_par_asociado TEXT,
    timestamp_log DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_archivos_carpeta_ruta ON archivos_sincronizados(id_carpeta, ruta_relativa);
CREATE INDEX IF NOT EXISTS idx_archivos_hash ON archivos_sincronizados(hash_sha256);
CREATE INDEX IF NOT EXISTS idx_cola_estado ON cola_sincronizacion(estado_cola, id_par_destino);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs_auditoria(timestamp_log DESC);
