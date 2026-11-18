"""Dos nodos con carpeta compartida, actualización, anti-eco y versiones."""
import socket
from pathlib import Path
import tempfile
import threading
import time
import unittest

from src.backend.sync.engine import AutoSync
from src.backend.network.p2p_socket import NodoP2PTCP


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        return sock.getsockname()[1]


class TestBidirectionalSync(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        root=Path(self.t.name)
        self.a=AutoSync(root/"a",root/"qa.db",root/"versions-a")
        self.b=AutoSync(root/"b",root/"qb.db",root/"versions-b")
        self.addCleanup(self._cleanup)
        self.secret="clave-para-test-de-dos-nodos-2026"
        self.port_a,self.port_b=free_port(),free_port()
        self.stops=[];self.threads=[]
        for engine,p in ((self.a,self.port_a),(self.b,self.port_b)):
            stop,ready=threading.Event(),threading.Event()
            srv=NodoP2PTCP(
                "127.0.0.1",p,engine.root,auth_token=self.secret,
                on_conflict="overwrite",allow_delete=True,
                on_before_overwrite=engine.backup_before_overwrite,
                on_received=engine.register_incoming,
                on_deleted=engine.register_remote_deleted,
            )
            thread=threading.Thread(target=srv.servir,args=(stop,ready),daemon=True)
            thread.start()
            self.assertTrue(ready.wait(4))
            self.stops.append(stop);self.threads.append(thread)
        self.a.add_peer("127.0.0.1",self.port_b,self.secret)
        self.b.add_peer("127.0.0.1",self.port_a,self.secret)

    def _cleanup(self):
        self.a.stop();self.b.stop()
        for e in self.stops:e.set()
        for t in self.threads:t.join(timeout=4)

    def until(self,fn,timeout=16):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if fn():return True
            time.sleep(.1)
        return fn()

    def test_both_directions_and_versions(self):
        self.a.start();self.b.start()
        origin=self.a.root/"documentos"/"informe.txt"
        origin.parent.mkdir()
        origin.write_text("primera versión","utf-8")
        target=self.b.root/"documentos"/"informe.txt"
        self.assertTrue(self.until(lambda:target.exists() and target.read_text("utf-8")=="primera versión"))
        target.write_text("segunda versión editada en B","utf-8")
        self.assertTrue(self.until(lambda:origin.read_text("utf-8")=="segunda versión editada en B"))
        self.assertTrue(self.until(lambda:self.a.db.stats()["pendientes"]==0 and
                                           self.b.db.stats()["pendientes"]==0))
        versions=self.a.db.versions("documentos/informe.txt")
        self.assertTrue(any(v["sha256"] for v in versions))
        self.assertEqual(origin.read_bytes(),target.read_bytes())

    def test_remote_delete_moves_to_archive_without_echo(self):
        self.a.start(propagate_deletes=True)
        self.b.start(propagate_deletes=True)
        file=self.a.root/"borrado.txt"
        file.write_text("proteger esta copia","utf-8")
        dest=self.b.root/"borrado.txt"
        self.assertTrue(self.until(dest.exists))
        file.unlink()
        self.assertTrue(self.until(lambda:not dest.exists()))
        archive=list((self.b.root/".localsync_deleted").glob("*-borrado.txt"))
        self.assertEqual(len(archive),1)
        self.assertEqual(archive[0].read_text("utf-8"),"proteger esta copia")
        self.assertTrue(self.until(lambda:self.a.db.stats()["pendientes"]==0 and
                                          self.b.db.stats()["pendientes"]==0))


if __name__=="__main__":
    unittest.main()
