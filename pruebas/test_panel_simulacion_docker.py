"""Integración de la API del panel con Docker real; solo para CI dedicado.

Se omite en pytest regular. El job Docker la ejecuta con
LOCALSYNC_DOCKER_E2E=1 después de la suite de sockets normal.
"""
import os
import time
import unittest

from fastapi.testclient import TestClient
from src.backend.api.routes import app


@unittest.skipUnless(os.getenv("LOCALSYNC_DOCKER_E2E") == "1",
                     "Requiere Docker Engine; disponible en job laboratorio-docker.")
class TestSimulacionDesdeGUI(unittest.TestCase):
    def test_ejecutar_y_limpiar_laboratorio_desde_api(self):
        with TestClient(app) as cliente:
            try:
                response = cliente.post("/api/lan/simulacion/iniciar", json={})
                self.assertEqual(response.status_code, 200, response.text)
                estado = None
                for _ in range(240):
                    estado = cliente.get("/api/lan/simulacion/estado").json()
                    if estado["estado"] != "ejecutando":
                        break
                    time.sleep(1)
                self.assertEqual(estado["estado"], "aprobado",
                                 "\n".join(estado.get("salida", [])[-45:]))
                self.assertEqual(estado["codigo"], 0)
                salida = "\n".join(estado["salida"])
                self.assertIn("AUDITORÍA VIRTUAL APROBADA", salida)
                self.assertIn("[OK] A -> B", salida)
                self.assertIn("[OK] B -> A", salida)
                evidencia = cliente.get("/api/lan/simulacion/evidencia")
                self.assertEqual(evidencia.status_code, 200)
                self.assertIn("AUDITORÍA VIRTUAL APROBADA", evidencia.text)
            finally:
                limpieza = cliente.post("/api/lan/simulacion/limpiar", json={})
                if limpieza.status_code == 200:
                    for _ in range(90):
                        estado = cliente.get("/api/lan/simulacion/estado").json()
                        if estado["estado"] != "ejecutando":
                            break
                        time.sleep(1)
                    self.assertEqual(estado["estado"], "sin_ejecutar",
                                     "\n".join(estado.get("salida", [])[-25:]))
