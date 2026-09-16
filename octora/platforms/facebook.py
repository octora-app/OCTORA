"""Facebook Reels plugin.

Honest v1.0 state: Reels publish via the Page video upload API. Credential slots
are ready; the live call is stubbed until the upload-session flow is wired.
"""
from .base import PlatformPlugin


class FacebookPlugin(PlatformPlugin):
    id = "facebook"
    name = "Facebook Reels"
    icon = "📘"
    color = "#1877f2"
    description = "Publishes reels to a Facebook Page via the Graph API."

    def credential_fields(self):
        return []  # v1.1: customers use the "Connect Facebook" button (seller OAuth)

    def setup_help(self):
        return ("No API keys needed. Click 'Connect Facebook' on the Platforms "
                "screen and sign in, then pick the Page to post reels to.")

    def is_configured(self, cfg):
        from ..core import oauth, seller_config
        return oauth.meta_page_token(cfg) is not None and seller_config.meta_ready()

    def publish(self, asset_path, meta, cfg, demo):
        if demo:
            return self._demo_publish(asset_path, meta)
        if not self.is_configured(cfg):
            return False, "LIVE Facebook: not connected — click 'Connect Facebook'."
        return False, ("LIVE Facebook: reels upload-session flow ships in the next "
                       "update. Credentials are stored. Not faked.")
