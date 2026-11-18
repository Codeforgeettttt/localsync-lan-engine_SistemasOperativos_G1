"""Proceso de sincronización sin FastAPI, útil para Docker y despliegue dedicado."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import threading
import time

from src.backend.network.p2p_socket import NodoP2PTCP
from src.backend.sync.engine import AutoSync


def main():
    parser=argparse.ArgumentParser(description="LocalSync motor autónomo TCP + vigilancia")
    parser.add_argument("--host",default="0.0.0.0")
    parser.add_argument("--port",type=int,default=9001)
    parser.add_argument("--peer",required=True)
    parser.add_argument("--peer-port",type=int,default=9001)
    parser.add_argument("--root",default="/data/sync")
    parser.add_argument("--state-db",default="/data/sync.db")
    parser.add_argument("--versions",default="/data/versions")
    parser.add_argument("--enable-deletes",action="store_true")
    args=parser.parse_args()
    token=os.getenv("LOCALSYNC_AUTH_TOKEN","")
    if len(token)<16:
        parser.error("Se requiere LOCALSYNC_AUTH_TOKEN de al menos 16 caracteres")
    engine=AutoSync(args.root,args.state_db,args.versions)
    engine.add_peer(args.peer,args.peer_port,token)
    receiver=NodoP2PTCP(
        args.host,args.port,engine.root,
        auth_token=token,on_conflict="overwrite",
        allow_delete=args.enable_deletes,
        on_before_overwrite=engine.backup_before_overwrite,
        on_received=engine.register_incoming,
        on_deleted=engine.register_remote_deleted,
    )
    stop=threading.Event()
    ready=threading.Event()
    def request_stop(*_):
        stop.set()
    signal.signal(signal.SIGTERM,request_stop)
    signal.signal(signal.SIGINT,request_stop)
    thread=threading.Thread(target=receiver.servir,args=(stop,ready),
                            daemon=True,name="localsync-tcp-receptor")
    thread.start()
    if not ready.wait(6):
        raise RuntimeError("El puerto TCP no está listo")
    engine.start(propagate_deletes=args.enable_deletes)
    print(f"[LocalSync][SYNC_LISTO] par={args.peer}:{args.peer_port} "
          f"carpeta={engine.root} borrados={args.enable_deletes}",flush=True)
    try:
        while not stop.wait(.5):
            if not thread.is_alive():
                raise RuntimeError("El servidor TCP se detuvo")
    finally:
        engine.stop()
        stop.set()
        thread.join(timeout=6)


if __name__=="__main__":
    main()
