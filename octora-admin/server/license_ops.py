"""RSA license operations for the admin panel.

Same envelope scheme as tools/keygen.py in the app repo:
  armored base64 of {"payload": {...}, "sig": b64}
  sig = RSASSA-PKCS1v15-SHA256 over canonical JSON of "payload".

The server holds the seller PRIVATE key (env OCTORA_SELLER_KEY path or
OCTORA_SELLER_PEM text) so it can issue keys online. The key NEVER leaves
the server.
"""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from . import config

_private_key = None


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def get_private_key():
    global _private_key
    if _private_key is not None:
        return _private_key
    if config.SELLER_KEY_PEM.strip():
        data = config.SELLER_KEY_PEM.encode()
    elif config.SELLER_KEY_PATH:
        data = Path(config.SELLER_KEY_PATH).read_bytes()
    else:
        raise RuntimeError("Seller private key not configured: set OCTORA_SELLER_KEY "
                           "(path) or OCTORA_SELLER_PEM (PEM text).")
    _private_key = serialization.load_pem_private_key(data, password=None)
    return _private_key


def seller_configured() -> bool:
    try:
        get_private_key()
        return True
    except Exception:
        return False


def issue_armored(name: str, email: str, hwid: str, days: int = 365) -> str:
    """Mint a license bound to `hwid` (raw HWID from the buyer's app)."""
    key = get_private_key()
    now = datetime.now(timezone.utc)
    payload = {
        "v": 1,
        "product": "OCTORA",
        "name": name,
        "email": email,
        "hwid": hwid.strip().lower(),
        "issued": now.strftime("%Y-%m-%d"),
        "expires": (now + timedelta(days=days)).strftime("%Y-%m-%d"),
        "features": ["full"],
    }
    sig = key.sign(_canonical(payload), padding.PKCS1v15(), hashes.SHA256())
    envelope = {"payload": payload, "sig": base64.b64encode(sig).decode()}
    body = base64.b64encode(json.dumps(envelope).encode()).decode()
    return ("-----BEGIN OCTORA LICENSE-----\n"
            + "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
            + "\n-----END OCTORA LICENSE-----\n")


def parse_armored(text: str) -> dict:
    lines = [ln.strip() for ln in text.strip().splitlines()
             if ln.strip() and "OCTORA LICENSE" not in ln]
    env = json.loads(base64.b64decode("".join(lines)).decode("utf-8"))
    if not isinstance(env, dict) or "payload" not in env or "sig" not in env:
        raise ValueError("Not an OCTORA license envelope")
    return env


def verify_envelope(env: dict) -> dict:
    """Verify with the seller PUBLIC key derived from the private key."""
    pub = get_private_key().public_key()
    sig = base64.b64decode(env["sig"])
    try:
        pub.verify(sig, _canonical(env["payload"]), padding.PKCS1v15(), hashes.SHA256())
    except Exception as e:
        raise ValueError(f"Signature invalid: {e}")
    payload = env["payload"]
    if payload.get("product") != "OCTORA":
        raise ValueError("License is for a different product")
    return payload


def key_id_of(armored: str) -> str:
    return hashlib.sha256(armored.strip().encode("utf-8")).hexdigest()


def hwid_hash_of(hwid: str) -> str:
    """What the app sends (never the raw HWID over telemetry)."""
    return hashlib.sha256(hwid.strip().lower().encode("utf-8")).hexdigest()
