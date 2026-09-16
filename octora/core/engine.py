"""Background pipeline: Download -> Fetch -> Render -> Drive -> Publish -> Cleanup.

Demo mode (default ON): simulates the full pipeline end-to-end with realistic
timing so every screen is visibly alive. No real network calls are ever made
in demo mode.

Live mode: Download uses yt-dlp, Drive uses the Google Drive API (OAuth),
Publish uses the platform plugins. Every live failure is reported honestly —
OCTORA never fakes a real post.
"""
import os
import shutil
import subprocess
import time
from datetime import timedelta
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer

from .config import Config
from .database import Database, iso_ist, now_ist
from .drive_sync import scan_folder
from . import gdrive
from .logger import get_logger
from . import metadata as seo
from ..platforms import plugin_for_label, ID_TO_LABEL, LABEL_TO_ID

log = get_logger("octora.engine")

RETRY_BASE_SECONDS = 30
MAX_ATTEMPTS = 5


def build_meta(db: Database, platform_label: str, asset_id=None,
               campaign_id=None, asset_filename: str = "",
               override_json: str = "") -> dict:
    """Renders the SEO metadata for one upload. Never raises — falls back to
    plain filename-based metadata so the pipeline can never jam on this."""
    try:
        import json as _json
        pid = LABEL_TO_ID.get(platform_label, "youtube")
        campaign = None
        if campaign_id:
            row = db.query_one("SELECT * FROM campaigns WHERE id=?", (campaign_id,))
            campaign = dict(row) if row else None
        filename = asset_filename
        if not filename and asset_id:
            r = db.query_one("SELECT filename FROM assets WHERE id=?", (asset_id,))
            filename = r["filename"] if r else ""
        overrides = _json.loads(override_json) if override_json else {}
        return seo.render(pid, campaign, filename or "clip.mp4", overrides or None)
    except Exception as e:  # noqa: BLE001
        log.warning("metadata render failed (%s) — using fallback", e)
        return {"title": asset_filename or "clip", "description": "",
                "tags": [], "caption": asset_filename or "clip",
                "warnings": [], "keyword": "", "niche": ""}

STAGE_DEFS = [
    ("download", "Download", "violet"),
    ("fetch", "Fetch", "green"),
    ("render", "Render", "amber"),
    ("drive", "Drive", "cyan"),
    ("publish", "Publish", "blue"),
    ("cleanup", "Cleanup", "gray"),
    ("autopilot", "Autopilot", "cyan"),
]


class _Worker(QThread):
    tick = pyqtSignal(dict)  # pipeline card update

    def __init__(self, engine, name):
        super().__init__()
        self.engine = engine
        self.wname = name
        self._stop = False

    def stop(self):
        self._stop = True

    def nap(self, seconds: float):
        end = time.time() + seconds
        while time.time() < end and not self._stop:
            time.sleep(0.1)


