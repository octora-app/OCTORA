"""TikTok plugin.

Honest v1.0 state: TikTok's Content Posting API requires an approved TikTok
developer app + audit before direct posting works. Credential slots are ready;
live posting reports exactly this instead of faking a post.
"""
from .base import PlatformPlugin


class TikTokPlugin(PlatformPlugin):
    id = "tiktok"
    name = "TikTok"
    icon = "🎵"
    color = "#25f4ee"
    description = "Direct posting via TikTok Content Posting API (needs approved app)."

    def credential_fields(self):
        return []  # v1.1: customers use the "Connect TikTok" button (seller OAuth)

    def setup_help(self):
        return ("No API keys needed. Click 'Connect TikTok' on the Platforms "
                "screen and sign in.\n"
                "NOTE: direct posting needs TikTok's Content Posting API audit "
                "approved on the seller's app — the button will tell you the status.")

    def is_configured(self, cfg):
        from ..core import seller_config
        return bool(cfg.get("tiktok_refresh_token") or
                    cfg.get("tiktok_access_token")) and seller_config.tiktok_ready()

    def publish(self, asset_path, meta, cfg, demo):
        if demo:
            return self._demo_publish(asset_path, meta)
        if not self.is_configured(cfg):
            return False, "LIVE TikTok: not connected — click 'Connect TikTok'."
        return False, ("LIVE TikTok: direct upload needs TikTok's Content Posting API "
                       "audit approved on the seller's app. Credentials are stored; "
                       "provider call ships next update. Not faked.")
