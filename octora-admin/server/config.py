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
