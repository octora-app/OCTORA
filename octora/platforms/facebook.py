"""Facebook Reels plugin — REAL publish via the Graph API.

Protocol (Page reels, resumable upload):
  1. POST /{page-id}/video_reels?upload_phase=start  -> video_id + upload_url
  2. POST {upload_url} with the raw file bytes,
     header: Authorization: OAuth {page-access-token}
  3. POST /{page-id}/video_reels?upload_phase=finish&video_id=...
     &video_state=PUBLISHED&description=...  -> {"success": true}

Uses the Page access token from the existing "Connect Facebook" flow
(oauth.meta_page_token) — no new credentials needed.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .base import PlatformPlugin

GRAPH = "https://graph.facebook.com/v19.0"
MAX_BYTES = 500 * 1024 * 1024  # sanity cap; Meta allows far more, reels are small


class FacebookPlugin(PlatformPlugin):
    id = "facebook"
    name = "Facebook Reels"
    icon = "\U0001F4D8"
    color = "#1877f2"
    description = "Publishes reels to a Facebook Page via the Graph API."

    def credential_fields(self):
        return []  # customers use the "Connect Facebook" button (seller OAuth)

    def setup_help(self):
        return ("No API keys needed. Click 'Connect Facebook' on the Platforms "
                "screen and sign in, then pick the Page to post reels to.")

    def is_configured(self, cfg):
        from ..core import oauth, seller_config
        return oauth.meta_page_token(cfg) is not None and seller_config.meta_ready()

    # -- HTTP ----------------------------------------------------------
    @staticmethod
    def _post_form(url, params):
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")

    @staticmethod
    def _meta_err(e: urllib.error.HTTPError) -> str:
        try:
            body = e.read().decode() or "{}"
            msg = json.loads(body).get("error", {}).get("message", "")
            return msg or body[:200]
        except Exception:  # noqa: BLE001
            return f"HTTP {e.code}"

    def _upload_bytes(self, upload_url, page_token, path):
        size = os.path.getsize(path)
        if size > MAX_BYTES:
            raise ValueError(f"file too large ({size // 1048576} MB > 500 MB)")
        with open(path, "rb") as f:
            data = f.read()
        req = urllib.request.Request(upload_url, data=data, method="POST")
        req.add_header("Authorization", f"OAuth {page_token}")
        req.add_header("Content-Type", "application/octet-stream")
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = json.loads(r.read().decode() or "{}")
        if not resp.get("success"):
            raise RuntimeError(f"byte upload not acknowledged: {resp}")

    # -- publish --------------------------------------------------------
    def publish(self, asset_path, meta, cfg, demo):
        if demo:
            return self._demo_publish(asset_path, meta)
        if not asset_path or not os.path.exists(asset_path):
            return False, "LIVE Facebook: local file missing."
        from ..core import oauth
        oauth.meta_ensure_token(cfg)  # keep the 60-day user token fresh
        page = oauth.meta_page_token(cfg)
        if not page:
            return False, ("LIVE Facebook: not connected — click 'Connect Facebook' "
                           "and pick a Page.")
        page_token, page_id = page
        caption = self._meta_caption(meta)
        try:
            start = self._post_form(
                f"{GRAPH}/{page_id}/video_reels",
                {"upload_phase": "start", "access_token": page_token})
            video_id = start.get("video_id")
            upload_url = start.get("upload_url")
            if not video_id or not upload_url:
                return False, f"LIVE Facebook: upload session failed — {start}"
            self._upload_bytes(upload_url, page_token, asset_path)
            fin = self._post_form(
                f"{GRAPH}/{page_id}/video_reels",
                {"upload_phase": "finish", "video_id": video_id,
                 "video_state": "PUBLISHED", "description": caption,
                 "access_token": page_token})
            if fin.get("success"):
                return True, f"LIVE Facebook: reel published (video id {video_id})"
            return False, f"LIVE Facebook: publish step failed — {fin}"
        except urllib.error.HTTPError as e:
            return False, f"LIVE Facebook: {self._meta_err(e)}"
        except Exception as e:  # noqa: BLE001
            return False, f"LIVE Facebook upload failed: {e}"
