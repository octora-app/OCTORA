"""TikTok plugin — COMING SOON.

TikTok's Content Posting API requires an approved TikTok developer app +
audit before direct posting works. Until the seller's app passes audit,
the platform is marked coming-soon in the UI and live publish attempts
are refused outright — never faked.
"""
from .base import PlatformPlugin


class TikTokPlugin(PlatformPlugin):
    id = "tiktok"
    name = "TikTok"
    icon = "\U0001F3B5"
    color = "#25f4ee"
    description = "Direct posting via TikTok Content Posting API — coming soon."
    coming_soon = True

    def credential_fields(self):
        return []  # coming soon: no credentials collected yet

    def setup_help(self):
        return ("🚧 Coming soon — TikTok direct posting ships after TikTok audits "
                "the seller's developer app. Meanwhile YouTube, Instagram and "
                "Facebook reels publish from this app.")

    def is_configured(self, cfg):
        return False  # coming soon: never reports ready

    def publish(self, asset_path, meta, cfg, demo):
        if demo:
            return self._demo_publish(asset_path, meta)
        return False, ("LIVE TikTok: coming soon — direct posting is not enabled yet "
                       "(needs TikTok's Content Posting API audit on the seller's app). "
                       "Nothing was posted.")
