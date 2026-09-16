"""Seller-bundled OAuth credentials (v1.1+).

The SELLER (Sudeep) registers ONE Google Cloud project, ONE Meta app and ONE
TikTok app, and pastes the credentials into octora/seller_config.json ONCE
before building the EXE / shipping the ZIP. That file is bundled with the app
(works inside a PyInstaller bundle too).

END CUSTOMERS never see or touch API keys: they click "Connect to YouTube",
"Connect to Google Drive", etc. on the Platforms screen and sign in with
their OWN accounts. Their personal tokens are stored per-machine in the
user config file (~/.octora or %APPDATA%/OCTORA), never in this file.

Environment variables can override the JSON (useful for CI/builds):
  OCTORA_SELLER_GOOGLE_CLIENT_ID / OCTORA_SELLER_GOOGLE_CLIENT_SECRET
  OCTORA_SELLER_META_APP_ID      / OCTORA_SELLER_META_APP_SECRET
  OCTORA_SELLER_TIKTOK_CLIENT_KEY / OCTORA_SELLER_TIKTOK_CLIENT_SECRET
"""
import json
import os
from pathlib import Path

from .config import resource_path

_FILENAME = "seller_config.json"

_cache = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    data: dict = {}
    # 1) bundled JSON (source tree or PyInstaller bundle)
    try:
        p = Path(resource_path(os.path.join("octora", _FILENAME)))
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    # 2) environment overrides win
    env_map = {
        ("google", "client_id"): "OCTORA_SELLER_GOOGLE_CLIENT_ID",
        ("google", "client_secret"): "OCTORA_SELLER_GOOGLE_CLIENT_SECRET",
        ("meta", "app_id"): "OCTORA_SELLER_META_APP_ID",
        ("meta", "app_secret"): "OCTORA_SELLER_META_APP_SECRET",
        ("tiktok", "client_key"): "OCTORA_SELLER_TIKTOK_CLIENT_KEY",
        ("tiktok", "client_secret"): "OCTORA_SELLER_TIKTOK_CLIENT_SECRET",
    }
    for (section, key), env in env_map.items():
        val = os.environ.get(env, "").strip()
        if val:
            data.setdefault(section, {})[key] = val
    _cache = data
    return data


def _pair(section: str, k1: str, k2: str):
    d = _load().get(section, {})
    a = str(d.get(k1, "") or "").strip()
    b = str(d.get(k2, "") or "").strip()
    if a and b:
        return a, b
    return None


def google() -> tuple[str, str] | None:
    """Seller's Google OAuth client (Desktop-app type)."""
    return _pair("google", "client_id", "client_secret")


def meta() -> tuple[str, str] | None:
    """Seller's Meta app id + app secret."""
    return _pair("meta", "app_id", "app_secret")


def tiktok() -> tuple[str, str] | None:
    """Seller's TikTok app client key + secret."""
    return _pair("tiktok", "client_key", "client_secret")


def google_ready() -> bool:
    return google() is not None


def meta_ready() -> bool:
    return meta() is not None


def tiktok_ready() -> bool:
    return tiktok() is not None


def status() -> dict:
    """For diagnostics / the Platforms screen seller check."""
    return {"google": google_ready(), "meta": meta_ready(), "tiktok": tiktok_ready()}


def reset_cache():
    global _cache
    _cache = None