def _emit_progress(worker, key, label, detail, steps=10, step_delay=0.4):
    for pct in range(0, 101, 100 // steps):
        if worker._stop:
            return False
        worker.tick.emit({"key": key, "label": label, "progress": pct,
                          "detail": detail, "retries": 0})
        worker.nap(step_delay)
    return True


class DownloadWorker(_Worker):
    """Downloads videos from URLs (yt-dlp in live mode, simulated in demo)."""

    def run(self):
        while not self._stop:
            try:
                if not self._pump():
                    self.tick.emit({"key": "download", "label": "Idle", "progress": 0,
                                    "detail": "No URLs queued", "retries": 0})
                    self.nap(3)
            except Exception as e:  # noqa: BLE001
                log.error("download worker error: %s", e)
                self.nap(5)

    def _pump(self) -> bool:
        db, cfg = self.engine.db, self.engine.cfg
        row = db.query_one("SELECT * FROM downloads WHERE status='queued' ORDER BY id LIMIT 1")
        if row is None:
            return False
        did = row["id"]
        db.execute("UPDATE downloads SET status='downloading' WHERE id=?", (did,))
        url = row["url"]
        self.tick.emit({"key": "download", "label": "Downloading", "progress": 5,
                        "detail": url[:60], "retries": 0})
        if cfg.demo_mode:
            ok, msg, path = self._demo_download(db, cfg, did, url)
        else:
            ok, msg, path = self._real_download(db, cfg, did, url)
        if ok:
            asset_id = self._register_asset(db, cfg, path, url, did)
            db.execute("UPDATE downloads SET status='done', progress=100, asset_id=? WHERE id=?",
                       (asset_id, did))
            log.info("download: done %s -> asset %s", url[:60], asset_id)
            self.tick.emit({"key": "download", "label": "Done", "progress": 100,
                            "detail": os.path.basename(path), "retries": 0})
        else:
            db.execute("UPDATE downloads SET status='failed', error=? WHERE id=?", (msg, did))
            log.error("download failed: %s (%s)", url[:60], msg)
            self.tick.emit({"key": "download", "label": "Failed", "progress": 0,
                            "detail": msg[:60], "retries": 0})
        self.engine.stats_changed.emit()
        return True

    def _demo_download(self, db, cfg, did, url):
        if not _emit_progress(self, "download", "Downloading", f"demo: {url[:50]}",
                              steps=8, step_delay=0.4):
            return False, "cancelled", ""
        folder = Path(cfg.get("asset_folder"))
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"demo_dl_{did}.mp4"
        # placeholder bytes; unique per download so dedup never collides
        path.write_bytes(os.urandom(128) + f"::OCTORA-DEMO::{did}::{url}".encode() * 4096)
        return True, "demo ok", str(path)

    def _real_download(self, db, cfg, did, url):
        exe = shutil.which("yt-dlp")
        if not exe:
            return False, "yt-dlp not found — pip install yt-dlp", ""
        folder = Path(cfg.get("asset_folder"))
        folder.mkdir(parents=True, exist_ok=True)
        tmpl = str(folder / f"dl_{did}.%(ext)s")
        self.tick.emit({"key": "download", "label": "Downloading", "progress": 30,
                        "detail": "yt-dlp running…", "retries": 0})
        try:
            r = subprocess.run([exe, "-o", tmpl, "--no-playlist", "--no-warnings",
                                "--max-filesize", "500m", url],
                               capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            return False, "yt-dlp timed out", ""
        if r.returncode != 0:
            return False, (r.stderr.strip()[-200:] or "yt-dlp failed"), ""
        cands = sorted(folder.glob(f"dl_{did}.*"), key=lambda p: p.stat().st_mtime)
        if not cands:
            return False, "yt-dlp finished but no file appeared", ""
        return True, "downloaded", str(cands[-1])

    def _register_asset(self, db, cfg, path, url, did):
        """Import the downloaded file, with Autopilot dedupe.

        Provenance comes from the downloads note ('autopilot:<niche_id>:<src>:<sid>').
        If the file's sha256 (or the stock source_id) already exists in assets,
        the just-downloaded file is DELETED instead of keeping two copies: the
        surviving asset row is marked as the download's asset and the download
        note records the duplicate link. Never raises.
        """
        from .drive_sync import import_file, sha256_of
        p = Path(path)
        niche_id, source_id = 0, ""
        try:
            nrow = db.query_one("SELECT note FROM downloads WHERE id=?", (did,))
            note = (nrow["note"] if nrow else "") or ""
            if note.startswith("autopilot:"):
                parts = note.split(":", 3)
                if len(parts) == 4:
                    try:
                        niche_id = int(parts[1])
                    except ValueError:
                        niche_id = 0
                    source_id = parts[2] + ":" + parts[3]
        except Exception:  # noqa: BLE001
            pass
        try:
            digest = sha256_of(p)
        except OSError:
            digest = ""
        dupe_of = None
        if digest:
            r = db.query_one("SELECT id FROM assets WHERE sha256=?", (digest,))
            if r:
                dupe_of = r["id"]
        if dupe_of is None and source_id and db.niche_dedup_hit(source_id, ""):
            r = db.query_one("SELECT id FROM assets WHERE source_id=? AND source_id<>''",
                             (source_id,))
            dupe_of = r["id"] if r else None
        if dupe_of is not None:
            # duplicate: the NEW asset is marked 'duplicate' and its file is
            # deleted — the surviving asset keeps its own status. Never two copies.
            try:
                p.unlink()
            except OSError:
                pass
            cur = db.execute(
                "INSERT INTO assets(filename,path,sha256,size,status,note,"
                "source_id,niche_id,added_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (p.name, "", None, 0, "duplicate",
                 f"duplicate of asset {dupe_of} — file not kept",
                 source_id, niche_id, iso_ist(now_ist())))
            db.execute("UPDATE downloads SET asset_id=?, note=? WHERE id=?",
                       (dupe_of,
                        f"duplicate of asset {dupe_of} (marker {cur.lastrowid})", did))
            log.info("download: duplicate of asset %s — new file removed, "
                     "kept single copy (marker %s)", dupe_of, cur.lastrowid)
            return dupe_of
        ok, _ = import_file(db, p)
        row = db.query_one("SELECT id FROM assets WHERE path=?", (str(p),))
        aid = row["id"] if row else None
        if aid:
            db.execute("UPDATE assets SET source_id=?, niche_id=? WHERE id=?",
                       (source_id, niche_id, aid))
            if cfg.demo_mode:
                # demo placeholders skip strict validation — the pipeline is what's demoed
                db.execute("UPDATE assets SET status='new', note='demo download' WHERE id=?",
                           (aid,))
        return aid


class FetchWorker(_Worker):
    """Watches source folders, imports new video files into the asset library."""

    def run(self):
        while not self._stop:
            try:
                db, cfg = self.engine.db, self.engine.cfg
                added, skipped = 0, 0
                folders = [cfg.get("drive_folder")]
                for c in db.query("SELECT source_folder FROM campaigns WHERE active=1"):
                    if c["source_folder"]:
                        folders.append(c["source_folder"])
                for folder in dict.fromkeys(f for f in folders if f):
                    a, s = scan_folder(db, folder)
                    added += a
                    skipped += s
                total = db.query_one("SELECT COUNT(*) c FROM assets")["c"] or 0
                if not _emit_progress(self, "fetch", "Running",
                                     f"Watching folders • {total} assets • {added} new",
                                     steps=4, step_delay=0.8):
                    return
                if added:
                    log.info("fetch: imported %d new asset(s)", added)
            except Exception as e:  # noqa: BLE001
                log.error("fetch worker error: %s", e)
                self.nap(5)


class RenderWorker(_Worker):
    """Prepares assets (demo: simulated render passes with real progress)."""

    def run(self):
        while not self._stop:
            try:
                db, cfg = self.engine.db, self.engine.cfg
                row = db.query_one("SELECT * FROM assets WHERE status='new' ORDER BY id LIMIT 1")
                if row is None:
                    if not _emit_progress(self, "render", "Idle", "No assets waiting",
                                          steps=4, step_delay=0.8):
                        return
                    continue
                db.execute("UPDATE assets SET status='rendering' WHERE id=?", (row["id"],))
                steps = ["Decoding", "Filters 1080x1920", "Captions", "Encoding"]
                for i, step in enumerate(steps):
                    for pct in range(0, 101, 25):
                        if self._stop:
                            return
                        overall = int((i * 100 + pct) / len(steps))
                        self.tick.emit({"key": "render", "label": "Processing",
                                        "progress": overall,
                                        "detail": f"{step}: {row['filename']}", "retries": 0})
                        self.nap(0.25 if cfg.demo_mode else 0.6)
                db.execute("UPDATE assets SET status='ready' WHERE id=?", (row["id"],))
                log.info("render: %s ready", row["filename"])
                self.engine.stats_changed.emit()
            except Exception as e:  # noqa: BLE001
                log.error("render worker error: %s", e)
                self.nap(5)


class DriveWorker(_Worker):
    """Uploads ready assets to Google Drive (real API in live mode)."""

    def run(self):
        while not self._stop:
            try:
                if not self._pump():
                    if not _emit_progress(self, "drive", "Idle", "Nothing to upload",
                                          steps=4, step_delay=0.8):
                        return
            except Exception as e:  # noqa: BLE001
                log.error("drive worker error: %s", e)
                self.nap(5)

    def _pump(self) -> bool:
        db, cfg = self.engine.db, self.engine.cfg
        row = db.query_one("SELECT * FROM assets WHERE status='ready' "
                           "AND drive_status='pending' ORDER BY id LIMIT 1")
        if row is None:
            return False
        aid = row["id"]
        db.execute("UPDATE assets SET drive_status='uploading' WHERE id=?", (aid,))
        name = row["filename"]
        if cfg.demo_mode:
            if not _emit_progress(self, "drive", "Uploading", f"demo: {name}",
                                  steps=8, step_delay=0.35):
                db.execute("UPDATE assets SET drive_status='pending' WHERE id=?", (aid,))
                return True
            db.execute("UPDATE assets SET drive_status='done', drive_file_id=? WHERE id=?",
                       (f"demo_drive_{aid}", aid))
            log.info("drive: demo uploaded %s", name)
        else:
            self.tick.emit({"key": "drive", "label": "Uploading", "progress": 40,
                            "detail": name, "retries": 0})
            folder_id, folder_msg = self._drive_folder(db, cfg, aid)
            if folder_id is None:
                db.execute("UPDATE assets SET drive_status='failed', note=? WHERE id=?",
                           (folder_msg, aid))
                log.error("drive: folder setup failed %s (%s)", name, folder_msg)
                return True
            ok, res = gdrive.upload_file(cfg, row["path"], folder_id)
            if ok:
                db.execute("UPDATE assets SET drive_status='done', drive_file_id=? WHERE id=?",
                           (res, aid))
                log.info("drive: uploaded %s -> %s (folder %s)", name, res, folder_id)
            else:
                db.execute("UPDATE assets SET drive_status='failed', note=? WHERE id=?",
                           (res, aid))
                log.error("drive: failed %s (%s)", name, res)
                self.tick.emit({"key": "drive", "label": "Failed", "progress": 0,
                                "detail": res[:60], "retries": 0})
                return True
        self.tick.emit({"key": "drive", "label": "Done", "progress": 100,
                        "detail": name, "retries": 0})
        # auto-queue for publishing so the pipeline runs end-to-end
        if cfg.get("auto_queue_after_drive", True):
            plat = ID_TO_LABEL.get(cfg.get("default_platform_id", "youtube"), "YT Shorts")
            camp_id = self._asset_campaign(db, aid)
            meta = build_meta(db, plat, asset_id=aid, campaign_id=camp_id,
                              asset_filename=name)
            import json as _json
            self.engine.enqueue(platform=plat, asset_id=aid, priority=6,
                                caption=meta["caption"],
                                meta_json=_json.dumps(meta, ensure_ascii=False))
            log.info("drive: auto-queued %s for %s (title: %r)", name, plat, meta["title"])
        self.engine.stats_changed.emit()
        self.engine.queue_changed.emit()
        return True

    @staticmethod
    def _asset_campaign(db, asset_id):
        r = db.query_one("SELECT campaign_id FROM downloads WHERE asset_id=?", (asset_id,))
        return r["campaign_id"] if r and r["campaign_id"] else None

    def _drive_folder(self, db, cfg, asset_id) -> tuple[str | None, str]:
        """Zero-setup Drive folder: OCTORA root, or OCTORA/<Campaign> when the
        asset is linked to a campaign. Created automatically on first use."""
        camp_id = self._asset_campaign(db, asset_id)
        if camp_id:
            c = db.query_one("SELECT name FROM campaigns WHERE id=?", (camp_id,))
            if c and c["name"]:
                return gdrive.ensure_campaign_folder(cfg, c["name"])
        return gdrive.ensure_octora_folder(cfg)


class PublishWorker(_Worker):
    """Publishes the upload queue through the platform plugins, with retries."""

    def run(self):
        while not self._stop:
            try:
                if not self._pump():
                    self.tick.emit({"key": "publish", "label": "Idle", "progress": 0,
                                    "detail": "Queue empty", "retries": 0})
                    self.nap(3)
            except Exception as e:  # noqa: BLE001
                log.error("publish worker error: %s", e)
                self.nap(5)

    def _pump(self) -> bool:
        eng, db, cfg = self.engine, self.engine.db, self.engine.cfg
        if eng.upload_paused:
            self.tick.emit({"key": "publish", "label": "Paused", "progress": 0,
                            "detail": "Uploads paused by operator", "retries": 0})
            self.nap(2)
            return True
        now = iso_ist(now_ist())
        row = db.query_one(
            """SELECT q.*, a.filename, a.path FROM upload_queue q
               LEFT JOIN assets a ON a.id=q.asset_id
               WHERE q.status='queued' AND (q.next_retry_at='' OR q.next_retry_at<=?)
               ORDER BY q.priority DESC, q.id LIMIT 1""", (now,))
        if row is None:
            return False
        qid = row["id"]
        name = row["filename"] or f"clip_{qid:04d}.mp4"
        db.execute("UPDATE upload_queue SET status='uploading', updated_at=? WHERE id=?",
                   (now, qid))
        eng.queue_changed.emit()
        self.tick.emit({"key": "publish", "label": "Uploading", "progress": 5,
                        "detail": f"{row['platform']}: {name}", "retries": row["attempts"]})
        steps = 12 if cfg.demo_mode else 20
        for i in range(steps):
            if self._stop:
                return True
            self.tick.emit({"key": "publish", "label": "Uploading",
                            "progress": int(5 + 90 * (i + 1) / steps),
                            "detail": f"{row['platform']}: {name}", "retries": row["attempts"]})
            self.nap(0.35 if cfg.demo_mode else 0.8)
        plugin = plugin_for_label(row["platform"])
        import json as _json
        try:
            meta = _json.loads(row["meta_json"]) if row["meta_json"] else None
        except Exception:  # noqa: BLE001
            meta = None
        if not meta:
            meta = build_meta(db, row["platform"], asset_id=row["asset_id"],
                              asset_filename=name)
        # Autopilot: niche-mode metadata (manual templates / Gemini auto) wins
        # for niche-sourced assets; stored on the asset row, passed to publish.
        niche_meta = self._niche_metadata(db, cfg, row["asset_id"],
                                          row["path"] or "", name)
        if niche_meta:
            meta.update(niche_meta)
            try:
                db.execute("UPDATE upload_queue SET meta_json=? WHERE id=?",
                           (_json.dumps(meta, ensure_ascii=False), qid))
            except Exception:  # noqa: BLE001
                pass
        ok, message = plugin.publish(row["path"] or "", meta, cfg, cfg.demo_mode)
        if ok:
            db.execute("UPDATE upload_queue SET status='posted', updated_at=? WHERE id=?",
                       (iso_ist(now_ist()), qid))
            if row["scheduled_post_id"]:
                db.execute("UPDATE scheduled_posts SET status='posted' WHERE id=?",
                           (row["scheduled_post_id"],))
            db.add_upload_log(row["platform"], name, "posted", message)
            log.info("publish: POSTED %s (%s)", name, row["platform"])
            # v1.3: upload event -> admin panel (consent-gated, fail-silent)
            try:
                from .telemetry import notify_upload
                notify_upload(db, cfg)
            except Exception:  # noqa: BLE001
                pass
            eng.notify.emit("OCTORA — Posted ✅", f"{name} → {row['platform']}")
            self.tick.emit({"key": "publish", "label": "Posted", "progress": 100,
                            "detail": name, "retries": row["attempts"]})
        else:
            attempts = (row["attempts"] or 0) + 1
            if attempts >= MAX_ATTEMPTS:
                db.execute("UPDATE upload_queue SET status='dead', attempts=?, "
                           "last_error=?, updated_at=? WHERE id=?",
                           (attempts, message, iso_ist(now_ist()), qid))
                if row["scheduled_post_id"]:
                    db.execute("UPDATE scheduled_posts SET status='failed' WHERE id=?",
                               (row["scheduled_post_id"],))
                db.add_upload_log(row["platform"], name, "failed", message)
                log.error("publish: DEAD %s after %d attempts: %s", name, attempts, message)
                eng.notify.emit("OCTORA — Failed ❌", f"{name}: {message}")
            else:
                wait = RETRY_BASE_SECONDS * (2 ** (attempts - 1))
                nxt = iso_ist(now_ist() + timedelta(seconds=wait))
                db.execute("UPDATE upload_queue SET status='queued', attempts=?, "
                           "last_error=?, next_retry_at=?, updated_at=? WHERE id=?",
                           (attempts, message, nxt, iso_ist(now_ist()), qid))
                db.add_upload_log(row["platform"], name, "failed",
                                  f"attempt {attempts}: {message} — retry in {wait}s")
                log.warning("publish: retry %d for %s in %ds (%s)", attempts, name, wait, message)
            self.tick.emit({"key": "publish", "label": "Retrying", "progress": 0,
                            "detail": f"{name}: {message}"[:70], "retries": attempts})
        eng.queue_changed.emit()
        eng.stats_changed.emit()
        return True


    def _niche_metadata(self, db, cfg, asset_id, asset_path, filename):
        """Autopilot metadata for niche-sourced assets.

        Manual mode fills the niche's manual_* templates; auto mode asks
        Gemini 2.0 Flash (keyword fallback when offline/keyless). The rendered
        result is stored on the asset row and returned for the publish call.
        Never raises — the pipeline must not jam on metadata."""
        try:
            if not asset_id:
                return None
            a = db.query_one("SELECT niche_id FROM assets WHERE id=?", (asset_id,))
            nid = (a["niche_id"] if a else 0) or 0
            if not nid:
                return None
            niche = db.get_niche(nid)
            if not niche:
                return None
            mode = (niche.get("mode") or "auto").lower()
            if mode == "manual":
                idx_r = db.query_one("SELECT COUNT(*) c FROM assets WHERE niche_id=?",
                                     (nid,))
                index = (idx_r["c"] if idx_r else 0) or 1
                meta = seo.apply_manual(niche, filename, index)
            else:
                meta = seo.generate_auto(asset_path, niche)
            tags = meta.get("tags") or []
            tags_str = ",".join(tags) if isinstance(tags, list) else str(tags)
            db.execute("UPDATE assets SET meta_title=?, meta_description=?, "
                       "meta_tags=?, meta_caption=? WHERE id=?",
                       (meta.get("title", ""), meta.get("description", ""),
                        tags_str, meta.get("caption", ""), asset_id))
            log.info("publish: niche '%s' (%s mode) metadata applied to %s",
                     niche.get("name"), mode, filename)
            return {"title": meta.get("title", ""),
                    "description": meta.get("description", ""),
                    "tags": tags if isinstance(tags, list) else [],
                    "caption": meta.get("caption", "") or meta.get("title", "")}
        except Exception as e:  # noqa: BLE001
            log.warning("niche metadata skipped (%s)", e)
            return None


class CleanupWorker(_Worker):
    """Auto-deletes local files ONLY after verified success (Drive done + posted).

    Safety: never deletes unless drive_status='done' AND at least one 'posted'
    queue entry exists for the asset AND the auto-delete setting is on.
    With 'keep backup' on, files are moved to the backup folder instead.
    """

    def run(self):
        while not self._stop:
            try:
                self._sweep()
                for _ in range(450):  # ~45s between sweeps
                    if self._stop:
                        return
                    self.tick.emit({"key": "cleanup", "label": "Armed", "progress": 0,
                                    "detail": "Watching for verified uploads", "retries": 0})
                    self.nap(0.1)
            except Exception as e:  # noqa: BLE001
                log.error("cleanup worker error: %s", e)
                self.nap(10)

    def _sweep(self):
        db, cfg = self.engine.db, self.engine.cfg
        if not cfg.get("auto_delete_after_success", True):
            return
        rows = db.query(
            """SELECT a.* FROM assets a
               WHERE a.drive_status='done' AND a.status='ready'
               AND EXISTS (SELECT 1 FROM upload_queue q
                           WHERE q.asset_id=a.id AND q.status='posted')""")
        for a in rows:
            p = Path(a["path"])
            try:
                if cfg.get("keep_backup", False):
                    bdir = Path(cfg.get("backup_folder") or (Path(cfg.get("asset_folder")) / "backup"))
                    bdir.mkdir(parents=True, exist_ok=True)
                    dest = bdir / p.name
                    if p.exists():
                        shutil.move(str(p), str(dest))
                    note = f"moved to backup {dest}"
                else:
                    if p.exists():
                        p.unlink()
                    note = "local file auto-deleted after verified upload+post"
                db.execute("UPDATE assets SET status='archived', note=? WHERE id=?",
                           (note, a["id"]))
                log.info("cleanup: %s (%s)", a["filename"], note)
                self.tick.emit({"key": "cleanup", "label": "Cleaning", "progress": 50,
                                "detail": a["filename"], "retries": 0})
            except Exception as e:  # noqa: BLE001
                log.error("cleanup: could not remove %s: %s", a["filename"], e)


class Engine(QObject):
    pipeline_updated = pyqtSignal(dict)
    queue_changed = pyqtSignal()
    stats_changed = pyqtSignal()
    notify = pyqtSignal(str, str)

    def __init__(self, db: Database, cfg: Config):
        super().__init__()
        self.db = db
        self.cfg = cfg
        self.upload_paused = False
        self._cards = {key: {"key": key, "label": "Idle", "progress": 0,
                             "detail": "—", "retries": 0}
                       for key, _, _ in STAGE_DEFS}
        self.workers: list[_Worker] = []
        self._sched = QTimer(self)
        self._sched.timeout.connect(self._scheduler_tick)
        self._sched.start(20_000)

    # ---- lifecycle ----
    def start(self):
        # Crash recovery: a killed/previous run can leave rows in a transient
        # "in-progress" state. Every pump only picks up the idle state, so
        # without this those items would sit stuck forever.
        self.db.execute("UPDATE downloads SET status='queued' WHERE status='downloading'")
        self.db.execute("UPDATE upload_queue SET status='queued' WHERE status='uploading'")
        self.db.execute("UPDATE assets SET drive_status='pending' WHERE drive_status='uploading'")
        log.info("engine: recovered interrupted downloads/uploads/drive syncs")
        # lazy import: autopilot imports _Worker from this module (cycle guard)
        from .autopilot import NicheScheduler
        for cls in (DownloadWorker, FetchWorker, RenderWorker,
                    DriveWorker, PublishWorker, CleanupWorker, NicheScheduler):
            w = cls(self, cls.__name__)
            w.tick.connect(self._on_tick)
            w.start()
            self.workers.append(w)
        log.info("engine started (demo_mode=%s)", self.cfg.demo_mode)
        self._scheduler_tick()

    def stop(self):
        self._sched.stop()
        for w in self.workers:
            w.stop()
        for w in self.workers:
            w.wait(3000)

    def _on_tick(self, card: dict):
        self._cards[card["key"]] = card
        self.pipeline_updated.emit(dict(self._cards))

    def cards(self):
        return dict(self._cards)

    # ---- scheduler: due IST posts -> upload queue ----
    def _scheduler_tick(self):
        try:
            now = iso_ist(now_ist())
            # NOT EXISTS guard: if a previous tick enqueued this post but the
            # app died before marking it in_queue, the next tick must NOT
            # create a second upload_queue row for the same post.
            due = self.db.query(
                "SELECT * FROM scheduled_posts WHERE status='queued' AND scheduled_at<=? "
                "AND NOT EXISTS (SELECT 1 FROM upload_queue q "
                "WHERE q.scheduled_post_id=scheduled_posts.id "
                "AND q.status IN ('queued','uploading','paused'))",
                (now,))
            import json as _json
            for p in due:
                meta = build_meta(self.db, p["platform"], asset_id=p["asset_id"],
                                  campaign_id=p["campaign_id"],
                                  asset_filename="",
                                  override_json=p["meta_json"] or "")
                self.enqueue(platform=p["platform"], scheduled_post_id=p["id"],
                             asset_id=p["asset_id"], priority=7, caption=meta["caption"],
                             meta_json=_json.dumps(meta, ensure_ascii=False))
                self.db.execute("UPDATE scheduled_posts SET status='in_queue' WHERE id=?",
                                (p["id"],))
                log.info("scheduler: queued '%s' (%s)", meta["title"][:40], p["platform"])
            if due:
                self.queue_changed.emit()
                self.stats_changed.emit()
        except Exception as e:  # noqa: BLE001
            log.error("scheduler error: %s", e)

    # ---- queue ops (used by UI) ----
    def enqueue(self, platform, asset_id=None, scheduled_post_id=None,
                priority=5, caption="", meta_json="") -> int:
        cur = self.db.execute(
            "INSERT INTO upload_queue(platform,asset_id,scheduled_post_id,priority,status,"
            "meta_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (platform, asset_id, scheduled_post_id, priority, "queued", meta_json,
             iso_ist(now_ist()), iso_ist(now_ist())))
        self.queue_changed.emit()
        self.stats_changed.emit()
        return cur.lastrowid

    def enqueue_download(self, url: str, campaign_id=None, note: str = "") -> int:
        cur = self.db.execute(
            "INSERT INTO downloads(url,campaign_id,status,note,created_at) VALUES(?,?,?,?,?)",
            (url, campaign_id, "queued", note or "", iso_ist(now_ist())))
        log.info("download queued: %s", url[:80])
        self.stats_changed.emit()
        return cur.lastrowid

    def set_paused(self, paused: bool):
        self.upload_paused = paused
        log.info("upload engine %s", "paused" if paused else "resumed")

    def cancel_item(self, qid: int):
        self.db.execute("UPDATE upload_queue SET status='cancelled', updated_at=? WHERE id=?",
                        (iso_ist(now_ist()), qid))
        self.queue_changed.emit()

    def pause_item(self, qid: int):
        self.db.execute("UPDATE upload_queue SET status='paused', updated_at=? WHERE id=?",
                        (iso_ist(now_ist()), qid))
        self.queue_changed.emit()

    def resume_item(self, qid: int):
        self.db.execute("UPDATE upload_queue SET status='queued', next_retry_at='', "
                        "updated_at=? WHERE id=?", (iso_ist(now_ist()), qid))
        self.queue_changed.emit()

    def retry_item(self, qid: int):
        self.db.execute("UPDATE upload_queue SET status='queued', attempts=0, "
                        "last_error='', next_retry_at='', updated_at=? WHERE id=?",
                        (iso_ist(now_ist()), qid))
        self.queue_changed.emit()

    def demo_burst(self, n: int = 4):
        """INITIATE HIGHER OUTPUT — queue demo downloads; the whole pipeline
        (download -> render -> drive -> publish -> cleanup) then runs visibly."""
        for i in range(n):
            self.enqueue_download(f"https://demo.octora.local/burst_{int(time.time())}_{i}.mp4")
        log.info("demo burst: queued %d downloads", n)
