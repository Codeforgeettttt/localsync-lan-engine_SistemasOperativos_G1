"""Pruebas de transferencia de archivos por TCP en localhost."""
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from src.backend.network.cliente_tcp import enviar_archivo
from src.backend.network.p2p_socket import NodoP2PTCP


class TestTransferenciaTCP(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.base = Path(self.temporal.name)
        self.destino = self.base / "recibidos"
        self.destino.mkdir()
        with socket.socket() as temporal:
            temporal.bind(("127.0.0.1", 0))
            puerto = temporal.getsockname()[1]
        self.nodo = NodoP2PTCP("127.0.0.1", puerto, self.destino)
        self.detener = threading.Event()
        listo = threading.Event()
        self.hilo = threading.Thread(target=self.nodo.servir, args=(self.detener, listo), daemon=True)
        self.hilo.start()
        self.assertTrue(listo.wait(3))

    def tearDown(self):
        self.detener.set()
        self.hilo.join(timeout=3)
        self.assertFalse(self.hilo.is_alive())

    def test_archivo_texto(self):
        origen = self.base / "Archivo de prueba.txt"
        origen.write_text("Texto de prueba para la comunicación 123123 probando", encoding="utf-8")
        self.assertTrue(enviar_archivo(origen, "127.0.0.1", self.nodo.port))
        self.assertEqual((self.destino / origen.name).read_bytes(), origen.read_bytes())

    def test_archivo_binario(self):
        origen = self.base / "datos.bin"
        origen.write_bytes(bytes(range(256)) * 400)
        self.assertTrue(enviar_archivo(origen, "127.0.0.1", self.nodo.port))
        self.assertEqual((self.destino / origen.name).read_bytes(), origen.read_bytes())

    def test_ruta_no_autorizada(self):
        from src.backend.network.transferencia import recibir_archivo
        with self.assertRaises(ValueError):
            recibir_archivo(None, {
                "ruta_relativa": "../fuera.txt", "tamano_bytes": 1, "hash_sha256": "0" * 64
            }, self.destino)
        self.assertFalse((self.base / "fuera.txt").exists())

    def test_transferencia_interrumpida(self):
        from src.backend.network.transferencia import recibir_archivo
        from hashlib import sha256
        receptor, emisor = socket.socketpair()
        try:
            emisor.sendall(b"parcial")
            emisor.shutdown(socket.SHUT_WR)
            with self.assertRaises(ConnectionError):
                recibir_archivo(receptor, {
                    "ruta_relativa": "cortado.txt", "tamano_bytes": 100,
                    "hash_sha256": sha256(b"parcial").hexdigest()
                }, self.destino)
        finally:
            receptor.close()
            emisor.close()
        self.assertFalse((self.destino / "cortado.txt").exists())
        self.assertEqual(list(self.destino.glob(".localsync-*")), [])


if __name__ == "__main__":
    unittest.main()
