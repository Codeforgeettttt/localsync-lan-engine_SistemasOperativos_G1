"""Pruebas de integración del transporte TCP, sin red externa ni cloud."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from src.backend.network.cliente_tcp import comprobar_conexion, enviar_archivo, enviar_carpeta
from src.backend.network.p2p_socket import NodoP2PTCP

TOKEN = "token_compartido_seguro_de_pruebas_12345"


class TestMotorLANCompleto(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.base = Path(temporal.name)
        self.origen = self.base / "origen"
        self.destino = self.base / "destino"
        self.origen.mkdir()
        self.destino.mkdir()

    def crear_nodo(self, *, token=None, on_conflict="keep-both", tls_cert=None, tls_key=None):
        with socket.socket() as temporal:
            temporal.bind(("127.0.0.1", 0))
            puerto = temporal.getsockname()[1]
        nodo = NodoP2PTCP("127.0.0.1", puerto, self.destino,
                          auth_token=token, on_conflict=on_conflict,
                          tls_cert=tls_cert, tls_key=tls_key)
        detener = threading.Event()
        listo = threading.Event()
        hilo = threading.Thread(target=nodo.servir, args=(detener, listo), daemon=True)
        hilo.start()
        self.assertTrue(listo.wait(3), "Servidor no inició")
        def cerrar():
            detener.set()
            hilo.join(timeout=5)
            self.assertFalse(hilo.is_alive(), "Servidor no cerró limpiamente")
        self.addCleanup(cerrar)
        return nodo

    def test_autenticacion_correcta_y_rechazo_incorrecta(self):
        nodo = self.crear_nodo(token=TOKEN)
        self.assertTrue(comprobar_conexion("127.0.0.1", nodo.port, auth_token=TOKEN))
        with self.assertRaises((PermissionError, ValueError, ConnectionError)):
            comprobar_conexion("127.0.0.1", nodo.port, auth_token="token_incorrecto_de_prueba_123")
        with self.assertRaises((PermissionError, ValueError, ConnectionError)):
            comprobar_conexion("127.0.0.1", nodo.port)
        archivo = self.origen / "datos.txt"
        archivo.write_text("datos autenticados", encoding="utf-8")
        self.assertTrue(enviar_archivo(archivo, "127.0.0.1", nodo.port, auth_token=TOKEN))
        self.assertEqual((self.destino / archivo.name).read_bytes(), archivo.read_bytes())

    def test_conflicto_conserva_original_y_version(self):
        nodo = self.crear_nodo()
        archivo = self.origen / "informe.txt"
        archivo.write_text("versión original", encoding="utf-8")
        self.assertTrue(enviar_archivo(archivo, "127.0.0.1", nodo.port))
        archivo.write_text("versión modificada", encoding="utf-8")
        self.assertTrue(enviar_archivo(archivo, "127.0.0.1", nodo.port))
        self.assertEqual((self.destino / "informe.txt").read_text(encoding="utf-8"), "versión original")
        copias = list(self.destino.glob("informe.conflict-*.txt"))
        self.assertEqual(len(copias), 1)
        self.assertEqual(copias[0].read_text(encoding="utf-8"), "versión modificada")
        self.assertTrue(enviar_archivo(archivo, "127.0.0.1", nodo.port))
        self.assertEqual(len(list(self.destino.glob("informe.conflict-*.txt"))), 1)
        self.assertEqual(list(self.destino.glob(".localsync-*")), [])

    def test_politica_rechazar_y_sin_sobrescritura(self):
        nodo = self.crear_nodo(on_conflict="reject")
        archivo = self.origen / "unico.txt"
        archivo.write_text("primero", encoding="utf-8")
        enviar_archivo(archivo, "127.0.0.1", nodo.port)
        archivo.write_text("segundo", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Archivo distinto"):
            enviar_archivo(archivo, "127.0.0.1", nodo.port)
        self.assertEqual((self.destino / "unico.txt").read_text(), "primero")

    def test_carpeta_recursiva_y_sin_symlinks(self):
        nodo = self.crear_nodo(token=TOKEN)
        (self.origen / "subcarpeta").mkdir()
        (self.origen / "subcarpeta" / "reporte.txt").write_text("archivo anidado")
        (self.origen / "vacio.bin").write_bytes(b"")
        (self.origen / "binario.dat").write_bytes(bytes(range(256)) * 12)
        bien, mal = enviar_carpeta(self.origen, "127.0.0.1", nodo.port,
                                  auth_token=TOKEN, prefijo_remoto="carpeta_compartida")
        self.assertEqual((bien, mal), (3, 0))
        for ruta in self.origen.rglob("*"):
            if ruta.is_file():
                copia = self.destino / "carpeta_compartida" / ruta.relative_to(self.origen)
                self.assertEqual(copia.read_bytes(), ruta.read_bytes())

    def test_ruta_traversal_rechazada(self):
        nodo = self.crear_nodo()
        archivo = self.origen / "archivo.txt"
        archivo.write_text("intento de traversal")
        for ruta in ["../fuera.txt", "/tmp/absoluto.txt", "x/../../fuera.txt", "..\\fuera.txt"]:
            with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                enviar_archivo(archivo, "127.0.0.1", nodo.port, ruta_remota=ruta)
        self.assertFalse((self.base / "fuera.txt").exists())

    def test_concurrencia_receptor_responde_a_varios_clientes(self):
        nodo = self.crear_nodo(token=TOKEN)
        archivos = []
        for i in range(8):
            ruta = self.origen / f"archivo_{i}.bin"
            ruta.write_bytes(os.urandom(16384 + i * 32))
            archivos.append(ruta)
        with ThreadPoolExecutor(max_workers=8) as pool:
            salidas = list(pool.map(lambda p: enviar_archivo(p, "127.0.0.1", nodo.port, auth_token=TOKEN), archivos))
        self.assertTrue(all(salidas))
        for archivo in archivos:
            self.assertEqual((self.destino / archivo.name).read_bytes(), archivo.read_bytes())

    def test_validar_servidor_no_seguro_rechazado_por_defecto(self):
        with self.assertRaisesRegex(ValueError, "LOCALSYNC_AUTH_TOKEN"):
            NodoP2PTCP("0.0.0.0", 9001, self.destino)
        nodo = NodoP2PTCP("0.0.0.0", 9001, self.destino, insecure_lan=True)
        self.assertFalse(nodo.tls_activo)

    @unittest.skipUnless(shutil.which("openssl"), "openssl no disponible")
    def test_tls_y_autenticacion(self):
        cert = self.base / "server.crt"
        key = self.base / "server.key"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        nodo = self.crear_nodo(token=TOKEN, tls_cert=str(cert), tls_key=str(key))
        self.assertTrue(comprobar_conexion("127.0.0.1", nodo.port, auth_token=TOKEN,
                                          tls_ca=str(cert)))
        archivo = self.origen / "cifrado.txt"
        archivo.write_text("prueba TLS")
        self.assertTrue(enviar_archivo(archivo, "127.0.0.1", nodo.port,
                                     auth_token=TOKEN, tls_ca=str(cert)))
        self.assertEqual((self.destino / archivo.name).read_bytes(), archivo.read_bytes())


if __name__ == "__main__":
    unittest.main()
