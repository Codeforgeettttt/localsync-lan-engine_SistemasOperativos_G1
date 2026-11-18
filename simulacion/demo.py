"""Auditoria reproducible: dos nodos Linux en LAN virtual Docker.

Requisitos en el host: Python 3.10+ y Docker Compose v2.
No requiere instalar dependencias Python en el host.
    python simulacion/demo.py
    python simulacion/demo.py --status
    python simulacion/demo.py --cleanup
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

PROJECT = "localsync-auditoria"
COMPOSE = Path(__file__).resolve().parent / "compose.yaml"


def ejecutar_compose(env: dict, *argumentos: str, capturar: bool = False) -> str:
    comando = ["docker", "compose", "-p", PROJECT, "-f", str(COMPOSE), *argumentos]
    try:
        resultado = subprocess.run(
            comando,
            env=env,
            text=True,
            check=True,
            capture_output=capturar,
            timeout=240 if "build" in argumentos or "up" in argumentos else 90,
        )
    except subprocess.CalledProcessError as exc:
        if capturar:
            print(exc.stdout or "", file=sys.stderr)
            print(exc.stderr or "", file=sys.stderr)
        raise
    return resultado.stdout.strip() if capturar else ""


def ejecutar_nodo(env: dict, nodo: str, *comando: str, capturar: bool = False) -> str:
    return ejecutar_compose(env, "exec", "-T", nodo, *comando, capturar=capturar)


def sha256_nodo(env: dict, nodo: str, ruta: str) -> str:
    codigo = (
        "import hashlib, pathlib, sys; "
        "print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())"
    )
    respuesta = ejecutar_nodo(env, nodo, "python", "-c", codigo, ruta, capturar=True)
    ultimo = respuesta.splitlines()[-1].strip()
    if len(ultimo) != 64 or any(c not in "0123456789abcdef" for c in ultimo):
        raise RuntimeError(f"Respuesta SHA-256 inesperada de {nodo}: {respuesta}")
    return ultimo


def exigir_igual(uno: str, dos: str, etiqueta: str) -> None:
    if uno != dos:
        raise AssertionError(f"{etiqueta}: SHA-256 DIFERENTE. origen={uno} destino={dos}")
    print(f"  [OK] {etiqueta}: SHA-256 idéntico: {uno}")


def preparar_archivos(env: dict, lote: str) -> tuple[str, str, str]:
    base = f"/data/envios/{lote}"
    codigo_a = (
        "from pathlib import Path; import sys; "
        "d=Path(sys.argv[1]); (d/'carpeta'/'docs').mkdir(parents=True,exist_ok=True); "
        "(d/'documento_A.txt').write_text('Versión ORIGINAL desde el nodo A\\n',encoding='utf-8'); "
        "(d/'carpeta'/'docs'/'manual.txt').write_text('Manual A en subcarpeta\\n',encoding='utf-8')"
    )
    codigo_b = (
        "from pathlib import Path; import sys; "
        "d=Path(sys.argv[1]); d.mkdir(parents=True,exist_ok=True); "
        "(d/'documento_B.bin').write_bytes(bytes(range(256))*128)"
    )
    ejecutar_nodo(env, "nodo-a", "python", "-c", codigo_a, base)
    ejecutar_nodo(env, "nodo-b", "python", "-c", codigo_b, base)
    return base + "/documento_A.txt", base + "/documento_B.bin", base + "/carpeta"


def transferir(env: dict, origen: str, destino: str, archivo: str, ruta_remota: str) -> None:
    ejecutar_nodo(
        env, origen, "python", "-m", "src.backend.network.cliente_tcp",
        "--host", destino, "--port", "9001", "--file", archivo,
        "--remote-path", ruta_remota, "--retries", "2",
    )


def demo(env: dict) -> None:
    lote = "lote_" + secrets.token_hex(4)
    remoto = f"auditoria/{lote}"
    print("\n[1/6] Creando dos contenedores Linux y la red LAN virtual aislada...", flush=True)
    ejecutar_compose(env, "up", "-d", "--build", "--wait", "--wait-timeout", "120")
    print("\n[2/6] Validando conectividad de ambas máquinas por DNS Docker...", flush=True)
    ejecutar_nodo(env, "nodo-a", "python", "-m", "src.backend.network.cliente_tcp",
                 "--host", "nodo-b", "--port", "9001")
    ejecutar_nodo(env, "nodo-b", "python", "-m", "src.backend.network.cliente_tcp",
                 "--host", "nodo-a", "--port", "9001")
    a, b, carpeta = preparar_archivos(env, lote)

    print("\n[3/6] Enviando archivo A -> B con ACK y verificando hash...", flush=True)
    transferir(env, "nodo-a", "nodo-b", a, f"{remoto}/documento_A.txt")
    hash_a = sha256_nodo(env, "nodo-a", a)
    exigir_igual(hash_a, sha256_nodo(env, "nodo-b", f"/data/recibidos/{remoto}/documento_A.txt"),
                 "A -> B")

    print("\n[4/6] Enviando archivo binario B -> A con ACK y verificando hash...", flush=True)
    transferir(env, "nodo-b", "nodo-a", b, f"{remoto}/documento_B.bin")
    exigir_igual(sha256_nodo(env, "nodo-b", b),
                 sha256_nodo(env, "nodo-a", f"/data/recibidos/{remoto}/documento_B.bin"),
                 "B -> A")

    print("\n[5/6] Enviando carpeta con subdirectorio A -> B...", flush=True)
    ejecutar_nodo(
        env, "nodo-a", "python", "-m", "src.backend.network.cliente_tcp",
        "--host", "nodo-b", "--directory", carpeta,
        "--remote-prefix", f"{remoto}/carpeta", "--retries", "2",
    )
    exigir_igual(
        sha256_nodo(env, "nodo-a", carpeta + "/docs/manual.txt"),
        sha256_nodo(env, "nodo-b", f"/data/recibidos/{remoto}/carpeta/docs/manual.txt"),
        "Carpeta con subdirectorio",
    )

    print("\n[6/6] Modificando A, reenviando y comprobando conflicto sin pérdida...", flush=True)
    cambiar = (
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_text('Versión MODIFICADA desde el nodo A\\n',encoding='utf-8')"
    )
    ejecutar_nodo(env, "nodo-a", "python", "-c", cambiar, a)
    hash_modificado = sha256_nodo(env, "nodo-a", a)
    transferir(env, "nodo-a", "nodo-b", a, f"{remoto}/documento_A.txt")
    transferir(env, "nodo-a", "nodo-b", a, f"{remoto}/documento_A.txt")
    exigir_igual(hash_a, sha256_nodo(env, "nodo-b",
                                    f"/data/recibidos/{remoto}/documento_A.txt"),
                 "Versión original preservada")
    ruta_conflicto = f"/data/recibidos/{remoto}/documento_A.conflict-{hash_modificado[:12]}.txt"
    exigir_igual(hash_modificado, sha256_nodo(env, "nodo-b", ruta_conflicto),
                 "Nueva versión en archivo de conflicto")
    validar_unica = (
        "from pathlib import Path; import sys; "
        "base=Path(sys.argv[1]); coincidencias=list(base.glob('documento_A.conflict-*.txt')); "
        "assert len(coincidencias)==1, f'Se esperó una versión conflictiva, hay {len(coincidencias)}'; "
        "print('  [OK] Reintento idempotente: una sola copia de conflicto')"
    )
    ejecutar_nodo(env, "nodo-b", "python", "-c", validar_unica, f"/data/recibidos/{remoto}")
    print("\nRESULTADO: AUDITORÍA VIRTUAL APROBADA. Dos nodos independientes, LAN, "
          "A->B, B->A, carpetas, ACK, SHA-256 y conflictos verificados.", flush=True)
    print(f"Carpeta de evidencia virtual: {remoto}")
    print("Ver contenedores: python simulacion/demo.py --status")
    print("Borrar contenedores/volúmenes de prueba: python simulacion/demo.py --cleanup")


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoría Docker de dos nodos LocalSync LAN")
    parser.add_argument("--status", action="store_true", help="Mostrar contenedores y registros")
    parser.add_argument("--cleanup", action="store_true", help="Detener y borrar volúmenes virtuales")
    parser.add_argument("--cleanup-after", action="store_true", help="Limpiar al finalizar (CI)")
    args = parser.parse_args()
    if not shutil.which("docker"):
        print("ERROR: no se encontró Docker. Instala/abre Docker Desktop (o Docker Engine).", file=sys.stderr)
        return 2

    env = os.environ.copy()
    # Token efímero para el laboratorio; nunca se escribe a disco ni a Git.
    env.setdefault("LOCALSYNC_AUTH_TOKEN", secrets.token_hex(32))
    if len(env["LOCALSYNC_AUTH_TOKEN"]) < 16:
        print("ERROR: LOCALSYNC_AUTH_TOKEN debe tener 16 caracteres o más.", file=sys.stderr)
        return 2

    try:
        if args.cleanup:
            ejecutar_compose(env, "down", "-v", "--remove-orphans")
            print("Entorno virtual eliminado (incluye los datos de prueba).")
        elif args.status:
            ejecutar_compose(env, "ps", "-a")
            ejecutar_compose(env, "logs", "--tail", "30", "nodo-a", "nodo-b")
        else:
            demo(env)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError, AssertionError, OSError) as exc:
        print(f"\n[ERROR] Auditoría virtual fallida: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.cleanup_after and not args.cleanup:
            try:
                ejecutar_compose(env, "down", "-v", "--remove-orphans")
            except Exception as exc:
                print(f"Advertencia: no se pudo limpiar el entorno: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
