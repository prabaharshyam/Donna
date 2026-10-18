"""App login for when Donna leaves localhost: password (scrypt) + optional TOTP 2FA,
server-side sessions, login rate limiting, CSRF header check and Host allow-list."""
import base64
import hashlib
import os
import hmac
import secrets
import struct
import time
import urllib.parse
from datetime import datetime, timedelta

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import db, secure

COOKIE = "donna_session"
# In the cloud nothing is ever "this Mac": every request needs a signed-in session.
CLOUD = os.environ.get("DONNA_CLOUD", "").lower() in ("1", "true", "yes")


def is_local(request) -> bool:
    if CLOUD:
        return False
    client = request.client.host if request.client else ""
    return client in ("127.0.0.1", "::1") and not request.headers.get("cf-connecting-ip") and not request.headers.get("x-forwarded-for")
SESSION_DAYS = 30
_fails = {}


# ---------------- password ----------------
def enabled() -> bool:
    return bool(db.get_setting("auth_hash"))


def _hash(pw: str, salt: bytes) -> str:
    return base64.b64encode(Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(pw.encode())).decode()


def set_password(pw: str):
    if len(pw) < 10:
        raise ValueError("Use at least 10 characters for the app password")
    salt = secrets.token_bytes(16)
    db.set_setting("auth_salt", base64.b64encode(salt).decode())
    db.set_setting("auth_hash", _hash(pw, salt))


def check_password(pw: str) -> bool:
    if not enabled():
        return False
    salt = base64.b64decode(db.get_setting("auth_salt"))
    return hmac.compare_digest(_hash(pw, salt), db.get_setting("auth_hash"))


def disable():
    for k in ("auth_hash", "auth_salt", "totp_secret", "totp_enabled"):
        db.run("DELETE FROM settings WHERE key=?", (k,))
    db.run("DELETE FROM sessions")


# ---------------- TOTP (RFC 6238) ----------------
def _totp(secret_b32: str, t: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    h = hmac.new(key, struct.pack(">Q", t // 30), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


def totp_enabled():
    return bool(db.get_setting("totp_enabled", False))


def totp_begin():
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    secure.set_secret("totp_pending", secret)
    label = urllib.parse.quote(f"Donna:{db.get_setting('user_name', 'me') or 'me'}")
    return {"secret": secret, "uri": f"otpauth://totp/{label}?secret={secret}&issuer=Donna&digits=6&period=30"}


def totp_verify(code: str, secret=None) -> bool:
    secret = secret or secure.get_secret("totp_secret")
    if not secret or not code:
        return False
    now = int(time.time())
    return any(hmac.compare_digest(_totp(secret, now + d * 30), code.strip().replace(" ", "")) for d in (-1, 0, 1))


def totp_confirm(code: str):
    pending = secure.get_secret("totp_pending")
    if not totp_verify(code, pending):
        raise ValueError("That code didn't match. Check your phone's clock and try again")
    secure.set_secret("totp_secret", pending)
    db.set_setting("totp_enabled", True)


def totp_disable():
    db.set_setting("totp_enabled", False)


# ---------------- sessions ----------------
def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(agent=""):
    token = secrets.token_urlsafe(32)
    exp = (datetime.now() + timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    db.run("INSERT INTO sessions(token_hash, expires, agent) VALUES (?,?,?)", (_h(token), exp, agent[:200]))
    return token


def valid_session(token) -> bool:
    if not token:
        return False
    r = db.row("SELECT expires FROM sessions WHERE token_hash=?", (_h(token),))
    return bool(r and r["expires"] > db.now())


def end_session(token):
    if token:
        db.run("DELETE FROM sessions WHERE token_hash=?", (_h(token),))


def end_all():
    db.run("DELETE FROM sessions")


def session_count():
    return db.row("SELECT COUNT(*) n FROM sessions WHERE expires>?", (db.now(),))["n"]


# ---------------- brute-force protection ----------------
def throttled(ip) -> int:
    n, until = _fails.get(ip, (0, 0))
    return max(0, int(until - time.time()))


def record_fail(ip):
    n, _ = _fails.get(ip, (0, 0))
    n += 1
    _fails[ip] = (n, time.time() + (min(300, 2 ** (n - 4) * 15) if n >= 5 else 0))


def record_ok(ip):
    _fails.pop(ip, None)


# ---------------- host allow-list (DNS-rebinding defence) ----------------
def allowed_host(host: str) -> bool:
    host = (host or "").split(":")[0].lower()
    if host in ("localhost", "127.0.0.1", "::1", "[::1]") or host.endswith(".localhost"):
        return True
    pubs = {(urllib.parse.urlparse(u).hostname or "").lower() for u in (db.get_setting("public_url", ""), os.environ.get("DONNA_PUBLIC_URL", ""))}
    extra = [h.strip().lower() for h in ((db.get_setting("allowed_hosts", "") or "") + "," + os.environ.get("DONNA_ALLOWED_HOSTS", "")).split(",") if h.strip()]
    return host in pubs - {""} or host in extra
