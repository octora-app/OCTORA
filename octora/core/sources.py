"""Free stock-video sources for Autopilot: Pexels (primary) + Pixabay (fallback).

Both offer free API keys (Pexels: pexels.com/api, Pixabay: pixabay.com/api/docs).
Keys are read from settings (pexels_api_key / pixabay_api_key) — never hardcoded.

Normalized video dict shape:
    {source, source_id, page_url, duration, width, height,
     tags, photographer, file_url}
"""
import json as _json
import urllib.parse as _parse
import urllib.request as _req
import urllib.error as _err

PEXELS_SEARCH = "https://api.pexels.com/videos/search"
PIXABAY_SEARCH = "https://pixabay.com/api/videos/"
_TIMEOUT = 25


def _http_get(url: str, headers: dict | None = None,
              params: dict | None = None) -> tuple[bool, dict | str]:
    """GET -> (True, parsed_json) or (False, reason)."""
    try:
        full = url + ("?" + _parse.urlencode(params) if params else "")
        r = _req.Request(full, headers=headers or {}, method="GET")
        with _req.urlopen(r, timeout=_TIMEOUT) as resp:
            return True, _json.loads(resp.read().decode("utf-8", "replace"))
    except _err.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:160]
        except Exception:  # noqa: BLE001
            detail = ""
        return False, f"HTTP {e.code}: {detail or e.reason}"
    except Exception as e:  # noqa: BLE001  (DNS, timeout, TLS, JSON…)
        return False, f"network error: {e}"


def _pick_pexels_file(video_files: list) -> dict | None:
    """Best portrait mp4: smallest width>=720 that is portrait, else first mp4."""
    mp4s = [f for f in (video_files or [])
            if isinstance(f, dict) and f.get("link")
            and ("mp4" in str(f.get("file_type", "")).lower()
                 or str(f.get("link", "")).lower().endswith(".mp4"))]
    if not mp4s:
        return None
    portrait = [f for f in mp4s
                if (f.get("height") or 0) >= (f.get("width") or 0)
                and (f.get("width") or 0) >= 720]
    if portrait:
        return min(portrait, key=lambda f: f["width"])
    return mp4s[0]


def pexels_search(api_key: str, query: str,
                  per_page: int = 20) -> tuple[list, str]:
    """Returns (videos, reason). reason is 'pexels' on success."""
    if not (api_key or "").strip():
        return [], "no Pexels API key — add one in Settings → Autopilot (free at pexels.com/api)"
    ok, data = _http_get(
        PEXELS_SEARCH,
        headers={"Authorization": (api_key or "").strip()},
        params={"query": query, "per_page": max(1, min(80, per_page)),
                "orientation": "portrait", "size": "medium"})
    if not ok:
        return [], f"Pexels error: {data}"
    out = []
    for v in (data.get("videos") or []):
        f = _pick_pexels_file(v.get("video_files"))
        if not f:
            continue
        out.append({
            "source": "pexels",
            "source_id": str(v.get("id", "")),
            "page_url": v.get("url", ""),
            "duration": v.get("duration") or 0,
            "width": f.get("width") or 0,
            "height": f.get("height") or 0,
            "tags": [],
            "photographer": v.get("user", {}).get("name", "") if isinstance(v.get("user"), dict) else "",
            "file_url": f["link"],
        })
    if not out:
        return [], "Pexels returned no usable portrait videos for this query"
    return out, "pexels"


def _pick_pixabay_file(variants: dict) -> dict | None:
    """Prefer medium (portrait-friendly), then large, small, tiny."""
    if not isinstance(variants, dict):
        return None
    for name in ("medium", "large", "small", "tiny"):
        v = variants.get(name)
        if isinstance(v, dict) and v.get("url"):
            return v
    for v in variants.values():
        if isinstance(v, dict) and v.get("url"):
            return v
    return None


def pixabay_search(api_key: str, query: str,
                   per_page: int = 20) -> tuple[list, str]:
    """Returns (videos, reason). reason is 'pixabay' on success."""
    if not (api_key or "").strip():
        return [], "no Pixabay API key — add one in Settings → Autopilot (free at pixabay.com/api/docs)"
    ok, data = _http_get(
        PIXABAY_SEARCH,
        params={"key": (api_key or "").strip(), "q": query,
                "per_page": max(3, min(200, per_page)),
                "orientation": "vertical", "video_type": "all"})
    if not ok:
        return [], f"Pixabay error: {data}"
    out = []
    for h in (data.get("hits") or []):
        f = _pick_pixabay_file(h.get("videos"))
        if not f:
            continue
        tags = [t.strip() for t in str(h.get("tags", "")).split(",") if t.strip()]
        out.append({
            "source": "pixabay",
            "source_id": str(h.get("id", "")),
            "page_url": h.get("pageURL", ""),
            "duration": h.get("duration") or 0,
            "width": f.get("width") or 0,
            "height": f.get("height") or 0,
            "tags": tags,
            "photographer": h.get("user", ""),
            "file_url": f["url"],
        })
    if not out:
        return [], "Pixabay returned no usable videos for this query"
    return out, "pixabay"


def search_videos(query: str, per_page: int = 20,
                  cfg=None) -> tuple[list, str]:
    """Try Pexels first, fall back to Pixabay.

    Returns (videos, reason): reason is 'pexels' / 'pixabay' on success,
    otherwise a human-readable explanation of why nothing came back.
    """
    if cfg is None:
        from .config import Config
        cfg = Config()
    videos, reason = pexels_search(cfg.get("pexels_api_key", ""), query, per_page)
    if videos:
        return videos, reason
    pix_videos, pix_reason = pixabay_search(cfg.get("pixabay_api_key", ""), query, per_page)
    if pix_videos:
        return pix_videos, pix_reason
    return [], reason or pix_reason or "no stock-video API keys configured"
