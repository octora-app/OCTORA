"""YouTube Shorts plugin — REAL resumable upload via urllib (live mode).

Protocol: POST upload session -> PUT bytes -> video id. Uses the Google OAuth
access token (same "Connect Google" as Drive). Shorts = vertical video < 3 min
with #Shorts in title/description.
"""
import json
import os
import urllib.error
import urllib.request

from .base import PlatformPlugin
from ..core import oauth

SESSION_URL = ("https://www.googleapis.com/upload/youtube/v3/videos"
               "?uploadType=resumable&part=snippet,status")


class YouTubePlugin(PlatformPlugin):
    id = "youtube"
    name = "YouTube Shorts"
    icon = "▶"
    color = "#ff0033"
    description = "Uploads vertical videos as Shorts via the YouTube Data API v3."

    def credential_fields(self):
        return []  # v1.1: customers use the "Connect to YouTube" button (seller OAuth)

    def setup_help(self):
        return ("No API keys needed. Click 'Connect to YouTube' on the Platforms "
                "screen and sign in with the Google account that owns your channel.")

    def is_configured(self, cfg):
        from ..core import oauth
        return bool(cfg.get("google_refresh_token")) and oauth.google_ready_for(cfg)

    def publish(self, asset_path, meta, cfg, demo):
        if demo:
            return self._demo_publish(asset_path, meta)
        if not asset_path or not os.path.exists(asset_path):
            return False, "LIVE YouTube: local file missing."
        token = oauth.google_access_token(cfg)
        if not token:
            return False, "LIVE YouTube: Google not connected — click 'Connect Google'."
        title = (meta.get("title") if isinstance(meta, dict) else None) \
            or (self._meta_caption(meta, os.path.basename(asset_path)))
        title = (title[:95] + " #Shorts") if "#Shorts" not in title else title[:100]
        description = (meta.get("description") if isinstance(meta, dict) else "") or title
        tags = [t for t in (meta.get("tags") if isinstance(meta, dict) else []) or []][:15]
        meta = {"snippet": {"title": title, "description": description[:5000],
                            "tags": tags, "categoryId": "22"},
                "status": {"privacyStatus": "public", "madeForKids": False,
                           "selfDeclaredMadeForKids": False}}
        try:
            session = self._init_session(token, meta, asset_path)
            vid = self._put_bytes(token, session, asset_path)
            return True, f"LIVE YouTube: uploaded, video id {vid}"
        except RuntimeError as e:
            # Expired cached access token (Google tokens live ~1h): clear it,
            # get a fresh one via the refresh token, and retry once — same
            # pattern as gdrive._refresh(). Without this, every upload after
            # the first hour fails with HTTP 401.
            if "HTTP 401" in str(e) or "HTTP 403" in str(e):
                cfg.set("google_access_token", "")
                token = oauth.google_access_token(cfg)
                if token:
                    try:
                        session = self._init_session(token, meta, asset_path)
                        vid = self._put_bytes(token, session, asset_path)
                        return True, f"LIVE YouTube: uploaded, video id {vid}"
                    except Exception as e2:  # noqa: BLE001
                        return False, f"LIVE YouTube upload failed: {e2}"
            return False, f"LIVE YouTube upload failed: {e}"
        except Exception as e:  # noqa: BLE001
            return False, f"LIVE YouTube upload failed: {e}"

    def _init_session(self, token, meta, path):
        import mimetypes
        mime, _ = mimetypes.guess_type(path)
        size = os.path.getsize(path)
        req = urllib.request.Request(
            SESSION_URL, data=json.dumps(meta).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Type": mime or "video/mp4",
                     "X-Upload-Content-Length": str(size)})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                loc = resp.headers.get("Location")
                if not loc:
                    raise RuntimeError("YouTube did not return an upload session")
                return loc
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"YouTube session init HTTP {e.code}: {e.read()[:200]}")

    def _put_bytes(self, token, session_url, path):
        with open(path, "rb") as f:
            data = f.read()
        req = urllib.request.Request(
            session_url, data=data, method="PUT",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "video/mp4",
                     "Content-Length": str(len(data))})
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                body = json.loads(resp.read().decode() or "{}")
                vid = body.get("id")
                if not vid:
                    raise RuntimeError("YouTube upload finished without a video id")
                return vid
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"YouTube upload HTTP {e.code}")
