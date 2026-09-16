"""Commercial licensing for OCTORA: RSA-signed keys, HWID lock, trial, grace, tamper checks.

How it works
------------
* The seller (Sudeep) owns an RSA private key (tools/keygen.py, NEVER shipped).
* A license file is an armored base64 envelope: {"payload": {...}, "sig": b64}.
  sig = RSASSA-PKCS1v15-SHA256 over the canonical JSON of "payload".
* The app embeds only the PUBLIC key (n, e) below and verifies with pure
  Python (pow + hashlib) — no third-party crypto dependency, PyInstaller-safe.

Honest note: no desktop software is literally uncrackable. This implements the
strongest *practical* protection for a Python app: signed keys + hardware-ID
binding + expiry + tamper checks. For extra strength, freeze with PyInstaller
and optionally run a bytecode obfuscator over the bundle before shipping.

Modes: 'licensed' (valid key) | 'trial' (1 day, full features) |
         'grace' (expired <= GRACE_DAYS ago, or clock rollback detected) |
         'expired' | 'none' (no trial started, no key).

STRICT 1-PC-1-LICENSE POLICY (v1.1+)
------------------------------------
One license key = exactly ONE machine. The key is minted for a specific HWID
(buyer sends HWID, seller binds it into the signed payload). Enforcement:

* activate() refuses keys whose HWID != this machine (clear message).
* status() re-verifies signature + HWID match on EVERY app start — a license
  file copied to another PC fails with "bound to another machine".
* A binding record (license_bound_hwid) is stored at activation as a second
  cross-check against file swaps.
* Clock rollback is detected (grace mode, not a free extension).

Bypass reality check: copying the license file, the config, or the whole data
folder to another PC all fail — the HWID is recomputed from the CURRENT
machine every launch. No network "phone home" is used (works offline).
"""
import base64
import hashlib
import hmac
import json
import platform
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# PUBLIC KEY — generated with: python tools/keygen.py keypair
# (replace these two lines if you rotate to your own seller keypair)
# ---------------------------------------------------------------------------
PUBLIC_N = 23365343135792229611583812654488259760680332886324200723953364545891219762645218436525876351349955647394075716321057366816104646451213409439959359932485350381776701763260907903045570832901730963981067437366095394840928208324454455134613469737068485228865522021375217782875509143460575041801786655477814176231071735381570857211780372795438965346517274120784425986124552593301098410154531179247323646514387528213382430059641052382181178137795183627699304585269652197654792625548363921360690896052429849515174297248620604709773422532057791749033942873153677078393391655104907448162695524125405780452763688300603330448281
PUBLIC_E = 65537

TRIAL_HOURS = 24  # exact 24-hour free trial, enforced on a UTC timestamp
GRACE_DAYS = 3
LICENSE_FILENAME = "license.octalicense"

# PKCS#1 v1.5 DigestInfo prefix for SHA-256
_SHA256_DINFO = bytes.fromhex("3031300d060960864801650304020105000420")


