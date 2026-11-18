"""Motor de sincronización incremental: vigilancia, cola SQLite, versiones y reintentos.

La sincronización es EXPLÍCITA (se activa en la GUI), entre carpeta local de
envío y carpeta receptora de cada par. Por seguridad DELETE no se propaga
a menos que ambos extremos lo autoricen; jamás observa la carpeta recibidos
para evitar bucles en red. No incluye reanudación por fragmentos.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import shutil
import sqlite3
import threading
import time
from collections import deque
from contextlib import closing
from datetime import datetime, timezone

from src.backend.core.engine import calcular_sha256
from src.backend.network.cliente_tcp import enviar_archivo
from src.backend.network.transferencia import MAX_FILE_SIZE


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_relative(value: str) -> str:
    from pathlib import PurePosixPath
    if not value or "\\" in value or "\0" in value or ":" in value:
        raise ValueError("Ruta relativa inválida")
    parts = value.split("/")
    if any(p in {"", ".", ".."} for p in parts) or PurePosixPath(value).is_absolute():
        raise ValueError("Ruta relativa insegura")
    return value


class ColaPersistente:
    """DB independiente para evitar incompatibilidad con el esquema de Fase 1."""

    def __init__(self, db: str | Path):
        self.path = Path(db)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with closing(self._open()) as con, con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS sync_peers(
                  id INTEGER PRIMARY KEY, host TEXT NOT NULL, port INTEGER NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  UNIQUE(host,port));
                CREATE TABLE IF NOT EXISTS sync_files(
                  path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
                  mtime_ns INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sync_queue(
                  id INTEGER PRIMARY KEY, peer_id INTEGER NOT NULL,
                  path TEXT NOT NULL, operation TEXT NOT NULL,
                  sha256 TEXT NOT NULL DEFAULT '', tries INTEGER NOT NULL DEFAULT 0,
                  state TEXT NOT NULL DEFAULT 'pending', next_run REAL NOT NULL DEFAULT 0,
                  error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                  UNIQUE(peer_id,path),
                  FOREIGN KEY(peer_id) REFERENCES sync_peers(id));
                CREATE TABLE IF NOT EXISTS sync_versions(
                  id INTEGER PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL,
                  backup TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_sync_pending ON sync_queue(state,next_run);
            """)

    def _open(self):
        con = sqlite3.connect(str(self.path), timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def peers(self):
        with self.lock, closing(self._open()) as con:
            return [dict(row) for row in con.execute("SELECT * FROM sync_peers ORDER BY id")]

    def add_peer(self, host: str, port: int):
        with self.lock, closing(self._open()) as con, con:
            con.execute("INSERT INTO sync_peers(host,port,enabled) VALUES(?,?,1) "
                        "ON CONFLICT(host,port) DO UPDATE SET enabled=1", (host, port))
            return int(con.execute("SELECT id FROM sync_peers WHERE host=? AND port=?",
                                   (host, port)).fetchone()[0])

    def remove_peer(self, peer_id: int):
        with self.lock, closing(self._open()) as con, con:
            con.execute("DELETE FROM sync_queue WHERE peer_id=?", (peer_id,))
            con.execute("DELETE FROM sync_peers WHERE id=?", (peer_id,))

    def files(self):
        with self.lock, closing(self._open()) as con:
            return {r["path"]: dict(r) for r in con.execute("SELECT * FROM sync_files")}

    def set_file(self, path: str, sha: str, size: int, mtime_ns: int):
        with self.lock, closing(self._open()) as con, con:
            con.execute("INSERT INTO sync_files VALUES(?,?,?,?) ON CONFLICT(path) "
                        "DO UPDATE SET sha256=excluded.sha256,size=excluded.size,"
                        "mtime_ns=excluded.mtime_ns", (path, sha, size, mtime_ns))

    def del_file(self, path: str):
        with self.lock, closing(self._open()) as con, con:
            con.execute("DELETE FROM sync_files WHERE path=?", (path,))

    def enqueue(self, peer_id: int, path: str, op: str, sha: str = ""):
        _safe_relative(path)
        with self.lock, closing(self._open()) as con, con:
            con.execute("""INSERT INTO sync_queue(peer_id,path,operation,sha256,created_at)
                         VALUES(?,?,?,?,?)
                         ON CONFLICT(peer_id,path) DO UPDATE SET
                           operation=excluded.operation, sha256=excluded.sha256,
                           tries=0,state='pending',next_run=0,error='',
                           created_at=excluded.created_at""", (peer_id, path, op, sha, utc()))

    def next_job(self):
        with self.lock, closing(self._open()) as con:
            row = con.execute("""
                SELECT q.*,p.host,p.port FROM sync_queue q JOIN sync_peers p
                ON p.id=q.peer_id WHERE q.state='pending'
                AND q.next_run<=? AND p.enabled=1 ORDER BY q.id LIMIT 1
            """, (time.time(),)).fetchone()
            return dict(row) if row else None

    def finish(self, job_id: int):
        with self.lock, closing(self._open()) as con, con:
            con.execute("DELETE FROM sync_queue WHERE id=?", (job_id,))

    def fail(self, job_id: int, attempts: int, message: str):
        delay = min(2 ** min(attempts, 7), 120)
        with self.lock, closing(self._open()) as con, con:
            con.execute("UPDATE sync_queue SET tries=?,state='pending',next_run=?,error=? "
                        "WHERE id=?", (attempts, time.time()+delay, message[:300], job_id))

    def stats(self):
        with self.lock, closing(self._open()) as con:
            n = con.execute("SELECT COUNT(*) FROM sync_queue").fetchone()[0]
            failed = con.execute("SELECT COUNT(*) FROM sync_queue WHERE tries>0").fetchone()[0]
            recent = [dict(r) for r in con.execute(
                "SELECT path,operation,tries,error,next_run FROM sync_queue ORDER BY id DESC LIMIT 20")]
            return {"pendientes": n, "con_errores": failed, "cola": recent}

    def add_version(self, path: str, sha: str, backup: str):
        with self.lock, closing(self._open()) as con, con:
            con.execute("INSERT INTO sync_versions(path,sha256,backup,created_at) VALUES(?,?,?,?)",
                        (path, sha, backup, utc()))

    def versions(self, path: str | None = None):
        with self.lock, closing(self._open()) as con:
            if path is None:
                rows=con.execute("SELECT * FROM sync_versions ORDER BY id DESC LIMIT 100")
            else:
                rows=con.execute("SELECT * FROM sync_versions WHERE path=? ORDER BY id DESC LIMIT 100",(path,))
            return [dict(r) for r in rows]


class AutoSync:
    """Un vigilante de una carpeta explícita + cola de envío para pares autorizados."""

    def __init__(self, root: str | Path, db: str | Path, backup_dir: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = ColaPersistente(db)
        self.backup_dir = Path(backup_dir).resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if self.root == self.backup_dir or self.root in self.backup_dir.parents:
            raise ValueError("Los respaldos deben estar fuera de la carpeta vigilada")
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._observer = None
        self._watchdog_enabled = False
        self._thread = None
        self._credentials: dict[tuple[str,int],str] = {}
        self._tls_ca: str | None = None
        self._events = deque(maxlen=80)
        self._lock = threading.RLock()
        self.propagate_deletes = False
        self._first_scan = True
        self._stable: dict[str,tuple[int,int]] = {}

    def event(self, kind: str, detail: str):
        with self._lock:
            self._events.appendleft({"fecha":utc(),"tipo":kind,"detalle":detail[:240]})

    def add_peer(self, host: str, port: int, token: str):
        if not token or len(token) < 16:
            raise ValueError("La sincronización requiere un token compartido de al menos 16 caracteres")
        peer = self.db.add_peer(host, port)
        with self._lock:
            self._credentials[(host,port)] = token
        self.event("PAR_AUTORIZADO", f"{host}:{port}")
        return peer

    def remove_peer(self, peer_id: int):
        peer = next((p for p in self.db.peers() if p["id"] == peer_id), None)
        self.db.remove_peer(peer_id)
        if peer:
            with self._lock:
                self._credentials.pop((peer["host"],peer["port"]), None)

    def start(self, *, propagate_deletes: bool = False):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            if not self.db.peers():
                raise ValueError("Añade un equipo remoto antes de activar la sincronización")
            self.propagate_deletes = propagate_deletes
            self._first_scan = True
            self._stop.clear()
            self._wake.clear()
            # Watchdog acelera la detección por eventos nativos; el escaneo
            # periódico sigue siendo la fuente de verdad y permite recuperarse.
            try:
                from watchdog.observers import Observer
                from watchdog.events import FileSystemEventHandler

                wake = self._wake
                class Changed(FileSystemEventHandler):
                    def on_any_event(self, event):
                        if ".localsync-" not in event.src_path:
                            wake.set()
                observer = Observer()
                observer.schedule(Changed(), str(self.root), recursive=True)
                observer.start()
                self._observer = observer
                self._watchdog_enabled = True
            except (OSError, ImportError, RuntimeError):
                self._observer = None
                self._watchdog_enabled = False
            self._thread = threading.Thread(target=self._run, name="localsync-autosync", daemon=True)
            self._thread.start()
            self.event("SYNC_INICIADO", "Vigilancia automática habilitada")
            return True

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=4)
            self._observer = None
        self._watchdog_enabled = False
        with self._lock:
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=6)
        self.event("SYNC_DETENIDO", "Vigilancia desactivada")

    def status(self):
        with self._lock:
            active = bool(self._thread and self._thread.is_alive())
            events = list(self._events)
        return {"activo":active,"watchdog_activo":self._watchdog_enabled,
                "carpeta":str(self.root),
                "borrados_remotos":self.propagate_deletes,"pares":self.db.peers(),
                "historial":events,**self.db.stats()}

    def _backup(self, path: str, source: Path, sha: str):
        if not source.exists() or not source.is_file():
            return
        # Content-addressed, never overwrite; backup before local modifications can be observed.
        target = self.backup_dir / sha[:2] / sha
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source,target)
        self.db.add_version(path, sha, str(target))

    def snapshot(self):
        found={}
        for file in sorted(self.root.rglob("*")):
            if file.is_symlink() or not file.is_file():
                continue
            rel = file.relative_to(self.root).as_posix()
            if rel.startswith(".localsync-") or "/.localsync-" in rel:
                continue
            try:
                stat=file.stat()
                if stat.st_size>MAX_FILE_SIZE:
                    continue
                found[rel]=(stat.st_size,stat.st_mtime_ns)
            except OSError:
                continue
        return found

    def scan(self):
        previous = self.db.files()
        current = self.snapshot()
        peers = self.db.peers()
        for rel,(size,mtime) in current.items():
            was=previous.get(rel)
            if was and was["size"]==size and was["mtime_ns"]==mtime:
                continue
            if self._stable.get(rel)!=(size,mtime):
                self._stable[rel]=(size,mtime)
                continue
            source=self.root / rel
            try:
                sha=calcular_sha256(source)
                if source.stat().st_mtime_ns!=mtime: continue
            except (OSError,ValueError):
                continue
            if was and was["sha256"]==sha:
                self.db.set_file(rel,sha,size,mtime)
                continue
            self.db.set_file(rel,sha,size,mtime)
            self._backup(rel,source,sha)
            for peer in peers:
                self.db.enqueue(peer["id"],rel,"CREATE",sha)
            self.event("CAMBIO_DETECTADO",rel)
        for rel,was in previous.items():
            if rel in current: continue
            self.db.del_file(rel)
            if not self._first_scan and self.propagate_deletes:
                for peer in peers:
                    self.db.enqueue(peer["id"],rel,"DELETE")
            self.event("ELIMINADO_LOCAL",rel)
        self._first_scan=False
        self._stable={k:v for k,v in self._stable.items() if k in current}

    def dispatch(self):
        job=self.db.next_job()
        if not job: return
        with self._lock:
            token=self._credentials.get((job["host"],job["port"])) or os.getenv("LOCALSYNC_AUTH_TOKEN")
        if not token or len(token)<16:
            self.db.fail(job["id"],job["tries"]+1,"Token no disponible; vuelve a autorizar el par")
            return
        try:
            if job["operation"]=="DELETE":
                from src.backend.network.cliente_tcp import enviar_borrado
                enviar_borrado(job["path"],job["host"],job["port"],auth_token=token,timeout=5)
            else:
                file=self.root / _safe_relative(job["path"])
                if not file.is_file() or file.is_symlink():
                    self.db.finish(job["id"])  # superseded by deletion/rename
                    return
                sha=calcular_sha256(file)
                if sha!=job["sha256"]:
                    self.db.enqueue(job["peer_id"],job["path"],"CREATE",sha)
                    return
                enviar_archivo(file,job["host"],job["port"],auth_token=token,
                              ruta_remota=job["path"],timeout=5,reintentos=0)
            self.db.finish(job["id"])
            self.event("SYNC_OK",f"{job['operation']} {job['path']} -> {job['host']}:{job['port']}")
        except (OSError,ValueError,PermissionError,ConnectionError) as exc:
            self.db.fail(job["id"],job["tries"]+1,str(exc))
            self.event("SYNC_REINTENTO",f"{job['path']}: {type(exc).__name__}")

    def restore(self, version_id: int):
        versions=self.db.versions()
        version=next((v for v in versions if v["id"]==version_id),None)
        if not version: raise ValueError("Versión no encontrada")
        rel=_safe_relative(version["path"])
        src=Path(version["backup"])
        if not src.is_file() or calcular_sha256(src)!=version["sha256"]:
            raise ValueError("El respaldo está ausente o dañado")
        dest=self.root / rel
        current=self.root
        for segment in rel.split("/"):
            current=current/segment
            if current.is_symlink(): raise ValueError("Destino con enlace simbólico")
        dest.parent.mkdir(parents=True,exist_ok=True)
        temp=dest.parent / (".localsync-restore-"+str(time.time_ns()))
        try:
            shutil.copy2(src,temp)
            os.replace(temp,dest)
        finally:
            temp.unlink(missing_ok=True)
        self.event("VERSION_RESTAURADA",rel)
        return rel

    def _run(self):
        while not self._stop.is_set():
            try:
                self.scan()
                self.dispatch()
            except Exception as exc:
                self.event("SYNC_ERROR",f"{type(exc).__name__}: {str(exc)[:140]}")
            self._wake.wait(1.0)
            self._wake.clear()
