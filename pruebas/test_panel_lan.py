"""Pruebas end-to-end del panel FastAPI contra un socket TCP REAL en localhost.

No requieren Docker ni dos máquinas. El laboratorio de dos contenedores se
ejecuta en el otro job de GitHub Actions.
"""
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.backend.api.routes import app
from src.backend.api import lan_routes


class TestPanelLAN(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.envios = self.base / "preparados"
        self.recibidos = self.base / "recibidos"
        self.patches = [
            patch.object(lan_routes, "ENVIO", self.envios),
            patch.object(lan_routes, "RECIBIDOS", self.recibidos),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _puerto_libre(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def test_interfaz_y_estado_real(self):
        ui = self.client.get("/")
        self.assertEqual(ui.status_code, 200)
        self.assertIn("LocalSync — Centro de control LAN", ui.text)
        self.assertIn("Ejecutar simulación completa", ui.text)
        self.assertEqual(self.client.get("/static/js/app.js").status_code, 200)
        self.assertEqual(self.client.get("/static/css/styles.css").status_code, 200)
        estado = self.client.get("/api/estado")
        self.assertEqual(estado.status_code, 200)
        self.assertIn("transferencia_tcp_manual", estado.json()["componentes_implementados"])
        self.assertIn("monitoreo_watchdog_inotify", estado.json()["componentes_pendientes"])

    def test_carga_rechaza_traversal_y_host_externo(self):
        r = self.client.post("/api/lan/archivos",
            files={"archivo": ("mal.txt", b"no", "text/plain")},
            data={"ruta": "../fuera.txt"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse((self.base / "fuera.txt").exists())
        for host in ("8.8.8.8", "https://example.org", "example.org"):
            r = self.client.post("/api/lan/conexion", json={"host":host,"puerto":9001})
            self.assertEqual(r.status_code, 400)

    def test_origen_web_externo_no_puede_ejecutar_acciones(self):
        r = self.client.post("/api/lan/receptor/iniciar",
                             json={"modo_lan":False,"puerto":9001},
                             headers={"origin":"https://sitio-ajeno.example"})
        self.assertEqual(r.status_code, 403)

    def test_subir_archivo_iniciar_receptor_y_transferir_desde_gui(self):
        puerto = self._puerto_libre()
        inicio = self.client.post("/api/lan/receptor/iniciar",
                                  json={"modo_lan":False,"puerto":puerto})
        self.assertEqual(inicio.status_code, 200, inicio.text)
        try:
            carpeta = self.client.post("/api/lan/archivos",
                files={"archivo": ("documento.txt", b"LocalSync control web", "text/plain")},
                data={"ruta":"carpeta/documento.txt"})
            self.assertEqual(carpeta.status_code, 200, carpeta.text)
            self.assertEqual(carpeta.json()["ruta"], "carpeta/documento.txt")
            ping = self.client.post("/api/lan/conexion",
                                    json={"host":"127.0.0.1","puerto":puerto})
            self.assertTrue(ping.json()["conectado"], ping.text)
            envio = self.client.post("/api/lan/enviar",
                json={"ruta":"carpeta/documento.txt","host":"127.0.0.1",
                      "puerto":puerto,"reintentos":0})
            self.assertEqual(envio.status_code, 200, envio.text)
            self.assertTrue(envio.json()["enviado"])
            self.assertEqual((self.recibidos/"carpeta"/"documento.txt").read_bytes(),
                             b"LocalSync control web")
            respuesta = self.client.get("/api/lan/descargar",
                                        params={"ruta":"carpeta/documento.txt"})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.content, b"LocalSync control web")
            estado = self.client.get("/api/lan/estado").json()
            self.assertTrue(estado["receptor"]["activo"])
            self.assertEqual(estado["envios"], 1)
            self.assertEqual(estado["recibidos"], 1)
            self.assertIn("ENVIO_OK", [e["tipo"] for e in estado["historial"]])
            self.assertIn("RECEPCION_OK", [e["tipo"] for e in estado["historial"]])
        finally:
            stop = self.client.post("/api/lan/receptor/detener", json={})
            self.assertEqual(stop.status_code, 200, stop.text)
            self.assertFalse(stop.json()["activo"])

    def test_carpeta_completa_y_destino_anidado(self):
        puerto = self._puerto_libre()
        r = self.client.post("/api/lan/receptor/iniciar",
                             json={"modo_lan":False, "puerto":puerto})
        self.assertEqual(r.status_code, 200, r.text)
        try:
            for nombre, dato in [("carpeta/a.txt", b"a"),("carpeta/sub/b.bin", b"\x00\x80\xfe")]:
                up = self.client.post("/api/lan/archivos",
                        files={"archivo": (Path(nombre).name, dato, "application/octet-stream")},
                        data={"ruta":nombre})
                self.assertEqual(up.status_code, 200, up.text)
            r = self.client.post("/api/lan/enviar-carpeta", json={
                "host":"127.0.0.1","puerto":puerto, "subcarpeta":"carpeta","prefijo":"respaldo"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["correctos"], 2)
            self.assertEqual(r.json()["errores"], 0)
            self.assertEqual((self.recibidos/"respaldo"/"a.txt").read_bytes(), b"a")
            self.assertEqual((self.recibidos/"respaldo"/"sub"/"b.bin").read_bytes(), b"\x00\x80\xfe")
        finally:
            self.client.post("/api/lan/receptor/detener", json={})

    def test_gestion_archivos_verificar_renombrar_eliminar_y_conflictos(self):
        dato = b"LocalSync archivo administrado"
        result = self.client.post("/api/lan/archivos",
            files={"archivo": ("informe.txt", dato, "text/plain")},
            data={"ruta": "grupo/informe.txt"})
        self.assertEqual(result.status_code, 200, result.text)

        sha = self.client.get("/api/lan/archivo/verificar",
                              params={"bandeja":"envios","ruta":"grupo/informe.txt"})
        self.assertEqual(sha.status_code, 200, sha.text)
        import hashlib
        self.assertEqual(sha.json()["sha256"], hashlib.sha256(dato).hexdigest())

        invalidos = ("../fuera.txt", "x/../../fuera.txt", "/etc/passwd")
        for mal in invalidos:
            with self.subTest(ruta=mal):
                self.assertEqual(self.client.request("DELETE", "/api/lan/archivo",
                    json={"bandeja":"envios","ruta":mal}).status_code, 400)

        renombrar = self.client.patch("/api/lan/archivo",json={
            "bandeja":"envios","ruta":"grupo/informe.txt","nuevo_nombre":"informe-final.txt"})
        self.assertEqual(renombrar.status_code, 200, renombrar.text)
        self.assertEqual(renombrar.json()["ruta"], "grupo/informe-final.txt")
        self.assertTrue((self.envios/"grupo"/"informe-final.txt").is_file())

        # El renombrado no acepta traversal ni sobrescribe un nombre existente.
        malformed = self.client.patch("/api/lan/archivo",json={
            "bandeja":"envios","ruta":"grupo/informe-final.txt","nuevo_nombre":"../malo.txt"})
        self.assertEqual(malformed.status_code, 400)
        otro = self.envios / "grupo" / "ocupado.txt"
        otro.write_bytes(b"no modificar")
        conflicto = self.client.patch("/api/lan/archivo",json={
            "bandeja":"envios","ruta":"grupo/informe-final.txt","nuevo_nombre":"ocupado.txt"})
        self.assertEqual(conflicto.status_code, 409)
        self.assertEqual(otro.read_bytes(), b"no modificar")

        eliminado = self.client.request("DELETE", "/api/lan/archivo",json={
            "bandeja":"envios","ruta":"grupo/informe-final.txt"})
        self.assertEqual(eliminado.status_code, 200, eliminado.text)
        self.assertFalse((self.envios/"grupo"/"informe-final.txt").exists())
        self.assertEqual(self.client.get("/api/lan/archivo/verificar",
            params={"bandeja":"envios","ruta":"grupo/informe-final.txt"}).status_code, 404)
        tipos = [x["tipo"] for x in self.client.get("/api/lan/estado").json()["historial"]]
        self.assertIn("ARCHIVO_ELIMINADO", tipos)
        self.assertIn("ARCHIVO_RENOMBRADO", tipos)

    def test_carga_demasiado_grande_limpia_temporales_y_estado_red(self):
        with patch.object(lan_routes, "MAX_FILE_SIZE", 4):
            resultado = self.client.post("/api/lan/archivos",
                files={"archivo": ("grande.bin", b"12345", "application/octet-stream")},
                data={"ruta":"grande.bin"})
        self.assertEqual(resultado.status_code, 413)
        self.assertFalse((self.envios/"grande.bin").exists())
        self.assertEqual(list(self.envios.rglob(".localsync-*")), [])
        red = self.client.get("/api/lan/red")
        self.assertEqual(red.status_code, 200)
        self.assertIn("ips_locales", red.json())

    def test_receptor_lan_exige_token(self):
        r = self.client.post("/api/lan/receptor/iniciar",
                             json={"modo_lan":True, "puerto":9001, "token":"corto"})
        self.assertEqual(r.status_code, 400)

    def test_demo_informa_ausencia_docker(self):
        with patch.object(lan_routes.shutil, "which", return_value=None):
            r = self.client.get("/api/lan/simulacion/estado")
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.json()["docker_disponible"])
            r = self.client.post("/api/lan/simulacion/iniciar", json={})
            self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
