"""Platform registry. To add a platform: write one plugin file, append it here."""
from .base import PlatformPlugin
from .youtube import YouTubePlugin
from .instagram import InstagramPlugin
from .tiktok import TikTokPlugin
from .facebook import FacebookPlugin

PLUGINS: list[PlatformPlugin] = [
    YouTubePlugin(),
    InstagramPlugin(),
    TikTokPlugin(),
    FacebookPlugin(),
]

_BY_ID = {p.id: p for p in PLUGINS}

# queue/scheduler label -> plugin id (keeps old DB rows working)
LABEL_TO_ID = {
    "YT Shorts": "youtube",
    "IG Reels": "instagram",
    "TikTok": "tiktok",
    "FB Reels": "facebook",
}
ID_TO_LABEL = {v: k for k, v in LABEL_TO_ID.items()}


def get_platform(pid: str) -> PlatformPlugin | None:
    return _BY_ID.get(pid)


def plugin_for_label(label: str) -> PlatformPlugin:
    return _BY_ID.get(LABEL_TO_ID.get(label, "youtube"))


def platform_enabled(cfg, pid: str) -> bool:
    return cfg.get(f"platform_{pid}_enabled", True) not in (False, "0", 0, "false")
