"""Descubrimiento UDP opt-in entre equipos con la misma clave HMAC.

Los paquetes no contienen el token. Un resultado no autoriza conexiones:
el usuario aún debe agregar explícitamente el par. Tráfico LAN: UDP 9002.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import threading
import time

DISCOVERY_PORT = 9002
VERSION = "LOCALSYNC_DISCOVERY_V1"
MAX_PACKET = 1024


def _sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("ascii"),
                    hashlib.sha256).hexdigest()


class DiscoveryResponder:
    def __init__(self, token: str, tcp_port: int = 9001,
                 udp_port: int = DISCOVERY_PORT, *, name: str | None = None):
        if not token or len(token) < 16:
            raise ValueError("La búsqueda segura de nodos requiere un token compartido.")
        self.token = token
        self.tcp_port = int(tcp_port)
        self.udp_port = int(udp_port)
        self.name = (name or socket.gethostname())[:60]
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return self.udp_port
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.udp_port))
            sock.settimeout(.2)
        except BaseException:
            sock.close()
            raise
        self.udp_port = sock.getsockname()[1]
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="localsync-descubrimiento")
        self._thread.start()
        return self.udp_port

    def _run(self):
        sock = self._sock
        while not self._stop.is_set():
            try:
                packet, origin = sock.recvfrom(MAX_PACKET)
                data = json.loads(packet.decode("utf-8"))
                nonce = data.get("nonce")
                if data.get("v") != VERSION or not isinstance(nonce, str):
                    continue
                if len(nonce) != 32 or any(x not in "0123456789abcdef" for x in nonce):
                    continue
                if not hmac.compare_digest(data.get("proof",""),
                                           _sign(self.token, "hello:"+nonce)):
                    continue
                response = {
                    "v":VERSION,"nonce":nonce,"port":self.tcp_port,
                    "name":self.name,
                    "proof":_sign(self.token,f"reply:{nonce}:{self.tcp_port}"),
                }
                sock.sendto(json.dumps(response).encode("utf-8"), origin)
            except (OSError, ValueError, UnicodeDecodeError, TypeError):
                continue

    def stop(self):
        self._stop.set()
        if self._sock:
            self._sock.close()
        if self._thread:
            self._thread.join(timeout=2)


def discover(token: str, *, udp_port: int = DISCOVERY_PORT,
             timeout: float = 1.2, targets: tuple[str,...] = ("255.255.255.255", "127.0.0.1")):
    """Descubre pares firmados por la misma clave, sin autorizar automáticamente."""
    if not token or len(token) < 16:
        raise ValueError("Introduzca el token compartido para buscar pares")
    nonce = secrets.token_hex(16)
    payload = json.dumps({
        "v":VERSION,"nonce":nonce,"proof":_sign(token,"hello:"+nonce),
    }).encode("utf-8")
    found = {}
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        sock.bind(("0.0.0.0",0))
        for target in targets:
            sock.sendto(payload,(target,udp_port))
        until=time.monotonic()+max(.1,min(timeout,5.0))
        while time.monotonic()<until and len(found)<24:
            sock.settimeout(max(.05,until-time.monotonic()))
            try:
                packet, address=sock.recvfrom(MAX_PACKET)
            except socket.timeout:
                break
            try:
                obj=json.loads(packet.decode("utf-8"))
                port=obj["port"];ip=ipaddress.ip_address(address[0])
                if not isinstance(port,int) or isinstance(port,bool) or not 1024<=port<=65535:
                    continue
                if not isinstance(ip,ipaddress.IPv4Address) or (
                    not (ip.is_private or ip.is_loopback) or ip.is_multicast
                ):
                    continue
                if obj.get("v")!=VERSION or obj.get("nonce")!=nonce:
                    continue
                if not hmac.compare_digest(obj.get("proof",""),
                                           _sign(token,f"reply:{nonce}:{port}")):
                    continue
                name=obj.get("name","LocalSync")
                if not isinstance(name,str):
                    name="LocalSync"
                found[(str(ip),port)]={"host":str(ip),"puerto":port,"nombre":name[:60]}
            except (ValueError,KeyError,TypeError,UnicodeDecodeError):
                continue
    return list(found.values())
