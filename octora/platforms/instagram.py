"""Instagram Reels plugin.

Honest v1.0 state: the Meta Graph API publishes reels from a PUBLIC video_url
(Meta's servers must be able to download the file). OCTORA stores files locally,
so live posting additionally needs a public file host. Until that is wired,
live mode reports exactly this instead of faking a post.
"""
from .base import PlatformPlugin


class InstagramPlugin(PlatformPlugin):
    id = "instagram"
    name = "Instagram Reels"
    icon = "📸"
    color = "#e1306c"
    description = "Publishes reels via the Instagram Graph API (needs a public video URL)."

    def credential_fields(self):
        return []  # v1.1: customers use the "Connect Instagram" button (seller OAuth)

    def setup_help(self):
        return ("No API keys needed. Click 'Connect Instagram' on the Platforms "
                "screen and sign in with Facebook.")

    def is_configured(self, cfg):
        from ..core import seller_config
        return bool(cfg.get("meta_access_token")) and seller_config.meta_ready()

    def publish(self, asset_path, meta, cfg, demo):
        if demo:
            return self._demo_publish(asset_path, meta)
        if not self.is_configured(cfg):
            return False, "LIVE Instagram: not connected — click 'Connect Instagram'."
        if not cfg.get("instagram_business_id"):
            return False, ("LIVE Instagram: no Business/Creator account linked to your "
                           "Facebook Pages — link one in the Instagram app, then reconnect.")
        caption = self._meta_caption(meta)
        # caption is staged and ready; the actual provider call still needs a
        # PUBLIC video_url (Meta's servers must download the file), which
        # OCTORA has no file host for yet — reported honestly, never faked.
        return False, ("LIVE Instagram: Meta requires a PUBLIC video_url for reels and "
                       "OCTORA has no file host wired yet — provider call ships next "
                       f"update. Caption staged ({len(caption)} chars). Not faked.")
