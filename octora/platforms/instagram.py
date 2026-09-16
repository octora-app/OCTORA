"""Instagram Reels plugin — REAL publish via the Instagram Graph API.

Two-step flow:
  1. POST /{ig-user-id}/media
     (media_type=REELS, video_url=<PUBLIC url>, caption=<caption>)
     -> container id
  2. Poll GET /{container-id}?fields=status_code until FINISHED
  3. POST /{ig-user-id}/media_publish (creation_id=<container id>) -> media id

The hard requirement is Meta's, not ours: `video_url` must be PUBLICLY
reachable — Meta's own servers download the file. OCTORA keeps files on the
customer's PC, so the customer supplies the public link: per job via
meta["video_url"], or once in config as `instagram_public_video_url`
(any direct https .mp4 link — their own site, a CDN, or any public file host).

If no public URL is available the publish FAILS with clear guidance —
a post is never faked.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .base import PlatformPlugin

GRAPH = "https://graph.facebook.com/v19.0"
POLL_INTERVAL = 10   # seconds between container status checks
POLL_TRIES = 60      # -> up to ~10 minutes of processing wait


class InstagramPlugin(PlatformPlugin):
    id = "instagram"
    name = "Instagram Reels"
    icon = "\U0001F4F8"
    color = "#e1306c"
    description = "Publishes reels via the Instagram Graph API (needs a public video URL)."

    def credential_fields(self):
        return []  # customers use the "Connect Instagram" button (seller OAuth)

    def setup_help(self):
        return ("No API keys needed. Click 'Connect Instagram' on the Platforms "
                "screen and sign in with Facebook (needs an Instagram Business/Creator "
                "account linked to your Page).\n"
                "PUBLIC VIDEO URL (Meta ki requirement): Meta ke servers ko video file "
                "khud download karni hoti hai, isliye reel ki ek public direct link chahiye "
                "(https .mp4 — apni website, CDN, ya koi public file host). Wahi link har "
                "job me 'video_url' ke roop me do, ya Settings me ek baar "
                "'instagram_public_video_url' set kar do. Bina public link ke post fail "
                "hoga — fake success kabhi nahi dikhega.")

    def is_configured(self, cfg):
        from ..core import seller_config
        return bool(cfg.get("meta_access_token")) and seller_config.meta_ready()

    # -- HTTP ----------------------------------------------------------
    @staticmethod
    def _post_form(url, params):
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")

    @staticmethod
    def _get_json(url):
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")

    @staticmethod
    def _meta_err(e: urllib.error.HTTPError) -> str:
        try:
            body = e.read().decode() or "{}"
            msg = json.loads(body).get("error", {}).get("message", "")
            return msg or body[:200]
        except Exception:  # noqa: BLE001
            return f"HTTP {e.code}"

    def _wait_finished(self, token, container_id):
        """Polls the container until Meta finishes processing it."""
        url = (f"{GRAPH}/{container_id}?fields=status_code,status"
               f"&access_token={urllib.parse.quote(token)}")
        for _ in range(POLL_TRIES):
            st = self._get_json(url)
            code = st.get("status_code")
            if code == "FINISHED":
                return True, ""
            if code == "ERROR":
                return False, f"Meta could not process the video: {st}"
            if code == "EXPIRED":
                return False, "container expired before publishing — retry the job"
            time.sleep(POLL_INTERVAL)
        return False, "timed out waiting for Meta to process the video"

    # -- publish --------------------------------------------------------
    def publish(self, asset_path, meta, cfg, demo):
        if demo:
            return self._demo_publish(asset_path, meta)
        from ..core import oauth
        token = oauth.meta_ensure_token(cfg)
        if not token:
            return False, "LIVE Instagram: not connected — click 'Connect Instagram'."
        ig_id = cfg.get("instagram_business_id", "")
        if not ig_id:
            return False, ("LIVE Instagram: no Business/Creator account linked to your "
                           "Facebook Pages — link one in the Instagram app, then reconnect.")
        video_url = ""
        if isinstance(meta, dict):
            video_url = (meta.get("video_url") or "").strip()
        if not video_url:
            video_url = (cfg.get("instagram_public_video_url") or "").strip()
        if not video_url:
            return False, (
                "LIVE Instagram: Meta requires a PUBLIC video_url for reels and none "
                "was provided. Reel ki file ko kisi public host par rakho (apni website / "
                "CDN / public file host — direct https .mp4 link), phir wahi link job ke "
                "'video_url' me do ya Settings me 'instagram_public_video_url' set karo. "
                "Bina public link ke post nahi hoga — not faked.")
        if not video_url.lower().startswith("https://"):
            return False, ("LIVE Instagram: video_url must be a public https:// link "
                           f"(got: {video_url[:60]}).")
        caption = self._meta_caption(meta)
        try:
            container = self._post_form(
                f"{GRAPH}/{ig_id}/media",
                {"media_type": "REELS", "video_url": video_url,
                 "caption": caption, "access_token": token})
            container_id = container.get("id")
            if not container_id:
                return False, f"LIVE Instagram: container create failed — {container}"
            ok, why = self._wait_finished(token, container_id)
            if not ok:
                return False, f"LIVE Instagram: {why}"
            pub = self._post_form(
                f"{GRAPH}/{ig_id}/media_publish",
                {"creation_id": container_id, "access_token": token})
            media_id = pub.get("id")
            if not media_id:
                return False, f"LIVE Instagram: media_publish failed — {pub}"
            return True, f"LIVE Instagram: reel published (media id {media_id})"
        except urllib.error.HTTPError as e:
            return False, f"LIVE Instagram: {self._meta_err(e)}"
        except Exception as e:  # noqa: BLE001
            return False, f"LIVE Instagram publish failed: {e}"
