"""Credential vault: encrypted at rest, owner-bound, never returned.

* AES-256-GCM with the credential's owner scope and reference as AAD, so a
  ciphertext copied to another owner's row fails authentication.
* ``put`` returns only an opaque reference. There is deliberately no method that
  returns secrets to a caller other than adapter construction (``reveal``), which
  is server-side only and never serialized.
* The persistent vault FAILS CLOSED: with no key or no ``cryptography`` package
  it refuses to store anything rather than falling back to plaintext.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import threading
from pathlib import Path

from .canonical import new_id

KEY_ENV = "PEOPLEPAY_MODELS_VAULT_KEY"
KEY_FILE_ENV = "PEOPLEPAY_MODELS_VAULT_KEY_FILE"


class VaultError(Exception):
    pass


class VaultUnavailable(VaultError):
    pass


def generate_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def mask(secret: str) -> str:
    """UI mask. Never reveals more than the last 4 chars, and only for long secrets."""
    if not secret:
        return ""
    return "••••" + (secret[-4:] if len(secret) >= 12 else "")


class Vault:
    def put(self, owner: str, secrets: dict[str, str]) -> str: raise NotImplementedError
    def reveal(self, owner: str, ref: str) -> dict[str, str]: raise NotImplementedError
    def delete(self, owner: str, ref: str) -> None: raise NotImplementedError
    def exists(self, owner: str, ref: str) -> bool: raise NotImplementedError


class MemoryVault(Vault):
    """Non-persistent. Used in tests and for process-lifetime env-derived system credentials."""

    def __init__(self) -> None:
        self._d: dict[str, tuple[str, dict[str, str]]] = {}
        self._lock = threading.Lock()

    def put(self, owner, secrets):
        ref = new_id("cred")
        with self._lock:
            self._d[ref] = (owner, dict(secrets))
        return ref

    def reveal(self, owner, ref):
        with self._lock:
            rec = self._d.get(ref)
        if rec is None or rec[0] != owner:
            raise VaultError("credential not found")
        return dict(rec[1])

    def delete(self, owner, ref):
        with self._lock:
            rec = self._d.get(ref)
            if rec and rec[0] == owner:
                del self._d[ref]

    def exists(self, owner, ref):
        with self._lock:
            rec = self._d.get(ref)
        return bool(rec and rec[0] == owner)

    def __repr__(self) -> str:
        return "MemoryVault(<redacted>)"


class EncryptedSqliteVault(Vault):
    def __init__(self, db_path: str | Path, key: str | bytes | None = None):
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:  # pragma: no cover - exercised via monkeypatch in tests
            raise VaultUnavailable("the 'cryptography' package is required to store credentials") from exc
        raw = key if key is not None else self._load_key()
        if raw is None:
            raise VaultUnavailable(
                f"no vault key: set {KEY_ENV} (see `python -m peoplepay_models.vault` for a new one) "
                f"or {KEY_FILE_ENV}")
        key_bytes = base64.urlsafe_b64decode(raw) if isinstance(raw, str) else raw
        if len(key_bytes) != 32:
            raise VaultUnavailable("vault key must be 32 bytes, urlsafe-base64 encoded")
        self._aes = AESGCM(key_bytes)
        self._path = str(db_path)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS credentials (ref TEXT PRIMARY KEY, owner TEXT NOT NULL, nonce BLOB NOT NULL, ct BLOB NOT NULL)")

    @staticmethod
    def _load_key() -> str | None:
        if os.environ.get(KEY_ENV):
            return os.environ[KEY_ENV]
        path = os.environ.get(KEY_FILE_ENV)
        if path and Path(path).is_file():
            return Path(path).read_text().strip()
        return None

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    @staticmethod
    def _aad(owner: str, ref: str) -> bytes:
        return f"{owner}\x00{ref}".encode()

    def put(self, owner, secrets):
        ref = new_id("cred")
        nonce = os.urandom(12)
        ct = self._aes.encrypt(nonce, json.dumps(secrets).encode(), self._aad(owner, ref))
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO credentials VALUES (?,?,?,?)", (ref, owner, nonce, ct))
        return ref

    def reveal(self, owner, ref):
        with self._conn() as c:
            row = c.execute("SELECT owner, nonce, ct FROM credentials WHERE ref=?", (ref,)).fetchone()
        if row is None or row[0] != owner:
            raise VaultError("credential not found")
        try:
            return json.loads(self._aes.decrypt(row[1], row[2], self._aad(owner, ref)))
        except Exception as exc:  # InvalidTag etc. -- never echo internals
            raise VaultError("credential could not be decrypted") from exc

    def delete(self, owner, ref):
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM credentials WHERE ref=? AND owner=?", (ref, owner))

    def exists(self, owner, ref):
        with self._conn() as c:
            return c.execute("SELECT 1 FROM credentials WHERE ref=? AND owner=?", (ref, owner)).fetchone() is not None

    def __repr__(self) -> str:
        return "EncryptedSqliteVault(<redacted>)"


if __name__ == "__main__":  # pragma: no cover
    print(generate_key())
