"""Prueba de integración con dos nodos TCP independientes en un mismo equipo.

Sirve como prueba automatizada de intercambio manual en ambos sentidos.
NO sustituye la demostración real con dos computadores en la misma LAN.
"""
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from src.backend.core.engine import calcular_sha256
from src.backend.network.cliente_tcp import comprobar_conexion, enviar_archivo
from src.backend.network.p2p_socket import NodoP2PTCP


class TestDosNodosTCP(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.base = Path(temporal.name)
        self.carpeta_a = self.base / "equipo_a"
        self.carpeta_b = self.base / "equipo_b"
        self.carpeta_a.mkdir()
        self.carpeta_b.mkdir()
        self.nodo_a = self._iniciar_nodo(self.carpeta_a)
        self.nodo_b = self._iniciar_nodo(self.carpeta_b)

    def _iniciar_nodo(self, carpeta):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            puerto = s.getsockname()[1]
        nodo = NodoP2PTCP("127.0.0.1", puerto, carpeta)
        detener = threading.Event()
        listo = threading.Event()
        hilo = threading.Thread(
            target=nodo.servir,
            args=(detener, listo),
            daemon=True,
        )
        hilo.start()

        def cerrar():
            detener.set()
            hilo.join(timeout=3)
            self.assertFalse(hilo.is_alive(), "El nodo TCP no se detuvo")

        self.addCleanup(cerrar)
        self.assertTrue(listo.wait(3), "El nodo TCP no inició")
        return nodo

    def test_intercambio_bidireccional_manual_verifica_sha256(self):
        archivo_a = self.carpeta_a / "origen_a.txt"
        archivo_a.write_text("Archivo creado en el equipo A", encoding="utf-8")
        archivo_b = self.carpeta_b / "origen_b.bin"
        archivo_b.write_bytes(bytes(range(256)) * 40)

        self.assertTrue(comprobar_conexion("127.0.0.1", self.nodo_a.port))
        self.assertTrue(comprobar_conexion("127.0.0.1", self.nodo_b.port))

        self.assertTrue(enviar_archivo(archivo_a, "127.0.0.1", self.nodo_b.port))
        self.assertTrue(enviar_archivo(archivo_b, "127.0.0.1", self.nodo_a.port))

        copia_en_b = self.carpeta_b / archivo_a.name
        copia_en_a = self.carpeta_a / archivo_b.name
        self.assertEqual(copia_en_b.read_bytes(), archivo_a.read_bytes())
        self.assertEqual(copia_en_a.read_bytes(), archivo_b.read_bytes())
        self.assertEqual(calcular_sha256(copia_en_b), calcular_sha256(archivo_a))
        self.assertEqual(calcular_sha256(copia_en_a), calcular_sha256(archivo_b))


if __name__ == "__main__":
    unittest.main()
