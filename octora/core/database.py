"""SQLite storage: campaigns, assets, schedule, upload queue, logs. Thread-safe."""
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import data_dir

IST = timezone(timedelta(hours=5, minutes=30))

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  platform TEXT NOT NULL,          -- 'YT Shorts'
  source_folder TEXT DEFAULT '',
  schedule_time TEXT DEFAULT '18:00',
  caption_template TEXT DEFAULT '',
  hashtags TEXT DEFAULT '',
  active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS assets(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT UNIQUE,
  size INTEGER DEFAULT 0,
  duration REAL DEFAULT 0,
  width INTEGER DEFAULT 0,
  height INTEGER DEFAULT 0,
  status TEXT DEFAULT 'new',       -- new | ready | failed
  note TEXT DEFAULT '',
  added_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS scheduled_posts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id INTEGER,
  asset_id INTEGER,
  platform TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,      -- ISO in IST
  status TEXT DEFAULT 'queued',    -- queued | posted | failed | cancelled
  caption TEXT DEFAULT '',
  attempts INTEGER DEFAULT 0,
  created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS upload_queue(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scheduled_post_id INTEGER,
  asset_id INTEGER,
  platform TEXT NOT NULL,
  priority INTEGER DEFAULT 5,
  status TEXT DEFAULT 'queued',    -- queued | uploading | posted | failed | dead | cancelled | paused
  attempts INTEGER DEFAULT 0,
  last_error TEXT DEFAULT '',
  next_retry_at TEXT DEFAULT '',
  created_at TEXT DEFAULT '',
  updated_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS uploads_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT, asset TEXT, status TEXT, message TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS app_logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  level TEXT, source TEXT, message TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS downloads(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  campaign_id INTEGER,
  status TEXT DEFAULT 'queued',    -- queued | downloading | done | failed
  progress INTEGER DEFAULT 0,
  asset_id INTEGER,
  error TEXT DEFAULT '',
  created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS niches(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  keywords TEXT DEFAULT '',
  videos_per_day INTEGER DEFAULT 5,
  mode TEXT DEFAULT 'auto' CHECK(mode IN ('auto','manual')),
  manual_title TEXT DEFAULT '',
  manual_description TEXT DEFAULT '',
  manual_tags TEXT DEFAULT '',
  manual_caption TEXT DEFAULT '',
  enabled INTEGER DEFAULT 1,
  last_run TEXT DEFAULT '',
  source_type TEXT DEFAULT 'stock',   -- 'stock' (Pexels/Pixabay) | 'links' (social URLs)
  source_links TEXT DEFAULT '',       -- newline-separated URLs for 'links' niches
  created_at TEXT DEFAULT ''
);
"""


def now_ist() -> datetime:
    return datetime.now(IST)


def iso_ist(dt: datetime) -> str:
    return dt.astimezone(IST).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "octora.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            # migrations for DBs created by older versions
            for ddl in (
                "ALTER TABLE assets ADD COLUMN drive_status TEXT DEFAULT 'pending'",
                "ALTER TABLE assets ADD COLUMN drive_file_id TEXT DEFAULT ''",
                # v1.2: SEO metadata engine
                "ALTER TABLE campaigns ADD COLUMN title_template TEXT DEFAULT ''",
                "ALTER TABLE campaigns ADD COLUMN description_template TEXT DEFAULT ''",
                "ALTER TABLE campaigns ADD COLUMN tags_template TEXT DEFAULT ''",
                "ALTER TABLE campaigns ADD COLUMN niche TEXT DEFAULT 'tech'",
                "ALTER TABLE scheduled_posts ADD COLUMN meta_json TEXT DEFAULT ''",
                "ALTER TABLE upload_queue ADD COLUMN meta_json TEXT DEFAULT ''",
                # v1.4 autopilot: niches + provenance + per-asset rendered metadata
                "ALTER TABLE downloads ADD COLUMN note TEXT DEFAULT ''",
                "ALTER TABLE assets ADD COLUMN source_id TEXT DEFAULT ''",
                "ALTER TABLE assets ADD COLUMN niche_id INTEGER DEFAULT 0",
                "ALTER TABLE assets ADD COLUMN meta_title TEXT DEFAULT ''",
                "ALTER TABLE assets ADD COLUMN meta_description TEXT DEFAULT ''",
                "ALTER TABLE assets ADD COLUMN meta_tags TEXT DEFAULT ''",
                "ALTER TABLE assets ADD COLUMN meta_caption TEXT DEFAULT ''",
                # v1.4 autopilot: social-link sourcing per niche
                "ALTER TABLE niches ADD COLUMN source_type TEXT DEFAULT 'stock'",
                "ALTER TABLE niches ADD COLUMN source_links TEXT DEFAULT ''",
            ):
                try:
                    self._conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # column already exists
            self._conn.commit()
        if self.get_kv("seeded") != "1":
            self.seed_demo()
            self.set_kv("seeded", "1")

    # ---- low level ----
    def execute(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def get_kv(self, key, default=""):
        r = self.query_one("SELECT value FROM kv WHERE key=?", (key,))
        return r["value"] if r else default

    def set_kv(self, key, value):
        self.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)", (key, str(value)))

    # ---- logging ----
    def add_log(self, level, source, message):
        self.execute(
            "INSERT INTO app_logs(level,source,message,at) VALUES(?,?,?,?)",
            (level, source, message, iso_ist(now_ist())),
        )
        # keep table bounded
        self.execute("DELETE FROM app_logs WHERE id NOT IN (SELECT id FROM app_logs ORDER BY id DESC LIMIT 2000)")

    def add_upload_log(self, platform, asset, status, message=""):
        self.execute(
            "INSERT INTO uploads_log(platform,asset,status,message,at) VALUES(?,?,?,?,?)",
            (platform, asset, status, message, iso_ist(now_ist())),
        )

    # ---- autopilot: niches + dedupe ----
    def niche_dedup_hit(self, source_id: str, sha256: str) -> bool:
        """True if any asset already carries this stock source_id, or this
        exact file hash (sha256 must be non-empty)."""
        if source_id:
            r = self.query_one(
                "SELECT id FROM assets WHERE source_id=? AND source_id<>''",
                (source_id,))
            if r:
                return True
        if sha256:
            r = self.query_one("SELECT id FROM assets WHERE sha256=?", (sha256,))
            if r:
                return True
        return False

    def list_niches(self, enabled_only: bool = False):
        sql = "SELECT * FROM niches" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY name"
        return [dict(r) for r in self.query(sql)]

    def get_niche(self, niche_id: int):
        r = self.query_one("SELECT * FROM niches WHERE id=?", (niche_id,))
        return dict(r) if r else None

    # ---- stats for dashboard ----
    def stats(self) -> dict:
        today = now_ist().date().isoformat()
        reels = self.query_one(
            "SELECT COUNT(*) c FROM uploads_log WHERE platform LIKE '%Reel%' AND status='posted'")
        shorts = self.query_one(
            "SELECT COUNT(*) c FROM uploads_log WHERE platform LIKE '%Short%' AND status='posted'")
        reels_today = self.query_one(
            "SELECT COUNT(*) c FROM uploads_log WHERE platform LIKE '%Reel%' AND status='posted' AND substr(at,1,10)=?",
            (today,))
        shorts_today = self.query_one(
            "SELECT COUNT(*) c FROM uploads_log WHERE platform LIKE '%Short%' AND status='posted' AND substr(at,1,10)=?",
            (today,))
        total = self.query_one("SELECT COUNT(*) c FROM uploads_log WHERE status IN ('posted','failed')")
        posted = self.query_one("SELECT COUNT(*) c FROM uploads_log WHERE status='posted'")
        active = self.query_one(
            "SELECT COUNT(*) c FROM upload_queue WHERE status IN ('queued','uploading')")
        dl_active = self.query_one(
            "SELECT COUNT(*) c FROM downloads WHERE status IN ('queued','downloading')")
        errors = self.query_one(
            "SELECT COUNT(*) c FROM app_logs WHERE level='ERROR' AND substr(at,1,10)=?",
            (today,))
        ok = posted["c"] or 0
        tot = total["c"] or 0
        return {
            "reels": reels["c"] or 0, "shorts": shorts["c"] or 0,
            "reels_today": reels_today["c"] or 0, "shorts_today": shorts_today["c"] or 0,
            "success_rate": round(100.0 * ok / tot, 1) if tot else 100.0,
            "active_tasks": (active["c"] or 0) + (dl_active["c"] or 0),
            "errors_today": errors["c"] or 0,
        }

    def uploads_per_day(self, days=14):
        rows = self.query(
            """SELECT substr(at,1,10) d,
                      SUM(CASE WHEN platform LIKE '%Reel%' AND status='posted' THEN 1 ELSE 0 END) reels,
                      SUM(CASE WHEN platform LIKE '%Short%' AND status='posted' THEN 1 ELSE 0 END) shorts
               FROM uploads_log WHERE at >= date('now','-{} days') GROUP BY d ORDER BY d""".format(days))
        return [dict(r) for r in rows]

    def platform_totals(self):
        rows = self.query(
            """SELECT CASE WHEN platform LIKE '%Reel%' THEN 'IG Reels' ELSE 'YT Shorts' END p,
                      COUNT(*) c FROM uploads_log WHERE status='posted' GROUP BY p""")
        return {r["p"]: r["c"] for r in rows}

    def posted_hours(self):
        rows = self.query(
            "SELECT CAST(substr(at,12,2) AS INTEGER) h, COUNT(*) c FROM uploads_log "
            "WHERE status='posted' GROUP BY h")
        return {r["h"]: r["c"] for r in rows if r["h"] is not None}

    # ---- demo seed: makes first launch look alive ----
    def seed_demo(self):
        t = now_ist()
        today = t.date()
        self.execute(
            "INSERT INTO campaigns(name,platform,source_folder,schedule_time,caption_template,hashtags,"
            "title_template,description_template,tags_template,niche,active,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("TechTips Daily", "YT Shorts", "", "14:00",
             "Tech tip of the day 🚀 {keyword}", "#tech #shorts #tips",
             "{keyword} 🔥 #Shorts",
             "{keyword} — full breakdown 👇\n\n🎯 Topic: {keyword}\n📅 {date}\n\n{tags_line}\n\n#Shorts",
             "tech, {keyword}, shorts, youtube shorts, viral",
             "tech", 1, iso_ist(t)))
        self.execute(
            "INSERT INTO campaigns(name,platform,source_folder,schedule_time,caption_template,hashtags,"
            "title_template,description_template,tags_template,niche,active,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("Design Shorts", "YT Shorts", "", "15:30",
             "Design that pops ✨ {keyword}", "#design #shorts #ui",
             "{keyword}", "", "",
             "design", 1, iso_ist(t)))
        self.execute(
            "INSERT INTO campaigns(name,platform,source_folder,schedule_time,caption_template,hashtags,"
            "title_template,description_template,tags_template,niche,active,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("Startup News", "YT Shorts", "", "19:30",
             "Startup world update 📰 {keyword}", "#startup #news",
             "{keyword}", "", "",
             "finance", 1, iso_ist(t)))

        # 14 days of upload history for analytics
        import random
        random.seed(7)
        for d in range(13, -1, -1):
            day = today - timedelta(days=d)
            for i in range(random.randint(4, 10)):
                plat = "YT Shorts"
                ok = random.random() < 0.97
                at = datetime(day.year, day.month, day.day,
                              random.randint(8, 22), random.randint(0, 59), tzinfo=IST)
                self.execute(
                    "INSERT INTO uploads_log(platform,asset,status,message,at) VALUES(?,?,?,?,?)",
                    (plat, f"clip_{day.strftime('%m%d')}_{i:02d}.mp4",
                     "posted" if ok else "failed",
                     "" if ok else "simulated network blip", iso_ist(at)))

        # today's scheduler timeline: posted / now / queued
        items = [
            ("YT Shorts", "TechTips #122", -150, "posted"),
            ("YT Shorts", "ProductDemo_A", -75, "posted"),
            ("YT Shorts", "DesignTips #09", 0, "queued"),
            ("YT Shorts", "Review_Builds", 75, "queued"),
            ("YT Shorts", "StartupNews #31", 165, "queued"),
        ]
        for plat, name, mins, status in items:
            at = t + timedelta(minutes=mins)
            cap = f"{name} — auto-published by OCTORA"
            self.execute(
                "INSERT INTO scheduled_posts(campaign_id,platform,scheduled_at,status,caption,created_at)"
                " VALUES (1,?,?,?,?,?)",
                (plat, iso_ist(at), status, cap, iso_ist(t)))
            # NOTE: queued items are picked up by the scheduler tick on engine
            # start — no orphan upload_queue rows are created here.
        # two demo downloads so the full pipeline is visibly alive on first launch
        for i in (1, 2):
            self.execute(
                "INSERT INTO downloads(url,campaign_id,status,created_at) VALUES(?,?,?,?)",
                (f"https://demo.octora.local/clip_{t.strftime('%H%M')}_{i}.mp4",
                 None, "queued", iso_ist(t)))
        # example niches (disabled by default) so the user sees how Autopilot
        # sourcing works: one legal stock-API niche, one social-links niche.
        self.execute(
            "INSERT OR IGNORE INTO niches(name,keywords,videos_per_day,mode,"
            "source_type,enabled,created_at) VALUES(?,?,?,?,?,?,?)",
            ("Animals — stock example", "animals", 5, "auto", "stock", 0,
             iso_ist(t)))
        self.execute(
            "INSERT OR IGNORE INTO niches(name,keywords,videos_per_day,mode,"
            "manual_title,manual_description,manual_tags,manual_caption,"
            "source_type,source_links,enabled,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("Social links — example", "", 5, "manual",
             "{keyword} | Daily {niche} #{index}",
             "{keyword}\n\nFollow for daily {niche} videos! ({date})",
             "{niche}, {keyword}, reels, viral",
             "👀 {keyword}\n\n#{niche} #reels",
             "links", "", 0, iso_ist(t)))
        self.add_log("INFO", "system", "Demo database seeded — welcome to OCTORA.")
