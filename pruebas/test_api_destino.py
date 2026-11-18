import unittest
from unittest.mock import patch
from fastapi import HTTPException
from src.backend.api import p2p_routes


class TestDestinoP2P(unittest.TestCase):
    def test_localhost(self):
        p2p_routes.validar_destino("127.0.0.1", 9001)

    @patch.dict("os.environ", {"LOCALSYNC_PAR_LAN": "192.168.1.20"})
    @patch("src.backend.api.p2p_routes.comprobar_conexion", return_value=True)
    def test_par_autorizado(self, comprobar):
        self.assertTrue(p2p_routes.consultar_conexion("192.168.1.20", 9002)["conectado"])
        comprobar.assert_called_once_with("192.168.1.20", 9002, timeout=2.0)

    @patch.dict("os.environ", {"LOCALSYNC_PAR_LAN": ""})
    def test_par_no_autorizado(self):
        with self.assertRaises(HTTPException) as error:
            p2p_routes.validar_destino("192.168.1.20", 9001)
        self.assertEqual(error.exception.status_code, 403)

    def test_destino_invalido(self):
        for host, puerto in [("8.8.8.8", 9001), ("localhost", 9001), ("127.0.0.1", 80)]:
            with self.subTest(host=host, puerto=puerto), self.assertRaises(HTTPException) as error:
                p2p_routes.validar_destino(host, puerto)
            self.assertEqual(error.exception.status_code, 400)
