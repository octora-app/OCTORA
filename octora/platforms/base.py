"""Platform plugin base class.

Adding a new platform later = create one file in this package subclassing
PlatformPlugin, then register it in __init__.py. No other code changes needed.
"""
from __future__ import annotations


class PlatformPlugin:
    """One publish destination (YouTube Shorts)."""
    id: str = "base"
    name: str = "Base"
    icon: str = "🔌"
    color: str = "#8b95a3"
    description: str = ""

    # -- credentials -----------------------------------------------------
    def credential_fields(self) -> list[tuple[str, str, str]]:
        """[(config_key, label, placeholder), ...] shown in Settings."""
        return []

    def setup_help(self) -> str:
        """Short human guide: how the user gets the credentials."""
        return ""

    def is_configured(self, cfg) -> bool:
        return all(cfg.get(k) for k, _, _ in self.credential_fields())

    def status(self, cfg, demo_mode: bool) -> tuple[str, str]:
        """-> (badge_text, badge_color_key)."""
        if demo_mode:
            return "DEMO", "amber"
        if not self.is_configured(cfg):
            return "NEEDS CREDENTIALS", "red"
        return "READY", "green"

    # -- publishing ------------------------------------------------------
    def publish(self, asset_path: str, meta: dict, cfg, demo: bool) -> tuple[bool, str]:
        """Attempt a post. `meta` holds the SEO engine output:
        {"title", "description", "tags" (list), "caption"}.
        Returns (ok, message). Never fake a real post: in live mode without
        working provider code, return (False, <reason>)."""
        raise NotImplementedError

    # -- helpers ---------------------------------------------------------
    def _demo_publish(self, asset_path: str, meta: dict | None = None) -> tuple[bool, str]:
        import os
        name = os.path.basename(asset_path) if asset_path else "clip.mp4"
        title = (meta or {}).get("title") or name
        return True, f"demo post simulated OK ({name}) — title: {title!r}"

    @staticmethod
    def _meta_caption(meta, fallback: str = "") -> str:
        if isinstance(meta, dict):
            return meta.get("caption") or meta.get("title") or fallback
        return str(meta or fallback)  # back-compat if a plain caption string arrives
