"""La demo local es reproducible sin Docker ni WSL."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_simulacion_local_dos_nodos_tcp_sin_docker():
    resultado = subprocess.run(
        [sys.executable, str(ROOT / "simulacion" / "demo_local.py")],
        cwd=ROOT, text=True, capture_output=True, timeout=45,
    )
    assert resultado.returncode == 0, resultado.stdout + "\n" + resultado.stderr
    for texto in ("PRUEBA LOCAL APROBADA", "[OK] A -> B",
                  "[OK] B -> A", "[OK] Archivo conflictivo",
                  "Conexiones autenticadas"):
        assert texto in resultado.stdout, texto
