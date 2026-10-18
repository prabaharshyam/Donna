"""Encryption.

Two layers:
  * App key (data/.appkey, Fernet) encrypts integration secrets at rest: SMTP password,
    Google client secret and OAuth tokens. Lets the scheduler send mail unattended.
  * Vault key is derived from YOUR master password (scrypt) and is never written to disk.
    Cards, passwords and IDs are AES-256-GCM encrypted with it. When the vault is locked,
    nobody (including Donna) can read those items.
"""
import base64
import json
import os
import secrets
import time

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import db

_KEYFILE = db.DATA_DIR / ".appkey"


def _appkey() -> Fernet:
    if not _KEYFILE.exists():
        _KEYFILE.write_bytes(Fernet.generate_key())
        os.chmod(_KEYFILE, 0o600)
    return Fernet(_KEYFILE.read_bytes())


def seal(value: str) -> str:
    return _appkey().encrypt(value.encode()).decode() if value else ""


def unseal(token: str) -> str:
    if not token:
        return ""
    try:
        return _appkey().decrypt(token.encode()).decode()
    except Exception:
        return ""


def get_secret(key: str) -> str:
    return unseal(db.get_setting(key, ""))


def set_secret(key: str, value: str):
    db.set_setting(key, seal(value))


# ---------------- Vault ----------------
_VERIFIER = b"donna-vault-ok"
_state = {"key": None, "unlocked_at": 0.0}


def _derive(password: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode())


def vault_configured() -> bool:
    return bool(db.get_setting("vault_salt"))


def _enc(key: bytes, plaintext: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def _dec(key: bytes, blob: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], None)


def vault_setup(password: str):
    if vault_configured():
        raise ValueError("Vault already configured")
    if len(password) < 8:
        raise ValueError("Use at least 8 characters")
    salt = secrets.token_bytes(16)
    key = _derive(password, salt)
    db.set_setting("vault_salt", base64.b64encode(salt).decode())
    db.set_setting("vault_check", base64.b64encode(_enc(key, _VERIFIER)).decode())
    _state.update(key=key, unlocked_at=time.time())


def vault_unlock(password: str) -> bool:
    salt = base64.b64decode(db.get_setting("vault_salt"))
    key = _derive(password, salt)
    try:
        if _dec(key, base64.b64decode(db.get_setting("vault_check"))) != _VERIFIER:
            return False
    except Exception:
        return False
    _state.update(key=key, unlocked_at=time.time())
    return True


def vault_lock():
    _state.update(key=None, unlocked_at=0.0)


def vault_unlocked() -> bool:
    if _state["key"] is None:
        return False
    timeout = int(db.get_setting("vault_autolock_min", 15)) * 60
    if time.time() - _state["unlocked_at"] > timeout:
        vault_lock()
        return False
    return True


def touch():
    if _state["key"] is not None:
        _state["unlocked_at"] = time.time()


def encrypt_item(data: dict) -> bytes:
    if not vault_unlocked():
        raise PermissionError("Vault is locked")
    touch()
    return _enc(_state["key"], json.dumps(data).encode())


def decrypt_item(blob: bytes) -> dict:
    if not vault_unlocked():
        raise PermissionError("Vault is locked")
    touch()
    return json.loads(_dec(_state["key"], blob))
