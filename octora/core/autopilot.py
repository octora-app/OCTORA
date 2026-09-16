"""Autopilot: per-niche video sourcing straight into the download queue.

Two source types per niche:
  stock — Pexels API first, Pixabay fallback (legal, reliable; free keys).
  links — newline-separated Instagram/TikTok/Facebook/YouTube URLs
           (video, profile/page, or hashtag URLs) enumerated with yt-dlp
           flat-playlist discovery. Only add content you have the right
           to repost.

For every enabled niche the scheduler spreads `videos_per_day` evenly across
24h (interval = 86400 / videos_per_day). When a niche is "due" (its last_run
is older than one interval), the next fresh video is queued for download
with provenance encoded in the downloads note:
    autopilot:<niche_id>:<source>:<source_id>

Dedupe happens twice: here by source_id (nothing queued twice), and again in
DownloadWorker after the bytes land (sha256 of the actual file).

Demo mode (or no API keys): synthetic demo entries keep the pipeline visibly
alive — no real network calls, mirroring the rest of the engine.

NO artificial caps: every enabled niche is processed each cycle; the only
throttle is the user's own videos_per_day plus platform API realities.
"""
import time
from datetime import datetime, timezone

from .engine import _Worker
from .logger import get_logger
from . import sources

log = get_logger("octora.autopilot")


def _parse_utc(ts: str):
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _demo_results(niche: dict, n: int = 3) -> list:
    """Synthetic stock entries for demo mode — unique per call."""
    ts = int(time.time() * 1000)
    nid = niche["id"]
    out = []
    for i in range(n):
        sid = f"auto_{nid}_{ts}_{i}"
        out.append({
            "source": "demo",
            "source_id": sid,
            "page_url": "",
            "duration": 12 + i,
            "width": 720,
            "height": 1280,
            "tags": (niche.get("keywords") or "").split(",")[:3],
            "photographer": "OCTORA demo",
            "file_url": f"https://demo.octora.local/{sid}.mp4",
        })
    return out


class NicheScheduler(_Worker):
    """Sources one fresh video per due niche per interval into downloads."""

    def run(self):
        self.tick.emit({"key": "autopilot", "label": "Starting", "progress": 0,
                        "detail": "Checking niches…", "retries": 0})
        while not self._stop:
            try:
                if self.engine.cfg.get("autopilot_enabled", True):
                    self._cycle()
                else:
                    self.tick.emit({"key": "autopilot", "label": "Off", "progress": 0,
                                    "detail": "Disabled in Settings", "retries": 0})
                self.nap(60)
            except Exception as e:  # noqa: BLE001
                log.error("autopilot cycle error: %s", e)
                self.tick.emit({"key": "autopilot", "label": "Error", "progress": 0,
                                "detail": str(e)[:70], "retries": 0})
                self.nap(30)

    def _cycle(self):
        db, cfg = self.engine.db, self.engine.cfg
        niches = db.list_niches(enabled_only=True)
        if not niches:
            self.tick.emit({"key": "autopilot", "label": "Idle", "progress": 0,
                            "detail": "No niches — add one on the Niches screen",
                            "retries": 0})
            return
        now = datetime.now(timezone.utc)
        due_count = 0
        for niche in niches:
            if self._stop:
                return
            vpd = max(1, int(niche.get("videos_per_day") or 1))
            interval = 86400.0 / vpd
            last = _parse_utc(niche.get("last_run") or "")
            if last is not None and (now - last).total_seconds() < interval:
                continue
            due_count += 1
            self._source_for_niche(db, cfg, niche, now)
        self.tick.emit({"key": "autopilot", "label": "Watching", "progress": 100,
                        "detail": f"{len(niches)} niche(s) • {due_count} due this cycle",
                        "retries": 0})
        self.engine.stats_changed.emit()

    def _source_for_niche(self, db, cfg, niche, now):
        nid = niche["id"]
        stype = (niche.get("source_type") or "stock").lower()
        self.tick.emit({"key": "autopilot", "label": "Sourcing", "progress": 30,
                        "detail": f"{niche['name']}: "
                                  f"{'social links' if stype == 'links' else 'stock'}…",
                        "retries": 0})
        if stype == "links":
            cands = self._link_candidates(cfg, niche)
        else:
            cands = self._stock_candidates(cfg, niche)
        queued = False
        for key, url, origin in cands:
            if self._stop:
                return
            note = f"autopilot:{nid}:{key}"
            if db.niche_dedup_hit(key, ""):
                continue
            pend = db.query_one(
                "SELECT id FROM downloads WHERE note=? AND status IN ('queued','downloading')",
                (note,))
            if pend:
                continue
            self.engine.enqueue_download(url, note=note)
            log.info("autopilot: queued %s (%s) for niche '%s'",
                     key, origin, niche["name"])
            self.tick.emit({"key": "autopilot", "label": "Queued", "progress": 80,
                            "detail": f"{niche['name']}: {key} via {origin}",
                            "retries": 0})
            queued = True
            break  # exactly one video per due interval
        if not queued:
            log.info("autopilot: no fresh video for niche '%s'", niche["name"])
        db.execute("UPDATE niches SET last_run=? WHERE id=?",
                   (now.isoformat(), nid))

    def _stock_candidates(self, cfg, niche):
        """(key, url, origin) list from Pexels/Pixabay (or demo entries)."""
        keywords = (niche.get("keywords") or "").strip() or niche["name"]
        if cfg.demo_mode or not (cfg.get("pexels_api_key") or cfg.get("pixabay_api_key")):
            videos, origin = _demo_results(niche), "demo"
        else:
            per_page = max(20, int(niche.get("videos_per_day") or 5) * 2)
            videos, origin = sources.search_videos(keywords, per_page=per_page, cfg=cfg)
        return [(f"{v['source']}:{v['source_id']}", v["file_url"], origin)
                for v in videos]

    def _link_candidates(self, cfg, niche):
        """(key, url, origin) list from the niche's social links via yt-dlp
        flat discovery (no media downloaded at this stage)."""
        if cfg.demo_mode:
            return [(f"demo:{v['source_id']}", v["file_url"], "demo")
                    for v in _demo_results(niche)]
        links = [ln.strip() for ln in (niche.get("source_links") or "").splitlines()
                 if ln.strip()]
        if not links:
            log.warning("autopilot: links niche '%s' has no source links — "
                        "add some on the Niches screen", niche["name"])
            return []
        from . import linkdiscovery
        cands = []
        for link in links:
            if self._stop:
                break
            for v in linkdiscovery.discover_new_videos(link):
                cands.append((f"{v['source']}:{v['source_id']}",
                              v["page_url"], v["source"]))
        return cands
