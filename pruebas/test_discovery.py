"""Pruebas del descubrimiento UDP autenticado sin registrar pares."""
import socket
import unittest

from src.backend.network.discovery import DiscoveryResponder, discover


class TestDiscovery(unittest.TestCase):
    def test_descubre_con_token_correcto(self):
        token="shared-secret-test-token-2026"
        srv=DiscoveryResponder(token, tcp_port=9101,udp_port=0,name="nodo-prueba")
        try:
            udp=srv.start()
            result=discover(token,udp_port=udp,timeout=.4,targets=("127.0.0.1",))
            self.assertTrue(any(item["puerto"]==9101 and item["nombre"]=="nodo-prueba"
                                for item in result),result)
            bad=discover("secret-distinto-de-20-caracteres",udp_port=udp,
                         timeout=.2,targets=("127.0.0.1",))
            self.assertEqual(bad,[])
        finally:
            srv.stop()

    def test_sin_clave_rechazado(self):
        with self.assertRaises(ValueError):
            discover("corta",udp_port=9002,targets=("127.0.0.1",))


if __name__=="__main__":
    unittest.main()