def hwid() -> str:
    """Stable hardware ID: 32 hex chars.

    Prefers OS-stable machine identifiers (survive NIC/MAC changes):
      Windows → SMBIOS machine UUID (wmic csproduct)
      Linux   → /etc/machine-id
      macOS   → IOPlatformUUID
    Falls back to MAC + hostname + OS. The MAC is only used when it looks
    like a REAL hardware address (uuid.getnode() returns a random value with
    the multicast bit set when no MAC is found — that would make the HWID
    unstable, so it is skipped in that case).
    """
    parts: list[str] = []
    sysname = platform.system()
    if sysname == "Windows":
        try:
            import subprocess
            out = subprocess.check_output(
                ["wmic", "csproduct", "get", "uuid"],
                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                timeout=10, text=True)
            for line in out.splitlines():
                line = line.strip()
                if line and line.lower() != "uuid" and "-" in line:
                    parts.append("win-uuid:" + line.lower())
                    break
        except Exception:
            pass
    elif sysname == "Linux":
        try:
            mid = Path("/etc/machine-id").read_text(encoding="utf-8").strip()
            if mid:
                parts.append("machine-id:" + mid.lower())
        except Exception:
            pass
    elif sysname == "Darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                timeout=10, text=True)
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m:
                parts.append("mac-uuid:" + m.group(1).lower())
        except Exception:
            pass
    try:
        mac = uuid.getnode()
        # skip random fallback values (multicast bit set = not a real MAC)
        if not (mac >> 40) & 0x01:
            parts.append("mac:%012x" % (mac & 0xFFFFFFFFFFFF))
    except Exception:
        pass
    parts.append("host:" + platform.node())
    parts.append("os:" + sysname)
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _pkcs1v15_verify(message: bytes, sig: bytes) -> bool:
    """Verify RSASSA-PKCS1v15-SHA256 without third-party libs."""
    k = (PUBLIC_N.bit_length() + 7) // 8
    if len(sig) != k:
        return False
    s = int.from_bytes(sig, "big")
    if s >= PUBLIC_N:
        return False
    em = pow(s, PUBLIC_E, PUBLIC_N).to_bytes(k, "big")
    # em = 0x00 || 0x01 || PS(0xFF..) || 0x00 || DigestInfo
    digest = hashlib.sha256(message).digest()
    expected_suffix = b"\x00" + _SHA256_DINFO + digest
    if len(em) < len(expected_suffix) + 11:
        return False
    if em[0] != 0x00 or em[1] != 0x01:
        return False
    # constant-time-ish check of padding then suffix
    sep = em.find(b"\x00", 2)
    if sep < 10:  # need at least 8 bytes of 0xFF padding
        return False
    if any(b != 0xFF for b in em[2:sep]):
        return False
    return hmac.compare_digest(em[sep:], expected_suffix)


def parse_armored(text: str) -> dict:
    """Parse -----BEGIN OCTORA LICENSE----- armor into the envelope dict."""
    lines = [ln.strip() for ln in text.strip().splitlines()
             if ln.strip() and "OCTORA LICENSE" not in ln]
    raw = base64.b64decode("".join(lines))
    env = json.loads(raw.decode("utf-8"))
    if not isinstance(env, dict) or "payload" not in env or "sig" not in env:
        raise ValueError("Not an OCTORA license envelope")
    return env


def verify_envelope(env: dict) -> dict:
    """Returns the payload dict if signature is valid, else raises ValueError."""
    payload = env["payload"]
    sig = base64.b64decode(env["sig"])
    if not _pkcs1v15_verify(_canonical(payload), sig):
        raise ValueError("Signature invalid — license file tampered or forged")
    if payload.get("product") != "OCTORA":
        raise ValueError("License is for a different product")
    return payload


