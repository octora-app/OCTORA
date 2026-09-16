"""App configuration: paths + JSON config file (credentials live here, never hardcoded)."""
import json
import os
from pathlib import Path

APP_NAME = "OCTORA"


def data_dir() -> Path:
    override = os.environ.get("OCTORA_DATA_DIR")
    if override:
        p = Path(override)
    elif os.name == "nt":
        p = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    else:
        p = Path.home() / ".octora"
    p.mkdir(parents=True, exist_ok=True)
    (p / "drive").mkdir(parents=True, exist_ok=True)
    (p / "assets").mkdir(parents=True, exist_ok=True)
    return p


def resource_path(rel: str) -> str:
    """Path to a bundled asset (works inside a PyInstaller bundle too)."""
    import sys
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
    return str(base / rel)


DEFAULTS = {
    "demo_mode": True,
    "operator": "docock_op",
    "drive_folder": "",
    "asset_folder": "",
    "backup_folder": "",
    "auto_delete_after_success": True,  # delete local file after verified upload+post
    "keep_backup": False,               # ...or move it to backup_folder instead
    "auto_queue_after_drive": True,     # auto-publish after Drive upload
    "default_platform": "IG Reels",     # YT Shorts | IG Reels | TikTok | FB Reels
    "google_client_id": "",        # BYO (v1.4+): customer's OWN Google Cloud OAuth
    "google_client_secret": "",     # client → uploads count on THEIR 100/day quota.
                                    # Empty = use seller's bundled client (shared quota).
    "google_refresh_token": "",     # CUSTOMER token (per-machine, from Connect flow)
    "google_access_token": "",
    "google_account_email": "",
    "drive_folder_id": "",
    "meta_access_token": "",        # CUSTOMER Meta token (per-machine)
    "meta_token_obtained_at": 0,
    "meta_user_name": "",
    "meta_user_email": "",
    "meta_pages": [],               # [{id, name, access_token}]
    "meta_page_id": "",
    "instagram_business_id": "",
    "instagram_username": "",
    "tiktok_access_token": "",      # CUSTOMER TikTok token (per-machine)
    "tiktok_refresh_token": "",
    "tiktok_open_id": "",
    "tiktok_display_name": "",
    "tiktok_token_obtained_at": 0,
    "youtube_api_key": "",
    "youtube_client_id": "",
    "youtube_client_secret": "",
    "instagram_token": "",
    "instagram_user_id": "",
    "tiktok_client_key": "",
    "tiktok_access_token": "",
    "facebook_page_token": "",
    "facebook_page_id": "",
    "accent": "red",          # red | cyan | violet
    "minimize_to_tray": True,
    "poll_seconds": 15,
    "trial_start": "",
    "last_seen": "",
    # ---- v1.3 admin-panel / telemetry wiring ----
    "telemetry_consent": False,          # master switch, set by first-run dialog
    "consent_asked": "",                 # "1" once the first-run dialog was shown
    "admin_server_url": "",              # e.g. https://octora-admin-xxxx.onrender.com
    "update_manifest_url": "",           # override; default https://octora.pages.dev/releases/latest.json
    "telemetry_last_validate": "",       # ISO ts of last successful server validation
    "telemetry_last_validate_ok": "",    # "1"/"0"
    "google_channel_name": "",           # cached at connect time (telemetry display)
    "google_subscriber_count": 0,
    # ---- v1.4 autopilot: free stock sources + metadata AI ----
    "autopilot_enabled": True,           # master switch for the NicheScheduler
    "pexels_api_key": "",                # free at pexels.com/api
    "pixabay_api_key": "",               # free at pixabay.com/api/docs
    "gemini_api_key": "",                # free at aistudio.google.com
}


class Config:
    def __init__(self):
        self.path = data_dir() / "config.json"
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if self.path.exists():
                self._data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            pass
        # resolve default folders
        if not self._data.get("drive_folder"):
            self._data["drive_folder"] = str(data_dir() / "drive")
        if not self._data.get("asset_folder"):
            self._data["asset_folder"] = str(data_dir() / "assets")

    def save(self):
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(self, key, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def update(self, mapping: dict):
        self._data.update(mapping)
        self.save()

    @property
    def demo_mode(self) -> bool:
        return bool(self.get("demo_mode", True))
