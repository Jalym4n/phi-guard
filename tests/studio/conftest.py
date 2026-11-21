"""Fixtures for Studio tests.

Every test in this folder runs with outbound network connections blocked:
any attempt to connect to a non-loopback address fails the test.
"""

from __future__ import annotations

import ipaddress
import socket

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from phi_guard_studio.app import create_app
from phi_guard_studio.config import StudioConfig
from phi_guard_studio.keystore import KeyStore

PORT = 8765
TOKEN = "test-token-not-secret"
BASE = f"http://127.0.0.1:{PORT}"


class ExternalNetworkCall(AssertionError):
    pass


def _is_local(address: object) -> bool:
    if isinstance(address, str):  # AF_UNIX path
        return True
    if not (isinstance(address, tuple) and address):
        return False
    host = str(address[0])
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Fail if anything tries to reach a non-loopback address."""
    calls: list[object] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address):
        if not _is_local(address):
            calls.append(address)
            raise ExternalNetworkCall(f"external network call to {address!r}")
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        if not _is_local(address):
            calls.append(address)
            raise ExternalNetworkCall(f"external network call to {address!r}")
        return real_connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in (None, "localhost", "127.0.0.1", "::1", "testserver") and not _is_local((host,)):
            calls.append(host)
            raise ExternalNetworkCall(f"DNS lookup for {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield calls
    assert calls == [], f"unexpected external network calls: {calls}"


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "studio-data"


@pytest.fixture
def app(data_dir):
    config = StudioConfig(port=PORT, token=TOKEN, data_dir=data_dir, static_dir=data_dir / "no-ui")
    return create_app(config, keystore=KeyStore(data_dir, use_keyring=False), ner_available=False)


@pytest.fixture
def client(app):
    with TestClient(app, base_url=BASE, headers={"X-PHI-Guard-Token": TOKEN}) as c:
        yield c


@pytest.fixture
def anon(app):
    """A client without the session token."""
    with TestClient(app, base_url=BASE) as c:
        yield c
