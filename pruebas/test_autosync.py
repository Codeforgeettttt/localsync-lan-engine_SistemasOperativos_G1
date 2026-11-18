"""Pruebas reales de sincronización en dos sockets, persistencia y seguridad."""
from pathlib import Path
import hashlib
import socket
import tempfile
import threading
import time
import unittest

from src.backend.sync.engine import AutoSync
from src.backend.network.p2p_socket import NodoP2PTCP


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0))
        return s.getsockname()[1]


class TestAutoSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "observados"
        self.received = self.root / "recibidos"
        self.out.mkdir(); self.received.mkdir()
        self.engine = AutoSync(self.out,self.root/"queue.db",self.root/"versions")
        self.addCleanup(self.engine.stop)
        self.port = port()
        self.token = "test_token_compartido_de_32_caracteres"
        self.event = threading.Event()
        self.ready = threading.Event()
        self.receiver = NodoP2PTCP("127.0.0.1",self.port,self.received,
                                   auth_token=self.token,allow_delete=True)
        self.thread = threading.Thread(target=self.receiver.servir,
                                       args=(self.event,self.ready),daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_receiver)
        self.assertTrue(self.ready.wait(4))
        self.peer_id = self.engine.add_peer("127.0.0.1",self.port,self.token)

    def _stop_receiver(self):
        self.event.set()
        self.thread.join(timeout=5)

    def _scan(self):
        self.engine.scan()
        self.engine.scan()

    def _until(self, callback, seconds=10):
        limit=time.monotonic()+seconds
        while time.monotonic()<limit:
            if callback():return True
            time.sleep(.1)
        return bool(callback())

    def test_detecta_y_transfiere_archivo_automaticamente(self):
        self.assertTrue(self.engine.start())
        src = self.out / "carpeta" / "ejemplo.txt"
        src.parent.mkdir()
        src.write_text("LocalSync autosync","utf-8")
        target=self.received/"carpeta"/"ejemplo.txt"
        self.assertTrue(self._until(lambda:target.is_file()))
        self.assertEqual(target.read_bytes(),src.read_bytes())
        self.assertEqual(self.engine.db.stats()["pendientes"],0)

    def test_cola_persistente_y_reintento_tras_reconexion(self):
        src=self.out/"pendiente.txt";src.write_text("en cola","utf-8")
        self._scan()
        self.assertEqual(self.engine.db.stats()["pendientes"],1)
        persisted=AutoSync(self.out,self.root/"queue.db",self.root/"versions")
        self.assertEqual(persisted.db.stats()["pendientes"],1)
        self.engine.dispatch()
        self.assertEqual((self.received/"pendiente.txt").read_bytes(),b"en cola")
        self.assertEqual(self.engine.db.stats()["pendientes"],0)

    def test_archiva_versiones_y_restaura(self):
        src=self.out/"version.txt";src.write_text("uno","utf-8")
        self._scan()
        src.write_text("dos diferente","utf-8")
        self._scan()
        history=self.engine.db.versions("version.txt")
        self.assertGreaterEqual(len(history),2)
        oldest=history[-1]
        self.assertEqual(hashlib.sha256(b"uno").hexdigest(),oldest["sha256"])
        self.engine.restore(oldest["id"])
        self.assertEqual(src.read_text("utf-8"),"uno")

    def test_borrado_remoto_opcional_y_papelera(self):
        src=self.out/"borrame.txt";src.write_text("recuperable","utf-8")
        self._scan()
        self.engine.dispatch()
        target=self.received/"borrame.txt"
        self.assertTrue(target.exists())
        self.engine.propagate_deletes=True
        src.unlink()
        self._scan()
        self.engine.dispatch()
        self.assertFalse(target.exists())
        papelera=list((self.received/".localsync_deleted").glob("*-borrame.txt"))
        self.assertEqual(len(papelera),1)
        self.assertEqual(papelera[0].read_text("utf-8"),"recuperable")

    def test_borrado_no_autorizado_se_rechaza(self):
        from src.backend.network.cliente_tcp import enviar_borrado
        other=port()
        stop=threading.Event();ready=threading.Event()
        receiver=NodoP2PTCP("127.0.0.1",other,self.received,
                            auth_token=self.token,allow_delete=False)
        thread=threading.Thread(target=receiver.servir,args=(stop,ready),daemon=True)
        thread.start()
        try:
            self.assertTrue(ready.wait(4))
            file=self.received/"reservado.txt"
            file.write_bytes(b"no-borrar")
            with self.assertRaises(ValueError):
                enviar_borrado("reservado.txt","127.0.0.1",other,auth_token=self.token)
            self.assertEqual(file.read_bytes(),b"no-borrar")
        finally:
            stop.set();thread.join(timeout=5)

    def test_no_borra_archivos_remotos_sin_consentimiento(self):
        src=self.out/"local.txt";src.write_bytes(b"local")
        self._scan();self.engine.dispatch()
        self.assertTrue((self.received/"local.txt").exists())
        src.unlink();self._scan()
        self.assertFalse(any(q["operation"]=="DELETE" for q in self.engine.db.stats()["cola"]))
        self.assertTrue((self.received/"local.txt").exists())


if __name__=="__main__":
    unittest.main()