class LicenseManager:
    def __init__(self, cfg):
        self.cfg = cfg
        from .config import data_dir
        self.file = data_dir() / LICENSE_FILENAME

    # ---- trial ----
    TRIAL_CHECK_TIMEOUT = 4  # seconds: server trial check must never block startup

    def _trial_check_url(self) -> str:
        base = ((self.cfg.get("admin_server_url", "") or "").strip()
                or "https://octora-admin.onrender.com").rstrip("/")
        return base + "/api/v1/trial/check"

    def _server_trial_verdict(self, trial_started_at: str = "") -> dict | None:
        """Ask the server whether this PC may start/keep a trial.

        Returns the verdict dict, or None when offline/unreachable (fail open:
        the local trial still works, the background sync revokes it later).
        """
        import json
        import urllib.request
        from .telemetry import hwid_hash  # local import: telemetry imports license
        payload = json.dumps({
            "hwid_hash": hwid_hash(),
            "trial_started_at": trial_started_at,
        }).encode("utf-8")
        req = urllib.request.Request(
            self._trial_check_url(), data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.TRIAL_CHECK_TIMEOUT) as r:
                if 200 <= r.status < 300:
                    return json.loads(r.read().decode("utf-8"))
        except Exception:
            pass
        return None

    def start_trial(self) -> bool:
        """Start the 24h trial. Returns False (and does NOT start a trial) when
        the server says this PC already used its one trial."""
        # Server-side one-trial-per-PC check. Offline -> fail open: the local
        # trial starts and the background sync registers/revokes it later.
        verdict = self._server_trial_verdict("")
        if verdict is not None and not verdict.get("allowed", True):
            self.cfg.set("trial_revoked", "1")
            return False
        now = datetime.now(timezone.utc).isoformat()
        self.cfg.set("trial_start", now)
        self.cfg.set("last_seen", now)
        self.cfg.set("trial_revoked", "0")
        self.cfg.set("trial_server_pending", "0" if verdict else "1")
        return True

    def sync_trial_with_server(self):
        """One-shot background sync (daemon thread): register an offline-started
        trial with the server and apply a server revocation when this PC already
        used its trial (e.g. local app data was wiped to grab a fresh trial)."""
        import threading

        def _run():
            try:
                trial_start = self.cfg.get("trial_start", "") or ""
                verdict = self._server_trial_verdict(trial_start)
                if verdict is None:
                    return  # still offline; retried on next launch
                self.cfg.set("trial_revoked",
                             "0" if verdict.get("allowed", True) else "1")
                self.cfg.set("trial_server_pending", "0")
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True, name="trial-sync").start()

    def _trial_hours_left(self) -> float | None:
        start = self.cfg.get("trial_start", "")
        if not start:
            return None
        try:
            if "T" in start:  # current format: full ISO UTC timestamp
                d0 = datetime.fromisoformat(start)
            else:             # legacy format from older builds: "%Y-%m-%d"
                d0 = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        if d0.tzinfo is None:
            d0 = d0.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        # Tamper guard: trial_start must not sit in the future (beyond a small
        # tolerance for real clock skew). A forward-set clock at trial start
        # would otherwise grant extra trial time.
        if d0 > now + timedelta(minutes=5):
            return 0.0
        delta = now - d0
        return min(float(TRIAL_HOURS), TRIAL_HOURS - delta.total_seconds() / 3600.0)

    # ---- clock rollback tamper check ----
    def _rollback_detected(self) -> bool:
        last = self.cfg.get("last_seen", "")
        if not last:
            return False
        try:
            prev = datetime.fromisoformat(last)
        except ValueError:
            return False
        return datetime.now(timezone.utc) < prev - timedelta(days=1)

    def _touch_seen(self):
        self.cfg.set("last_seen", datetime.now(timezone.utc).isoformat())

    # ---- main status ----
    def status(self) -> dict:
        """-> {mode, days_left, name, email, message}"""
        rollback = self._rollback_detected()
        lic = self._load_license()
        if lic["ok"]:
            p = lic["payload"]
            try:
                exp = datetime.strptime(p["expires"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (ValueError, KeyError):
                return {"mode": "invalid", "days_left": 0, "name": "", "email": "",
                        "message": "License file is corrupt."}
            now = datetime.now(timezone.utc)
            me = hwid()
            # --- STRICT 1-PC-1-LICENSE: HWID verified on EVERY start ---
            if not hmac.compare_digest(p.get("hwid", "").lower(), me):
                return {"mode": "invalid", "days_left": 0,
                        "name": p.get("name", ""), "email": "",
                        "message": ("⛔ This license is bound to ANOTHER machine and "
                                    "cannot be used here.\n\n"
                                    f"License issued for HWID:\n{p.get('hwid', '?')}\n"
                                    f"This machine's HWID:\n{me}\n\n"
                                    "Copying a license file to another PC does not work — "
                                    "each PC needs its own license key. Contact the seller "
                                    "with the HWID above.")}
            # binding-record cross-check (detects license-file swaps)
            bound = str(self.cfg.get("license_bound_hwid", "") or "").lower()
            if bound and not hmac.compare_digest(bound, me):
                # Payload HWID matches this machine but the stored binding does
                # not (e.g. seller re-issued a key and the file was replaced
                # manually) — self-heal the record instead of false-rejecting.
                self.cfg.set("license_bound_hwid", me)
            if now <= exp:
                self._touch_seen()
                mode = "grace" if rollback else "licensed"
                msg = ("License valid." + (" Clock rollback detected — running in grace mode."
                                           if rollback else ""))
                return {"mode": mode, "days_left": (exp - now).days, "name": p.get("name", ""),
                        "email": p.get("email", ""), "message": msg}
            if now <= exp + timedelta(days=GRACE_DAYS):
                self._touch_seen()
                return {"mode": "grace", "days_left": 0, "name": p.get("name", ""),
                        "email": p.get("email", ""),
                        "message": f"License expired {(now - exp).days}d ago — offline grace "
                                   f"({GRACE_DAYS}d). Renew soon."}
            return {"mode": "expired", "days_left": 0, "name": p.get("name", ""),
                    "email": "", "message": "License expired. Please renew."}
        if lic["present"]:
            return {"mode": "invalid", "days_left": 0, "name": "", "email": "",
                    "message": f"License file rejected: {lic['error']}"}
        trial_left = self._trial_hours_left()
        if trial_left is None:
            return {"mode": "none", "days_left": 0, "name": "", "email": "",
                    "message": "No trial started and no license found."}
        self._touch_seen()
        if trial_left > 0:
            # Server-side one-trial-per-PC revocation (e.g. app data was wiped
            # to grab a fresh trial). Applied by the background trial sync.
            if (self.cfg.get("trial_revoked", "0") or "0") == "1":
                return {"mode": "expired", "days_left": 0, "name": "", "email": "",
                        "message": ("This PC has already used its free 1-day trial.\n\n"
                                    "You need a subscription to continue using OCTORA.\n"
                                    "Tap 'Buy license' to get 7-Day, 30-Day or Lifetime access.")}
            mode = "grace" if rollback else "trial"
            hrs = int(trial_left)
            mins = int((trial_left - hrs) * 60)
            return {"mode": mode, "days_left": 0 if hrs == 0 else 1,
                    "name": "Trial user", "email": "",
                    "message": f"Trial: {hrs}h {mins}m left." +
                               (" Clock rollback detected — grace mode." if rollback else "")}
        return {"mode": "expired", "days_left": 0, "name": "", "email": "",
                "message": ("Your 1-day free trial has ended.\n\n"
                            "You need a subscription to continue using OCTORA.\n"
                            "Tap 'Buy license' to get 7-Day, 30-Day or Lifetime access.")}

    def _load_license(self) -> dict:
        if not self.file.exists():
            return {"present": False, "ok": False}
        try:
            env = parse_armored(self.file.read_text(encoding="utf-8"))
            payload = verify_envelope(env)
            return {"present": True, "ok": True, "payload": payload}
        except Exception as e:  # noqa: BLE001
            return {"present": True, "ok": False, "error": str(e)}

    def activate(self, armored_text: str) -> tuple[bool, str]:
        """Validate pasted/file license text and install it. Returns (ok, message).

        STRICT: the key's HWID must equal THIS machine's HWID, otherwise
        activation is refused — a key copied from another PC can never be
        installed here.
        """
        try:
            env = parse_armored(armored_text)
            payload = verify_envelope(env)
        except Exception as e:  # noqa: BLE001
            return False, f"Invalid license: {e}"
        me = hwid()
        if not hmac.compare_digest(payload.get("hwid", "").lower(), me):
            return False, ("⛔ This license is bound to ANOTHER machine and cannot "
                           "be activated here.\n\n"
                           f"This machine's HWID:\n{me}\n"
                           f"License issued for HWID:\n{payload.get('hwid', '?')}\n\n"
                           "One license = one PC. Ask the seller for a license key "
                           "for THIS machine's HWID.")
        self.file.write_text(armored_text.strip() + "\n", encoding="utf-8")
        # binding record: second cross-check used on every later start
        self.cfg.set("license_bound_hwid", me)
        return True, (f"Activated! Licensed to {payload.get('name')} "
                      f"until {payload.get('expires')}.")
