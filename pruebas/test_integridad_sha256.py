"""Pruebas de integridad SHA-256 de LocalSync, sin servicios externos."""
import hashlib
import socket
import tempfile
import unittest
from pathlib import Path

from src.backend.core.engine import calcular_sha256
from src.backend.network.transferencia import recibir_archivo


class TestIntegridadSHA256(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.base = Path(self.temporal.name)

    def recibir_bytes(self, nombre, contenido, hash_esperado):
        receptor, emisor = socket.socketpair()
        try:
            emisor.sendall(contenido)
            emisor.shutdown(socket.SHUT_WR)
            return recibir_archivo(receptor, {
                "ruta_relativa": nombre,
                "tamano_bytes": len(contenido),
                "hash_sha256": hash_esperado,
            }, self.base)
        finally:
            receptor.close()
            emisor.close()

    def test_hash_correcto(self):
        contenido = b"LocalSync: prueba de integridad"
        archivo = self.base / "original.txt"
        archivo.write_bytes(contenido)
        esperado = hashlib.sha256(contenido).hexdigest()
        self.assertEqual(calcular_sha256(archivo), esperado)
        destino = self.recibir_bytes("copia.txt", contenido, esperado)
        self.assertEqual(destino.read_bytes(), contenido)
        self.assertEqual(calcular_sha256(destino), esperado)

    def test_modificacion_cambia_hash(self):
        original = b"Mensaje original"
        modificado = b"Mensaje original!"
        self.assertNotEqual(
            hashlib.sha256(original).hexdigest(),
            hashlib.sha256(modificado).hexdigest(),
        )
        with self.assertRaisesRegex(ValueError, "SHA-256 no coincide"):
            self.recibir_bytes("alterado.txt", modificado, hashlib.sha256(original).hexdigest())
        self.assertFalse((self.base / "alterado.txt").exists())

    def test_archivo_vacio(self):
        esperado = hashlib.sha256(b"").hexdigest()
        destino = self.recibir_bytes("vacio.txt", b"", esperado)
        self.assertEqual(destino.stat().st_size, 0)
        self.assertEqual(calcular_sha256(destino), esperado)

    def test_archivo_rechazado_sin_temporales(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 no coincide"):
            self.recibir_bytes("rechazado.bin", b"contenido", "0" * 64)
        self.assertFalse((self.base / "rechazado.bin").exists())
        self.assertEqual(list(self.base.glob(".localsync-*")), [])

    def test_archivo_existente_no_se_sobrescribe(self):
        destino = self.base / "documento.txt"
        destino.write_bytes(b"version correcta")
        with self.assertRaisesRegex(ValueError, "SHA-256 no coincide"):
            self.recibir_bytes("documento.txt", b"version corrupta", "0" * 64)
        self.assertEqual(destino.read_bytes(), b"version correcta")
        self.assertEqual(list(self.base.glob(".localsync-*")), [])


if __name__ == "__main__":
    unittest.main()
