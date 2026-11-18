"""Prueba opcional de navegador real de LocalSync con Playwright.

Solo se ejecuta en GitHub Actions cuando LOCALSYNC_BROWSER_E2E=1.
Antes de ejecutar se inicia Uvicorn en http://127.0.0.1:8080.
Guarda capturas como artefactos de la auditoría.
"""
import os
from pathlib import Path
import unittest

@unittest.skipUnless(os.getenv("LOCALSYNC_BROWSER_E2E") == "1",
                     "Prueba visual reservada para el trabajo de CI navegador")
class TestInterfazEnNavegador(unittest.TestCase):
    def test_recorrido_real_en_chrome(self):
        from playwright.sync_api import sync_playwright

        directorio = Path("evidencias_gui")
        directorio.mkdir(exist_ok=True)
        with sync_playwright() as p:
            if os.getenv("LOCALSYNC_CHROME_CHANNEL") == "chrome":
                navegador = p.chromium.launch(channel="chrome", headless=True,
                                              args=["--no-sandbox"])
            else:
                navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = navegador.new_page(viewport={"width": 1440, "height": 900},
                                          device_scale_factor=1)
                errores = []
                page.on("pageerror", lambda error: errores.append(str(error)))
                page.goto("http://127.0.0.1:8080/", wait_until="networkidle")
                self.assertIn("LocalSync", page.title())
                page.locator("#statReceiver").wait_for()
                page.screenshot(path=str(directorio / "01_resumen.png"), full_page=True)

                page.locator('[data-nav="transferir"]').click()
                page.locator("#startReceiver").click()
                page.wait_for_function(
                    "document.getElementById('receiverBadge').textContent === 'EN LÍNEA'")
                page.locator("#checkConnection").click()
                page.wait_for_function(
                    "document.getElementById('connectionBadge').textContent === 'CONECTADO'")
                page.locator("#uploadFiles").set_input_files({
                    "name": "auditoria.txt",
                    "mimeType": "text/plain",
                    "buffer": b"Archivo de prueba E2E LocalSync",
                })
                page.wait_for_function(
                    "document.getElementById('outgoingFiles').textContent.includes('auditoria.txt')")
                page.locator("#outgoingFiles button").first.click()
                page.wait_for_function(
                    "document.getElementById('incomingFiles').textContent.includes('auditoria.txt')")
                page.screenshot(path=str(directorio / "02_transferencia_real.png"), full_page=True)
                # Probar gestión de archivos desde botones reales del navegador.
                page.locator("#incomingFiles button").filter(has_text="SHA-256").first.click()
                page.wait_for_function(
                    "document.getElementById('incomingFiles').textContent.includes('SHA-256:')")
                page.once("dialog", lambda dialog: dialog.accept("auditoria-verificada.txt"))
                page.locator("#incomingFiles button").filter(has_text="Renombrar").first.click()
                page.wait_for_function(
                    "document.getElementById('incomingFiles').textContent.includes('auditoria-verificada.txt')")
                page.screenshot(path=str(directorio / "04_archivo_verificado.png"), full_page=True)
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator("#incomingFiles .btn-danger").first.click()
                page.wait_for_function(
                    "!document.getElementById('incomingFiles').textContent.includes('auditoria-verificada.txt')")
                page.locator("#stopReceiver").click()
                page.wait_for_function(
                    "document.getElementById('receiverBadge').textContent === 'APAGADO'")

                page.locator('[data-nav="laboratorio"]').click()
                self.assertTrue(page.locator("#runSimulation").is_visible())
                page.screenshot(path=str(directorio / "03_laboratorio.png"), full_page=True)
                page.locator("#runLocalSimulation").click()
                page.wait_for_function(
                    "document.getElementById('labLog').textContent.includes('PRUEBA LOCAL APROBADA')",
                    timeout=60000)
                page.screenshot(path=str(directorio / "05_prueba_local_sin_docker.png"), full_page=True)
                self.assertFalse(errores, "Errores JavaScript: "+repr(errores))
            finally:
                navegador.close()


if __name__ == "__main__":
    unittest.main()
