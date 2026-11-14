"""Pruebas del cliente TCP contra un servidor local real."""
import socket
import threading
import unittest

from src.backend.network.cliente_tcp import comprobar_conexion
from src.backend.network.p2p_socket import NodoP2PTCP


class TestClienteTCP(unittest.TestCase):
    def setUp(self):
        with socket.socket() as temporal:
            temporal.bind(("127.0.0.1", 0))
            puerto = temporal.getsockname()[1]
        self.nodo = NodoP2PTCP("127.0.0.1", puerto)
        self.detener = threading.Event()
        listo = threading.Event()
        self.hilo = threading.Thread(target=self.nodo.servir, args=(self.detener, listo), daemon=True)
        self.hilo.start()
        self.assertTrue(listo.wait(3), "El servidor de prueba no inició")

    def tearDown(self):
        self.detener.set()
        self.hilo.join(timeout=3)
        self.assertFalse(self.hilo.is_alive())

    def test_conexion_ping_ack(self):
        self.assertTrue(comprobar_conexion("127.0.0.1", self.nodo.port))

    def test_servidor_no_disponible(self):
        with socket.socket() as temporal:
            temporal.bind(("127.0.0.1", 0))
            puerto_sin_servidor = temporal.getsockname()[1]
            with self.assertRaises(OSError):
                comprobar_conexion("127.0.0.1", puerto_sin_servidor, timeout=0.5)

    def test_host_invalido(self):
        with self.assertRaises(ValueError):
            comprobar_conexion("", self.nodo.port)

    def test_puerto_invalido(self):
        with self.assertRaises(ValueError):
            comprobar_conexion("127.0.0.1", 10)


if __name__ == "__main__":
    unittest.main()
