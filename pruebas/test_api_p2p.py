"""Pruebas aisladas de los endpoints P2P de FastAPI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from src.backend.api import p2p_routes


class TestApiP2P(unittest.TestCase):
    @patch("src.backend.api.p2p_routes.comprobar_conexion", return_value=True)
    def test_conexion_disponible(self, comprobar):
        resultado = p2p_routes.consultar_conexion()
        self.assertTrue(resultado["conectado"])
        comprobar.assert_called_once_with("127.0.0.1", 9001, timeout=2.0)

    @patch("src.backend.api.p2p_routes.comprobar_conexion", side_effect=ConnectionRefusedError("rechazada"))
    def test_conexion_no_disponible(self, comprobar):
        self.assertFalse(p2p_routes.consultar_conexion()["conectado"])

    def test_rechazar_traversal(self):
        for nombre in ("../secreto.txt", "..\\secreto.txt", ".."):
            with self.subTest(nombre=nombre), self.assertRaises(HTTPException) as error:
                p2p_routes.enviar_archivo_local(p2p_routes.SolicitudArchivo(nombre=nombre))
            self.assertEqual(error.exception.status_code, 400)

    def test_archivo_inexistente(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(p2p_routes, "CARPETA_ENVIO", Path(tmp)):
                with self.assertRaises(HTTPException) as error:
                    p2p_routes.enviar_archivo_local(p2p_routes.SolicitudArchivo(nombre="no_existe.txt"))
                self.assertEqual(error.exception.status_code, 404)

    @patch("src.backend.api.p2p_routes.enviar_archivo", return_value=True)
    def test_envio_archivo(self, enviar):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            (carpeta / "prueba.txt").write_text("LocalSync", encoding="utf-8")
            with patch.object(p2p_routes, "CARPETA_ENVIO", carpeta):
                resultado = p2p_routes.enviar_archivo_local(p2p_routes.SolicitudArchivo(nombre="prueba.txt"))
        self.assertTrue(resultado["enviado"])
        enviar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
