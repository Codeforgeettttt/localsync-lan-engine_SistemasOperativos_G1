"""Valida CREATE_RESUME tras caída real del socket y tras reintento completo."""
import hashlib
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from src.backend.network.cliente_tcp import enviar_archivo
from src.backend.network.p2p_socket import NodoP2PTCP


def free_port():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1",0))
        return sock.getsockname()[1]


class TestResume(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.dest=self.base/"recibidos"
        self.dest.mkdir()
        self.port=free_port()
        self.stop=threading.Event()
        ready=threading.Event()
        self.node=NodoP2PTCP("127.0.0.1",self.port,self.dest)
        self.thread=threading.Thread(target=self.node.servir,args=(self.stop,ready),daemon=True)
        self.thread.start()
        self.addCleanup(self._shutdown)
        self.assertTrue(ready.wait(5))

    def _shutdown(self):
        self.stop.set()
        self.thread.join(timeout=5)

    def test_reanudar_tras_caida_con_sha_y_bytes_identicos(self):
        src=self.base/"origen.bin"
        data=bytes(range(256))*400
        src.write_bytes(data)
        sha=hashlib.sha256(data).hexdigest()
        packet=self.node.crear_mensaje_control("CREATE_RESUME","anidada/origen.bin",sha,len(data))
        with socket.create_connection(("127.0.0.1",self.port),timeout=5) as s:
            s.settimeout(5)
            self.node.enviar_trama(s,packet)
            offer=self.node.decodificar_mensaje_control(self.node.recibir_trama(s))
            self.assertEqual(offer["operacion"],"ACK")
            self.assertEqual(offer["tamano_bytes"],0)
            s.sendall(data[:10000])
            # Forzar cierre TCP con cuerpo incompleto.
        partials=self.dest/".localsync_partials"
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            files=list(partials.glob("*.part")) if partials.is_dir() else []
            if files and files[0].stat().st_size==10000:
                break
            time.sleep(.05)
        self.assertTrue(files)
        self.assertEqual(files[0].stat().st_size,10000)
        self.assertTrue(enviar_archivo(src,"127.0.0.1",self.port,
            ruta_remota="anidada/origen.bin",reintentos=2,reanudar=True))
        got=self.dest/"anidada"/"origen.bin"
        self.assertEqual(got.read_bytes(),data)
        self.assertEqual(list(partials.glob("*.part")),[])

        # El emisor repite la misma operación: offset=tamaño, 0 bytes nuevos.
        self.assertTrue(enviar_archivo(src,"127.0.0.1",self.port,
            ruta_remota="anidada/origen.bin",reanudar=True))
        self.assertEqual(got.read_bytes(),data)

    def test_integridad_de_otro_hash_crea_conflicto(self):
        src=self.base/"documento.txt"
        src.write_text("primer contenido",encoding="utf-8")
        self.assertTrue(enviar_archivo(src,"127.0.0.1",self.port,reanudar=True))
        src.write_text("segunda versión diferente",encoding="utf-8")
        self.assertTrue(enviar_archivo(src,"127.0.0.1",self.port,reanudar=True))
        self.assertEqual((self.dest/"documento.txt").read_text(encoding="utf-8"),"primer contenido")
        conflicts=list(self.dest.glob("documento.conflict-*.txt"))
        self.assertEqual(len(conflicts),1)
        self.assertEqual(conflicts[0].read_text(encoding="utf-8"),"segunda versión diferente")


if __name__=="__main__":
    unittest.main()
