"""Auditoría Docker de sincronización automática bidireccional, versiones y DELETE.

Uso: python simulacion/demo_autosync.py [--cleanup-after]
No modifica carpetas de usuario: utiliza dos volúmenes aislados de Docker.
"""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

FOLDER=Path(__file__).resolve().parent
PROJECT="localsync-autosync"
COMPOSE=[str(FOLDER/"compose.yaml"),str(FOLDER/"compose_autosync.yaml")]


def cmd(env,*args,capture=False,timeout=240):
    result=subprocess.run(["docker","compose","-p",PROJECT,
                           "-f",COMPOSE[0],"-f",COMPOSE[1],*args],
                          env=env,check=True,text=True,
                          capture_output=capture,timeout=timeout)
    return result.stdout.strip() if capture else ""


def on(env,node,code,*args):
    return cmd(env,"exec","-T",node,"python","-c",code,*args,capture=True,timeout=20)


def check_hash(env,node,path):
    return on(env,node,
              "import hashlib,sys;from pathlib import Path;"
              "print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())",path).splitlines()[-1]


def exists(env,node,path):
    return on(env,node,"import sys;from pathlib import Path;"
              "print('YES' if Path(sys.argv[1]).is_file() else 'NO')",path).splitlines()[-1]=="YES"


def until(env,node,path,expected=True,timeout=35):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if exists(env,node,path)==expected:
            return
        time.sleep(.5)
    raise AssertionError(f"{node}: estado esperado {expected} para {path}")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--cleanup-after",action="store_true")
    parser.add_argument("--cleanup",action="store_true")
    args=parser.parse_args()
    env=os.environ.copy()
    env.setdefault("LOCALSYNC_AUTH_TOKEN",secrets.token_hex(32))
    if args.cleanup:
        cmd(env,"down","-v","--remove-orphans")
        print("[OK] Laboratorio de sincronización eliminado.")
        return
    lot="prueba_"+secrets.token_hex(4)
    target="/data/sync/"+lot+".txt"
    try:
        print("[1/6] Iniciando dos Linux en red Docker privada...",flush=True)
        cmd(env,"up","-d","--build","--wait","--wait-timeout","120")
        print("[2/6] Archivo nuevo en A: debe aparecer automáticamente en B",flush=True)
        on(env,"nodo-a","import sys;from pathlib import Path;"
           "p=Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True);"
           "p.write_text('LocalSync primera versión',encoding='utf-8')",target)
        until(env,"nodo-b",target)
        hash_a=check_hash(env,"nodo-a",target)
        hash_b=check_hash(env,"nodo-b",target)
        assert hash_a==hash_b, "A->B: hashes distintos"
        print("[OK] A -> B: SHA-256 idéntico "+hash_a,flush=True)

        print("[3/6] Editando en B: debe actualizar A sin intervención humana",flush=True)
        on(env,"nodo-b","import sys;from pathlib import Path;"
           "Path(sys.argv[1]).write_text('LocalSync segunda versión B',encoding='utf-8')",target)
        changed=hashlib.sha256(b"LocalSync segunda versi\xc3\xb3n B").hexdigest()
        end=time.monotonic()+35
        while time.monotonic()<end and check_hash(env,"nodo-a",target)!=changed:
            time.sleep(.5)
        assert check_hash(env,"nodo-a",target)==changed, "B->A no se actualizó"
        assert check_hash(env,"nodo-b",target)==changed, "B perdió sus bytes"
        print("[OK] B -> A: SHA-256 idéntico "+changed,flush=True)

        print("[4/6] Verificando cola SQLite y respaldos de versiones...",flush=True)
        versions=on(env,"nodo-a","import sqlite3;"
            "c=sqlite3.connect('/data/sync.db');"
            "print(c.execute('SELECT COUNT(*) FROM sync_versions').fetchone()[0])")
        assert int(versions.splitlines()[-1])>=1, "No se guardó una versión"
        print("[OK] Versiones persistentes en SQLite",flush=True)

        print("[5/6] Borrando en A: B debe archivar en papelera recuperable...",flush=True)
        on(env,"nodo-a","import sys;from pathlib import Path;Path(sys.argv[1]).unlink()",target)
        until(env,"nodo-b",target,False)
        archived=on(env,"nodo-b","from pathlib import Path;"
             "p=Path('/data/sync/.localsync_deleted');"
             "print(len(list(p.glob('*-"+lot+".txt'))))")
        assert int(archived.splitlines()[-1])>=1,"El borrado no se archivó"
        print("[OK] Archivo eliminado del espejo y recuperable en papelera B",flush=True)

        print("[6/6] Comprobando que no quedan archivos reaparecidos...",flush=True)
        time.sleep(2)
        assert not exists(env,"nodo-a",target) and not exists(env,"nodo-b",target)
        print("RESULTADO: SINCRONIZACION AUTOMATICA BIDIRECCIONAL APROBADA",flush=True)
    except Exception:
        try:
            cmd(env,"logs","--tail","60",timeout=30)
        except Exception:
            pass
        raise
    finally:
        if args.cleanup_after:
            cmd(env,"down","-v","--remove-orphans",timeout=120)


if __name__=="__main__":
    main()
