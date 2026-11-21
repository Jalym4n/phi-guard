from __future__ import annotations

import pytest

from phi_guard_studio import keystore as ks
from phi_guard_studio.keystore import KeyStore, KeyStoreError, decrypt_export, encrypt_export


class MemoryKeyring:
    """A stand-in for the OS keychain."""

    priority = 10

    def __init__(self):
        self.store = {}

    def get_password(self, service, account):
        return self.store.get((service, account))

    def set_password(self, service, account, value):
        self.store[(service, account)] = value


def test_keychain_backend_preferred(tmp_path, monkeypatch):
    ring = MemoryKeyring()
    monkeypatch.setattr(KeyStore, "_probe_keyring", staticmethod(lambda: ring))
    store = KeyStore(tmp_path)
    key = store.get_or_create()
    assert store.backend == "keychain" and not (tmp_path / "key.bin").exists()
    assert store.get_or_create() == key and ring.store
    st = store.status()
    assert st.location == "System keychain" and st.fingerprint == ks.fingerprint(key)


def test_fail_keyring_falls_back_to_file(tmp_path):
    store = KeyStore(tmp_path)  # this test machine has no usable keychain
    if store.backend == "keychain":  # pragma: no cover - developer machines
        pytest.skip("a real keychain is available")
    key = store.get_or_create()
    assert (tmp_path / "key.bin").exists() and KeyStore(tmp_path).get_or_create() == key
    assert key not in (tmp_path / "key.bin").read_bytes()


def test_file_from_another_machine_is_rejected(tmp_path, monkeypatch):
    store = KeyStore(tmp_path, use_keyring=False)
    store.get_or_create()
    monkeypatch.setattr(ks, "_machine_secret", lambda: b"different machine")
    with pytest.raises(KeyStoreError, match="can't be opened"):
        KeyStore(tmp_path, use_keyring=False).get_or_create()
    assert KeyStore(tmp_path, use_keyring=False).status().exists is False


def test_export_roundtrip_and_tamper():
    key = b"k" * 32
    blob = encrypt_export(key, "a long passphrase")
    assert key not in blob
    assert decrypt_export(blob, "a long passphrase") == key
    with pytest.raises(KeyStoreError):
        decrypt_export(blob, "wrong passphrase!")
    tampered = blob.replace(b'"n": 32768', b'"n": 1073741824')
    with pytest.raises(KeyStoreError, match="not a phi-guard"):
        decrypt_export(tampered, "a long passphrase")
    with pytest.raises(KeyStoreError):
        encrypt_export(key, "short")


def test_launcher_main_runs_server(monkeypatch, tmp_path, capsys):
    import uvicorn

    from phi_guard_studio import launcher

    ran = {}

    def fake_run(self, sockets=None):
        ran["sockets"] = sockets
        sockets[0].close()

    opened = []
    monkeypatch.setattr(uvicorn.Server, "run", fake_run)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(
        launcher.threading, "Timer", lambda delay, fn, args: type("T", (), {"start": lambda s: fn(*args)})()
    )
    monkeypatch.setenv("PHI_GUARD_STUDIO_TOKEN", "launch-token")
    assert launcher.main(["--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "#token=launch-token" in out and "Nothing is uploaded" in out
    assert opened and opened[0].startswith("http://127.0.0.1:") and ran["sockets"]
    assert launcher.main(["--data-dir", str(tmp_path), "--no-browser", "--host", "0.0.0.0", "--allow-network"]) == 0
    assert "WARNING" in capsys.readouterr().err
