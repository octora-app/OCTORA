"""Customer-side telemetry for the OCTORA admin panel (v1.3).

Sends a small heartbeat to the seller's admin server so Sudeep can see
which users are active, which channels they connected, subscriber counts
and upload results.

PRIVACY & SAFETY RULES (hard):
* Master consent flag: nothing is ever sent unless the user accepted the
  first-run telemetry dialog (config key ``telemetry_consent``) AND a
  server URL is configured. The user can revoke anytime in Settings.
* Fails SILENTLY: every network call is wrapped, short timeouts, background
  daemon threads only. Telemetry can NEVER crash, slow or block the app.
* Cold-start resilient: free hosts sleep — retries with backoff
  (immediate, +45s, +4min) instead of one shot.
* Only ``hwid_hash`` (SHA-256 of the local HWID) is sent — never the raw
  hardware ID, never file contents, never video data.

See PRIVACY.md (admin panel repo) for the user-facing disclosure and
INTEGRATION.md for the wiring points.
"""
import hashlib
import json
import threading
import time
import urllib.request
from datetime import datetime, timezone

HEARTBEAT_INTERVAL = 6 * 3600          # every 6 hours
RETRY_DELAYS = (45, 240)               # cold-start friendly backoff (s)
CONNECT_TIMEOUT = 8
READ_TIMEOUT = 25
# Single source of truth for the app version (used by the updater and the
# heartbeat). Never hardcode a second copy — a desync here makes the
# updater offer the already-installed version in a loop.
from octora import __version__ as APP_VERSION


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def server_url(cfg) -> str:
    """Admin server base URL. Falls back to the baked-in production server so
    payments/licenses work out of the box; Settings can override it."""
    return ((cfg.get("admin_server_url", "") or "").strip()
            or DEFAULT_SERVER_URL).rstrip("/")


# Production payment/license server (set after deploy; overridable in Settings).
DEFAULT_SERVER_URL = "https://octora-admin.onrender.com"


def enabled(cfg) -> bool:
    """Master gate: consent + configured server."""
    return bool(cfg.get("telemetry_consent", False)) and bool(server_url(cfg))


def hwid_hash() -> str:
    from .license import hwid
    return hashlib.sha256(hwid().encode("utf-8")).hexdigest()


def license_key_id(cfg) -> str:
    """Fingerprint of the installed license file (lets the server link the user)."""
    try:
        from .config import data_dir
        from .license import LICENSE_FILENAME
        p = data_dir() / LICENSE_FILENAME
        if p.exists():
            return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        pass
    return ""


def connected_platforms(cfg) -> list:
    """What the user connected — from local config tokens only (no API calls)."""
    plats = []
    if cfg.get("google_refresh_token"):
        plats.append({"platform": "google", "channel_id": "",
                      "channel_name": cfg.get("google_channel_name", "") or "YouTube + Drive",
                      "subscriber_count": int(cfg.get("google_subscriber_count", 0) or 0)})
    return plats


def counters(db) -> dict:
    """Upload counters from the local DB. Never raises."""
    try:
        total = db.query_one(
            "SELECT COUNT(*) c FROM uploads_log WHERE status='posted'")["c"]
        today = datetime.now().date().isoformat()
        day = db.query_one(
            "SELECT COUNT(*) c FROM uploads_log WHERE status='posted' AND at LIKE ?",
            (today + "%",))["c"]
        return {"uploads_total": int(total or 0), "uploads_today": int(day or 0)}
    except Exception:
        return {"uploads_total": 0, "uploads_today": 0}


def build_payload(db, cfg) -> dict:
    c = counters(db)
    return {
        "license_key_id": license_key_id(cfg),
        "hwid_hash": hwid_hash(),
        "app_version": APP_VERSION,
        "platforms": connected_platforms(cfg),
        "uploads_total": c["uploads_total"],
        "uploads_today": c["uploads_today"],
        "trial_started_at": cfg.get("trial_start", "") or "",
        "timestamp": _now_iso(),
    }


def _post(url: str, payload: dict) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def _send_with_retry(db, cfg, payload: dict):
    """Retry schedule tolerant of free-host cold starts. Never raises."""
    try:
        url = server_url(cfg) + "/api/v1/heartbeat"
        if _post(url, payload):
            return
        for delay in RETRY_DELAYS:
            time.sleep(delay)
            if not enabled(cfg):      # user revoked meanwhile
                return
            if _post(url, payload):
                return
    except Exception:
        pass


def send_heartbeat(db, cfg, reason: str = "periodic"):
    """Fire-and-forget heartbeat. Safe to call from anywhere — never blocks."""
    try:
        if not enabled(cfg):
            return
        payload = build_payload(db, cfg)
        payload["reason"] = reason
        t = threading.Thread(target=_send_with_retry, args=(db, cfg, payload),
                             daemon=True, name=f"telemetry-{reason}")
        t.start()
    except Exception:
        pass


def start_background_loop(db, cfg):
    """6-hour heartbeat loop. Call once at app start (after consent)."""
    def loop():
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            try:
                if enabled(cfg):
                    _send_with_retry(db, cfg, build_payload(db, cfg))
            except Exception:
                pass
    t = threading.Thread(target=loop, daemon=True, name="telemetry-loop")
    t.start()
    return t


def notify_platform_change(db, cfg):
    """Call after a platform connect/disconnect."""
    send_heartbeat(db, cfg, reason="platform_change")


def notify_upload(db, cfg):
    """Call after an upload completes (posted or failed)."""
    send_heartbeat(db, cfg, reason="upload")


# ---------------------------------------------------------------------------
# Online license validation with offline grace (used at app startup).
# Returns (ok: bool, message: str). Never raises; offline -> consults cache.
# ---------------------------------------------------------------------------
GRACE_DAYS_OFFLINE = 3


def validate_online(cfg) -> tuple:
    """Ask the server whether this license is still valid (not revoked)."""
    try:
        if not enabled(cfg):
            return True, "telemetry disabled — local check only"
        kid = license_key_id(cfg)
        if not kid:
            return True, "no license installed — local check only"
        url = server_url(cfg) + "/api/v1/license/validate"
        payload = {"key_id": kid, "hwid_hash": hwid_hash()}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)) as r:
            res = json.loads(r.read().decode("utf-8"))
        if res.get("valid"):
            cfg.set("telemetry_last_validate", _now_iso())
            cfg.set("telemetry_last_validate_ok", "1")
            return True, "server: license valid"
        cfg.set("telemetry_last_validate_ok", "0")
        return False, "server: " + res.get("message", "license invalid")
    except Exception:
        # Offline / cold start / server asleep -> grace from cache
        try:
            last = cfg.get("telemetry_last_validate", "")
            ok = cfg.get("telemetry_last_validate_ok", "") == "1"
            if ok and last:
                dt = datetime.now(timezone.utc) - datetime.strptime(
                    last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if dt.days <= GRACE_DAYS_OFFLINE:
                    return True, "offline — using cached validation"
        except Exception:
            pass
        return True, "offline — local check only"
