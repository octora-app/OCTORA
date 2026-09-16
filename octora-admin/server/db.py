"""Storage for the OCTORA admin panel.

SQLite by default (zero-config local dev). Set DATABASE_URL to a Postgres
URL for hosted deploys (recommended — free hosts wipe SQLite files on
redeploy; see ADMIN_SETUP.md). SQL is written with `?` placeholders and
translated to `%s` for Postgres automatically.
"""
from datetime import datetime, timedelta, timezone

from . import config


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DB:
    def __init__(self, url: str | None = None):
        self.url = url or config.DATABASE_URL
        self.pg = self.url.startswith("postgres://") or self.url.startswith("postgresql://")
        if self.pg:
            import psycopg
            from psycopg.rows import dict_row
            self._conn = psycopg.connect(self.url, autocommit=True, row_factory=dict_row)
        else:
            import sqlite3
            path = self.url.split(":///", 1)[1] if ":///" in self.url else self.url
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        self.init_schema()

    # -- low-level ---------------------------------------------------------
    def _q(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.pg else sql

    def _aid(self) -> str:
        return "SERIAL PRIMARY KEY" if self.pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(self._q(sql), params)
        if not self.pg:
            self._conn.commit()
        return cur

    def query(self, sql, params=()):
        return [dict(r) for r in self.execute(sql, params).fetchall()]

    def query_one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # -- schema ------------------------------------------------------------
    def init_schema(self):
        aid = self._aid()
        self.execute(f"""CREATE TABLE IF NOT EXISTS meta(
            k TEXT PRIMARY KEY, v TEXT)""")
        self.execute(f"""CREATE TABLE IF NOT EXISTS admins(
            id {aid}, username TEXT UNIQUE, pw_hash TEXT, salt TEXT, created_at TEXT)""")
        self.execute("""CREATE TABLE IF NOT EXISTS sessions(
            token_hash TEXT PRIMARY KEY, admin_id INTEGER, expires_at TEXT)""")
        self.execute("""CREATE TABLE IF NOT EXISTS licenses(
            key_id TEXT PRIMARY KEY, name TEXT, email TEXT,
            hwid_bound TEXT, issued_at TEXT, expires_at TEXT, days INTEGER,
            status TEXT DEFAULT 'active', armored TEXT, notes TEXT)""")
        self.execute(f"""CREATE TABLE IF NOT EXISTS users(
            id {aid}, hwid_hash TEXT UNIQUE, name TEXT, email TEXT,
            license_key_id TEXT, status TEXT DEFAULT 'active',
            plan TEXT DEFAULT 'full', app_version TEXT,
            first_seen TEXT, last_seen TEXT, notes TEXT)""")
        self.execute(f"""CREATE TABLE IF NOT EXISTS platforms(
            id {aid}, user_id INTEGER, platform TEXT,
            channel_id TEXT, channel_name TEXT, subscriber_count INTEGER DEFAULT 0,
            updated_at TEXT, UNIQUE(user_id, platform))""")
        self.execute(f"""CREATE TABLE IF NOT EXISTS heartbeats(
            id {aid}, user_id INTEGER, ts TEXT, app_version TEXT,
            uploads_total INTEGER DEFAULT 0, uploads_today INTEGER DEFAULT 0)""")

    # -- meta --------------------------------------------------------------
    def meta_get(self, k, default=None):
        r = self.query_one("SELECT v FROM meta WHERE k=?", (k,))
        return r["v"] if r else default

    def meta_set(self, k, v):
        if self.query_one("SELECT k FROM meta WHERE k=?", (k,)):
            self.execute("UPDATE meta SET v=? WHERE k=?", (v, k))
        else:
            self.execute("INSERT INTO meta(k,v) VALUES(?,?)", (k, v))

    # -- admins & sessions ---------------------------------------------------
    def get_admin(self, username="admin"):
        return self.query_one("SELECT * FROM admins WHERE username=?", (username,))

    def create_admin(self, username, pw_hash, salt):
        self.execute("INSERT INTO admins(username,pw_hash,salt,created_at) VALUES(?,?,?,?)",
                     (username, pw_hash, salt, utcnow()))

    def update_admin_pw(self, admin_id, pw_hash, salt):
        self.execute("UPDATE admins SET pw_hash=?, salt=? WHERE id=?", (pw_hash, salt, admin_id))

    def create_session(self, token_hash, admin_id, expires_at):
        self.execute("INSERT INTO sessions(token_hash,admin_id,expires_at) VALUES(?,?,?)",
                     (token_hash, admin_id, expires_at))

    def get_session(self, token_hash):
        return self.query_one("SELECT * FROM sessions WHERE token_hash=?", (token_hash,))

    def delete_session(self, token_hash):
        self.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def prune_sessions(self):
        self.execute("DELETE FROM sessions WHERE expires_at < ?", (utcnow(),))

    # -- licenses ------------------------------------------------------------
    def issue_license(self, key_id, name, email, hwid_bound, issued_at, expires_at,
                      days, armored, notes=""):
        self.execute("""INSERT INTO licenses(key_id,name,email,hwid_bound,issued_at,
                      expires_at,days,status,armored,notes)
                      VALUES(?,?,?,?,?,?,?,'active',?,?)""",
                     (key_id, name, email, hwid_bound, issued_at, expires_at, days, armored, notes))

    def get_license(self, key_id):
        return self.query_one("SELECT * FROM licenses WHERE key_id=?", (key_id,))

    def list_licenses(self, search=""):
        if search:
            like = f"%{search}%"
            return self.query("SELECT * FROM licenses WHERE name LIKE ? OR email LIKE ? "
                              "OR key_id LIKE ? ORDER BY issued_at DESC", (like, like, like))
        return self.query("SELECT * FROM licenses ORDER BY issued_at DESC")

    def set_license_status(self, key_id, status):
        self.execute("UPDATE licenses SET status=? WHERE key_id=?", (status, key_id))

    def bind_license(self, key_id, hwid_hash):
        self.execute("UPDATE licenses SET hwid_bound=? WHERE key_id=?", (hwid_hash, key_id))

    # -- users ---------------------------------------------------------------
    def upsert_user(self, hwid_hash, app_version="", license_key_id="",
                    uploads_total=0, uploads_today=0):
        now = utcnow()
        u = self.query_one("SELECT * FROM users WHERE hwid_hash=?", (hwid_hash,))
        if u:
            self.execute("""UPDATE users SET last_seen=?, app_version=?,
                            license_key_id=CASE WHEN ?<>'' THEN ? ELSE license_key_id END
                            WHERE id=?""",
                         (now, app_version or u["app_version"], license_key_id,
                          license_key_id, u["id"]))
            uid = u["id"]
        else:
            cur = self.execute("""INSERT INTO users(hwid_hash,name,email,license_key_id,
                                status,plan,app_version,first_seen,last_seen)
                                VALUES(?,'','',?,'active','full',?,?,?)""",
                               (hwid_hash, license_key_id, app_version, now, now))
            uid = cur.lastrowid if not self.pg else self.query_one(
                "SELECT id FROM users WHERE hwid_hash=?", (hwid_hash,))["id"]
        # fill name/email from the license when known
        if license_key_id:
            lic = self.get_license(license_key_id)
            if lic and (not u or not u["name"]):
                self.execute("UPDATE users SET name=?, email=? WHERE id=?",
                             (lic["name"], lic["email"], uid))
        return uid

    def get_user(self, uid):
        return self.query_one("SELECT * FROM users WHERE id=?", (uid,))

    def list_users(self, search="", limit=200):
        if search:
            like = f"%{search}%"
            return self.query("SELECT * FROM users WHERE name LIKE ? OR email LIKE ? "
                              "OR hwid_hash LIKE ? ORDER BY last_seen DESC LIMIT ?",
                              (like, like, like, limit))
        return self.query("SELECT * FROM users ORDER BY last_seen DESC LIMIT ?", (limit,))

    def set_user_status(self, uid, status):
        self.execute("UPDATE users SET status=? WHERE id=?", (status, uid))

    # -- platforms & heartbeats ----------------------------------------------
    def upsert_platform(self, user_id, platform, channel_id="", channel_name="",
                        subscriber_count=0):
        now = utcnow()
        ex = self.query_one("SELECT id FROM platforms WHERE user_id=? AND platform=?",
                            (user_id, platform))
        if ex:
            self.execute("""UPDATE platforms SET channel_id=?, channel_name=?,
                            subscriber_count=?, updated_at=? WHERE id=?""",
                         (channel_id, channel_name, subscriber_count, now, ex["id"]))
        else:
            self.execute("""INSERT INTO platforms(user_id,platform,channel_id,channel_name,
                            subscriber_count,updated_at) VALUES(?,?,?,?,?,?)""",
                         (user_id, platform, channel_id, channel_name, subscriber_count, now))

    def user_platforms(self, user_id):
        return self.query("SELECT * FROM platforms WHERE user_id=? ORDER BY platform",
                          (user_id,))

    def add_heartbeat(self, user_id, app_version, uploads_total, uploads_today):
        self.execute("""INSERT INTO heartbeats(user_id,ts,app_version,uploads_total,
                        uploads_today) VALUES(?,?,?,?,?)""",
                     (user_id, utcnow(), app_version, uploads_total, uploads_today))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=config.HEARTBEAT_PRUNE_DAYS))
        self.execute("DELETE FROM heartbeats WHERE ts < ?",
                     (cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),))

    def heartbeat_history(self, user_id, limit=60):
        return self.query("SELECT ts, uploads_total, uploads_today FROM heartbeats "
                          "WHERE user_id=? ORDER BY ts DESC LIMIT ?", (user_id, limit))

    # -- overview --------------------------------------------------------------
    def overview(self):
        total_users = self.query_one("SELECT COUNT(*) c FROM users")["c"]
        active_lic = self.query_one(
            "SELECT COUNT(*) c FROM licenses WHERE status='active' AND expires_at >= ?",
            (utcnow(),))["c"]
        channels = self.query_one("SELECT COUNT(*) c FROM platforms")["c"]
        today = utcnow()[:10]
        up_today = self.query_one(
            "SELECT COALESCE(SUM(uploads_today),0) s FROM heartbeats WHERE ts LIKE ?",
            (today + "%",))["s"]
        recent = self.query("SELECT * FROM users ORDER BY last_seen DESC LIMIT 8")
        # uploads per day, last 14 days
        per_day = self.query(
            "SELECT SUBSTR(ts,1,10) d, SUM(uploads_today) s FROM heartbeats "
            "WHERE ts >= ? GROUP BY d ORDER BY d",
            ((datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d"),))
        return {"total_users": total_users, "active_licenses": active_lic,
                "connected_channels": channels, "uploads_today": up_today or 0,
                "recent_users": recent, "uploads_per_day": per_day}
