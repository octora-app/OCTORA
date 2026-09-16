"""Social-link video discovery for Autopilot (source_type='links').

Each niche lists newline-separated YouTube URLs — direct video URLs,
channel URLs, or playlist URLs.
yt-dlp enumerates the videos in flat-playlist mode WITHOUT downloading any
media; the existing DownloadWorker fetches the actual bytes later through the
same yt-dlp pipeline.

Discovery never raises and never blocks the scheduler: per-link failures are
logged and skipped.
"""
import shutil
import subprocess

from .logger import get_logger

log = get_logger("octora.linkdiscovery")

YTDLP_TIMEOUT = 120


def source_of(url: str) -> str:
    """youtube | other — from the URL domain."""
    u = (url or "").lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return "other"


def discover_new_videos(link: str, timeout: int = YTDLP_TIMEOUT) -> list:
    """Enumerate videos for one link.

    Returns a list of {source, source_id, page_url, title}. Empty list on any
    failure (yt-dlp missing, login-walled/private content, network error…).
    Never raises.
    """
    link = (link or "").strip()
    if not link:
        return []
    exe = shutil.which("yt-dlp")
    if not exe:
        log.warning("linkdiscovery: yt-dlp not found — pip install yt-dlp "
                    "(link skipped: %s)", link[:60])
        return []
    src = source_of(link)
    try:
        r = subprocess.run(
            [exe, "--flat-playlist", "--no-warnings", "--no-check-certificate",
             "--print", "%(id)s\t%(title)s\t%(webpage_url)s\t%(url)s", link],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        log.warning("linkdiscovery: timed out (%s)", link[:60])
        return []
    except Exception as e:  # noqa: BLE001
        log.warning("linkdiscovery: failed (%s): %s", link[:60], e)
        return []
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()
        hint = err[-1][-160:] if err else "yt-dlp failed"
        log.warning("linkdiscovery: %s -> %s", link[:60], hint)
        return []
    out = []
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        vid, title = parts[0].strip(), (parts[1] or "").strip()
        page_url = (parts[2] or "").strip()
        raw_url = parts[3].strip() if len(parts) > 3 else ""
        if not vid:
            continue
        if not page_url and raw_url.startswith("http"):
            page_url = raw_url
        if not page_url:
            continue  # can't queue what we can't download later
        out.append({
            "source": src,
            "source_id": vid,
            "page_url": page_url,
            "title": title or vid,
        })
    log.info("linkdiscovery: %d video(s) from %s (%s)", len(out), src, link[:60])
    return out
