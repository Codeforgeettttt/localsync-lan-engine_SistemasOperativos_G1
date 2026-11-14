"""Pruebas de comunicación TCP local para LocalSync."""
import socket
import struct
import threading
import unittest

from src.backend.network.p2p_socket import NodoP2PTCP


class TestServidorTCP(unittest.TestCase):
    def setUp(self):
        with socket.socket() as temporal:
            temporal.bind(("127.0.0.1", 0))
            puerto = temporal.getsockname()[1]
        self.nodo = NodoP2PTCP("127.0.0.1", puerto)
        self.detener = threading.Event()
        listo = threading.Event()
        self.hilo = threading.Thread(target=self.nodo.servir, args=(self.detener, listo), daemon=True)
        self.hilo.start()
        self.assertTrue(listo.wait(3))

    def tearDown(self):
        self.detener.set()
        self.hilo.join(timeout=3)
        self.assertFalse(self.hilo.is_alive())

    def test_ping_ack_por_socket_real(self):
        with socket.create_connection(("127.0.0.1", self.nodo.port), timeout=3) as cliente:
            ping = self.nodo.crear_mensaje_control("PING", "", "0" * 64, 0)
            self.nodo.enviar_trama(cliente, ping)
            respuesta = self.nodo.decodificar_mensaje_control(self.nodo.recibir_trama(cliente))
        self.assertEqual(respuesta["operacion"], "ACK")

    def test_trama_fragmentada(self):
        with socket.create_connection(("127.0.0.1", self.nodo.port), timeout=3) as cliente:
            ping = self.nodo.crear_mensaje_control("PING", "", "0" * 64, 0)
            trama = struct.pack("!I", len(ping)) + ping
            for parte in (trama[:2], trama[2:5], trama[5:]):
                cliente.sendall(parte)
            respuesta = self.nodo.decodificar_mensaje_control(self.nodo.recibir_trama(cliente))
        self.assertEqual(respuesta["operacion"], "ACK")

    def test_trama_invalida_no_detiene_servidor(self):
        with socket.create_connection(("127.0.0.1", self.nodo.port), timeout=3) as cliente:
            cliente.sendall(b"\xff\xff\xff\xff")
        with socket.create_connection(("127.0.0.1", self.nodo.port), timeout=3) as cliente:
            self.nodo.enviar_trama(cliente, self.nodo.crear_mensaje_control("PING", "", "0" * 64, 0))
            respuesta = self.nodo.decodificar_mensaje_control(self.nodo.recibir_trama(cliente))
        self.assertEqual(respuesta["operacion"], "ACK")


if __name__ == "__main__":
    unittest.main()
