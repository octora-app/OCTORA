"""Admin authentication: pbkdf2-hashed password + token sessions."""
import hashlib
import hmac
import secrets
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from . import config
from .db import DB, utcnow


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000).hex()


def ensure_admin(db: DB):
    """Create the admin account on first boot from OCTORA_ADMIN_PASSWORD."""
    if db.get_admin("admin"):
        return
    if not config.ADMIN_PASSWORD:
        raise RuntimeError("First boot: set OCTORA_ADMIN_PASSWORD env var, then restart.")
    salt = secrets.token_bytes(16)
    db.create_admin("admin", _hash(config.ADMIN_PASSWORD, salt), salt.hex())


def verify_login(db: DB, password: str) -> bool:
    admin = db.get_admin("admin")
    if not admin:
        return False
    salt = bytes.fromhex(admin["salt"])
    return secrets.compare_digest(_hash(password, salt), admin["pw_hash"])


def create_session(db: DB, admin_id: int) -> tuple[str, str]:
    """Create a session; returns (cookie_token, csrf_token)."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    csrf_token = secrets.token_urlsafe(32)
    exp = (datetime.now(timezone.utc) + timedelta(hours=config.SESSION_HOURS)
           ).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.create_session(token_hash, admin_id, exp, csrf_token)
    return token, csrf_token


def session_csrf_token(db: DB, token: str | None) -> str:
    """CSRF token for the current admin session (backfills older sessions)."""
    if not token:
        return ""
    th = hashlib.sha256(token.encode()).hexdigest()
    s = db.get_session(th)
    if not s:
        return ""
    csrf = s.get("csrf_token") or ""
    if not csrf:
        csrf = secrets.token_urlsafe(32)
        db.set_session_csrf(th, csrf)
    return csrf


def csrf_valid(db: DB, token: str | None, submitted: str) -> bool:
    expected = session_csrf_token(db, token)
    return bool(expected) and hmac.compare_digest(str(submitted or ""), expected)


# ---------------------------------------------------------------------------
# Login brute-force protection: 10 failed attempts per 10 minutes from one IP
# -> 15-minute lockout. In-memory (single worker on Render's free tier).
# ---------------------------------------------------------------------------
_LOGIN_FAILURES: dict[str, deque] = {}
_LOGIN_LOCKOUTS: dict[str, float] = {}
MAX_LOGIN_FAILURES = 10
LOGIN_FAIL_WINDOW_SECS = 600
LOGIN_LOCKOUT_SECS = 900


def login_allowed(ip: str) -> tuple[bool, int]:
    """(allowed, seconds_until_retry)."""
    until = _LOGIN_LOCKOUTS.get(ip, 0)
    now = time.time()
    if until > now:
        return False, int(until - now)
    return True, 0


def record_login_failure(ip: str):
    now = time.time()
    dq = _LOGIN_FAILURES.setdefault(ip, deque())
    while dq and dq[0] < now - LOGIN_FAIL_WINDOW_SECS:
        dq.popleft()
    dq.append(now)
    if len(dq) >= MAX_LOGIN_FAILURES:
        _LOGIN_LOCKOUTS[ip] = now + LOGIN_LOCKOUT_SECS
        _LOGIN_FAILURES.pop(ip, None)


def clear_login_failures(ip: str):
    _LOGIN_FAILURES.pop(ip, None)
    _LOGIN_LOCKOUTS.pop(ip, None)


def session_admin(db: DB, token: str | None):
    if not token:
        return None
    db.prune_sessions()
    if not token:
        return None
    th = hashlib.sha256(token.encode()).hexdigest()
    s = db.get_session(th)
    if not s or s["expires_at"] < utcnow():
        return None
    return db.get_admin("admin")


def destroy_session(db: DB, token: str | None):
    if token:
        db.delete_session(hashlib.sha256(token.encode()).hexdigest())
