"""Platform registry. OCTORA is YouTube-only: the only plugin is YouTube.

To add a platform later: write one plugin file, append it here.
"""
from .base import PlatformPlugin
from .youtube import YouTubePlugin

PLUGINS: list[PlatformPlugin] = [
    YouTubePlugin(),
]

_BY_ID = {p.id: p for p in PLUGINS}

# queue/scheduler label -> plugin id.
# Old labels ("IG Reels", "TikTok", "FB Reels") map to "youtube" so rows
# created by older versions keep working instead of breaking the queue.
LABEL_TO_ID = {
    "YT Shorts": "youtube",
    "IG Reels": "youtube",
    "TikTok": "youtube",
    "FB Reels": "youtube",
    "Both": "youtube",
}
ID_TO_LABEL = {"youtube": "YT Shorts"}


def get_platform(pid: str) -> PlatformPlugin | None:
    return _BY_ID.get(pid)


def plugin_for_label(label: str) -> PlatformPlugin:
    return _BY_ID.get(LABEL_TO_ID.get(label, "youtube"))


def platform_enabled(cfg, pid: str) -> bool:
    return cfg.get(f"platform_{pid}_enabled", True) not in (False, "0", 0, "false")
