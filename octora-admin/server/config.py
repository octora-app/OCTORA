"""Environment configuration for the OCTORA admin panel."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'octora_admin.db'}")

ADMIN_PASSWORD = os.environ.get("OCTORA_ADMIN_PASSWORD", "")

# Seller private key: either a filesystem path ...
SELLER_KEY_PATH = os.environ.get("OCTORA_SELLER_KEY", "")
# ... or the raw PEM text (handy on free hosts where file upload is awkward)
SELLER_KEY_PEM = os.environ.get("OCTORA_SELLER_PEM", "")

SESSION_HOURS = int(os.environ.get("OCTORA_SESSION_HOURS", "12"))
HEARTBEAT_PRUNE_DAYS = 120
APP_NAME = "OCTORA Admin"

# ---------------------------------------------------------------- payments
# Subscription plans: id -> {name, days, price_usdt}. Lifetime = 100 years.
# USDT (TRC-20) receiving address — where customers pay for licenses.
SELLER_USDT_TRC20 = os.environ.get(
    "OCTORA_USDT_TRC20", "TVTjQKqYuntgk6EfD6PqeFvezZnVCCimjz")
# Tether USD contract on Tron (TRC-20)
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TRONGRID_API = os.environ.get("TRONGRID_API", "https://api.trongrid.io")
# Optional TronGrid API key (free tier raises rate limits); anonymous works.
TRONGRID_API_KEY = os.environ.get("TRONGRID_API_KEY", "")

# Payment finality: a transfer must be this old (seconds) before a license is
# issued. Tron's ~3s DPoS blocks make a 90s-old transaction irreversible for
# all practical purposes; this defeats re-org / double-spend tricks.
MIN_TX_AGE_SECONDS = int(os.environ.get("OCTORA_MIN_TX_AGE_SECONDS", "90"))

# Rate limits (per IP, sliding window) on abuse-sensitive endpoints.
RATE_LIMIT_PAY_VERIFY = int(os.environ.get("OCTORA_RL_PAY_VERIFY", "10"))    # per minute
RATE_LIMIT_ACTIVATE = int(os.environ.get("OCTORA_RL_ACTIVATE", "30"))        # per minute
RATE_LIMIT_REBIND = int(os.environ.get("OCTORA_RL_REBIND", "10"))            # per minute

# HWID rebind policy: at most one approved rebind per license per this many days.
REBIND_COOLDOWN_DAYS = int(os.environ.get("OCTORA_REBIND_COOLDOWN_DAYS", "30"))
PLANS = {
    "weekly":   {"name": "7-Day",   "days": 7,     "price_usdt": 10.0},
    "monthly":  {"name": "30-Day",  "days": 30,    "price_usdt": 30.0},
    "lifetime": {"name": "Lifetime", "days": 36500, "price_usdt": 100.0},
}

# Auto-update manifest served at /api/v1/updates/latest (also mirrored as a
# static file on the website). Edit when shipping a new version.
UPDATE_MANIFEST = {
    "version": os.environ.get("OCTORA_LATEST_VERSION", "1.4.0"),
    "download_url": os.environ.get(
        "OCTORA_DOWNLOAD_URL",
        "https://github.com/OCTORA-app/OCTORA/releases/latest/download/OCTORA-Setup.exe"),
    "changelog": os.environ.get(
        "OCTORA_CHANGELOG",
        "1-day free trial, USDT (TRC-20) auto-licensing, one-click auto-updates."),
    "mandatory": False,
}
