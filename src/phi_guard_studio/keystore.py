"""Storage for the HMAC "protection key" that makes codes like ``[SIN_2311c0d1]``.

Preferred storage is the operating system's keychain via ``keyring``
(macOS Keychain, Windows Credential Manager, Linux Secret Service).

If no keychain is available (for example a headless Linux box or a Docker
container), the key is stored in ``key.bin`` in the app-data folder,
encrypted with AES-256-GCM under a wrapping key derived (scrypt) from this
machine's identity and user name, with file permissions 0600.  **This
fallback only stops casual copying of the file to another machine.**  Anyone
who can run code as this user on this machine can recover the key.  Settings
labels it clearly.

Export uses a user password: scrypt (n=2**15, r=8, p=1) derives a 256-bit key
from the password and a random 16-byte salt, and AES-256-GCM encrypts the
protection key with a random 12-byte nonce.  The export file is JSON holding
the KDF parameters, salt, nonce and ciphertext (base64).  A wrong password
fails the GCM authentication check.

The key itself is never returned by the API; only a short fingerprint
(first 8 hex characters of its SHA-256) is shown so users can tell keys apart.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import json
import os
import platform
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

__all__ = ["KEY_BYTES", "KeyStatus", "KeyStore", "KeyStoreError", "decrypt_export", "encrypt_export"]

SERVICE = "phi-guard-studio"
ACCOUNT = "hmac-key"
KEY_BYTES = 32
EXPORT_FORMAT = "phi-guard-key-export/v1"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1
MIN_PASSWORD_LENGTH = 10


class KeyStoreError(ValueError):
    """A key operation failed.  ``str(exc)`` is a plain-language message."""


@dataclass
class KeyStatus:
    exists: bool
    backend: str  # "keychain" | "file"
    location: str
    fingerprint: str | None


def _scrypt(secret: bytes, salt: bytes, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(secret)


def encrypt_export(key: bytes, password: str) -> bytes:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise KeyStoreError(f"Please use a password of at least {MIN_PASSWORD_LENGTH} characters.")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    ct = AESGCM(_scrypt(password.encode(), salt)).encrypt(nonce, key, EXPORT_FORMAT.encode())
    blob = {
        "format": EXPORT_FORMAT,
        "kdf": {"name": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P},
        "cipher": "AES-256-GCM",
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ct).decode(),
    }
    return (json.dumps(blob, indent=2) + "\n").encode()


def decrypt_export(data: bytes, password: str) -> bytes:
    try:
        blob = json.loads(data)
        if blob.get("format") != EXPORT_FORMAT:
            raise ValueError
        kdf = blob["kdf"]
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
        if not (2**14 <= n <= 2**20 and r <= 16 and p <= 4):  # refuse absurd (DoS) parameters
            raise ValueError
        salt = base64.b64decode(blob["salt"])
        nonce = base64.b64decode(blob["nonce"])
        ct = base64.b64decode(blob["ciphertext"])
    except (ValueError, KeyError, TypeError) as exc:
        raise KeyStoreError("This file is not a phi-guard key export.") from exc
    try:
        key = AESGCM(_scrypt(password.encode(), salt, n, r, p)).decrypt(nonce, ct, EXPORT_FORMAT.encode())
    except InvalidTag as exc:
        raise KeyStoreError("The password is not correct for this key file.") from exc
    if len(key) != KEY_BYTES:
        raise KeyStoreError("This key file is damaged.")
    return key


def _machine_secret() -> bytes:
    """Stable, machine-specific (not secret!) material for the file fallback."""
    parts = [platform.node(), getpass.getuser(), str(uuid.getnode())]
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            parts.append(Path(p).read_text().strip())
            break
        except OSError:
            continue
    return "|".join(parts).encode()


class KeyStore:
    def __init__(self, data_dir: Path, use_keyring: bool = True) -> None:
        self.file = Path(data_dir) / "key.bin"
        self._keyring: Any = None
        if use_keyring:
            self._keyring = self._probe_keyring()

    @staticmethod
    def _probe_keyring() -> Any:
        try:
            import keyring
            from keyring.backends import fail

            backend = keyring.get_keyring()
            if isinstance(backend, fail.Keyring) or backend.priority <= 0:
                return None
            return keyring
        except Exception:  # pragma: no cover - platform specific
            return None

    @property
    def backend(self) -> str:
        return "keychain" if self._keyring is not None else "file"

    # -- low level -----------------------------------------------------------
    def _read(self) -> bytes | None:
        if self._keyring is not None:
            value = self._keyring.get_password(SERVICE, ACCOUNT)
            return base64.b64decode(value) if value else None
        if not self.file.exists():
            return None
        blob = self.file.read_bytes()
        salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
        try:
            return AESGCM(_scrypt(_machine_secret(), salt, n=2**14)).decrypt(nonce, ct, b"phi-guard-local")
        except InvalidTag as exc:
            raise KeyStoreError(
                "The saved protection key can't be opened on this computer. Create a new key or import a backup."
            ) from exc

    def _write(self, key: bytes) -> None:
        if self._keyring is not None:
            self._keyring.set_password(SERVICE, ACCOUNT, base64.b64encode(key).decode())
            return
        self.file.parent.mkdir(parents=True, exist_ok=True)
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        ct = AESGCM(_scrypt(_machine_secret(), salt, n=2**14)).encrypt(nonce, key, b"phi-guard-local")
        tmp = self.file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(salt + nonce + ct)
        os.replace(tmp, self.file)

    # -- public --------------------------------------------------------------
    def get_or_create(self) -> bytes:
        key = self._read()
        if key is None:
            key = secrets.token_bytes(KEY_BYTES)
            self._write(key)
        return key

    def rotate(self) -> bytes:
        key = secrets.token_bytes(KEY_BYTES)
        self._write(key)
        return key

    def export(self, password: str) -> bytes:
        return encrypt_export(self.get_or_create(), password)

    def import_(self, data: bytes, password: str) -> bytes:
        key = decrypt_export(data, password)
        self._write(key)
        return key

    def status(self) -> KeyStatus:
        try:
            key = self._read()
        except KeyStoreError:
            key = None
        location = "System keychain" if self._keyring is not None else str(self.file)
        return KeyStatus(key is not None, self.backend, location, fingerprint(key) if key else None)


def fingerprint(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:8]
