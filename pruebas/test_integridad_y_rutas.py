"""
Suite de Pruebas Reproducibles de Fase 1 - LocalSync (Grupo G1)
Integrantes Oficiales:
  - Valery Michell Herrera Roca
  - Daniel Felipe Rojas Gonzales

Compatible con `pytest -v` y `python3 -m unittest`.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.backend.core.engine import calcular_sha256, validar_ruta_segura, MotorSincronizacionLocal
from src.backend.network.p2p_socket import NodoP2PTCP
from src.backend.storage.db_manager import GestorBaseDatosLocal


class TestLocalSyncFase1(unittest.TestCase):
    def test_calculo_sha256_consistente(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            archivo_prueba = Path(tmp_dir) / "documento_prueba.txt"
            archivo_prueba.write_bytes(b"Contenido verificable LocalSync Sistemas Operativos G1")
            h1 = calcular_sha256(archivo_prueba)
            h2 = calcular_sha256(archivo_prueba)
            self.assertEqual(len(h1), 64)
            self.assertEqual(h1, h2)

    def test_calculo_sha256_archivo_inexistente(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                calcular_sha256(Path(tmp_dir) / "no_existe.bin")

    def test_bloqueo_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "carpeta_autorizada"
            base.mkdir()
            self.assertTrue(validar_ruta_segura(base, "subcarpeta/informe.pdf"))
            self.assertFalse(validar_ruta_segura(base, "../../etc/passwd"))
            self.assertFalse(validar_ruta_segura(base, "/etc/shadow"))
            self.assertFalse(validar_ruta_segura(base, ""))

    def test_nodo_p2p_constructor_y_serializacion(self):
        nodo = NodoP2PTCP(host="127.0.0.1", port=9001)
        self.assertEqual(nodo.host, "127.0.0.1")
        self.assertEqual(nodo.port, 9001)
        self.assertFalse(nodo.transporte_tcp_activo)

        hash_ejemplo = "a" * 64
        trama = nodo.crear_mensaje_control("CREATE", "docs/guia.pdf", hash_ejemplo, 2048)
        decodificado = NodoP2PTCP.decodificar_mensaje_control(trama)
        self.assertEqual(decodificado["protocolo"], "LOCALSYNC_P2P_V1")
        self.assertEqual(decodificado["operacion"], "CREATE")
        self.assertEqual(decodificado["ruta_relativa"], "docs/guia.pdf")
        self.assertEqual(decodificado["hash_sha256"], hash_ejemplo)
        self.assertEqual(decodificado["tamano_bytes"], 2048)

    def test_sqlite_restriccion_compuesta_carpeta_ruta(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test_localsync.db"
            schema_path = Path(__file__).resolve().parent.parent / "src" / "bd" / "schema.sql"
            gestor = GestorBaseDatosLocal(db_file)
            gestor.inicializar_esquema(schema_path)

            resumen_inicial = gestor.obtener_resumen_bd()
            self.assertTrue(resumen_inicial["bd_inicializada"])
            self.assertEqual(len(resumen_inicial["tablas_detectadas"]), 6)

            id_carpeta_1 = gestor.registrar_carpeta_autorizada("/home/ubuntu/carpeta_a", "Carpeta A")
            id_carpeta_2 = gestor.registrar_carpeta_autorizada("/home/ubuntu/carpeta_b", "Carpeta B")
            hash_valido = "b" * 64

            id_arch_1 = gestor.registrar_archivo_sincronizado(id_carpeta_1, "notas/tema1.txt", hash_valido, 120, 1700000000.0)
            id_arch_2 = gestor.registrar_archivo_sincronizado(id_carpeta_2, "notas/tema1.txt", hash_valido, 120, 1700000000.0)
            self.assertNotEqual(id_arch_1, id_arch_2)

            with self.assertRaises(sqlite3.IntegrityError):
                gestor.registrar_archivo_sincronizado(id_carpeta_1, "notas/tema1.txt", hash_valido, 150, 1700000005.0)

    def test_estado_motor_local_transparente(self):
        motor = MotorSincronizacionLocal()
        estado = motor.obtener_estado_motor()
        self.assertFalse(estado["watchdog_activo"])
        self.assertTrue(estado["sha256_operativo"])


if __name__ == "__main__":
    unittest.main()
