"""Admin authentication: pbkdf2-hashed password + token sessions."""
import hashlib
import secrets
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


def create_session(db: DB, admin_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    exp = (datetime.now(timezone.utc) + timedelta(hours=config.SESSION_HOURS)
           ).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.create_session(token_hash, admin_id, exp)
    return token


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
