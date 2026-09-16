"""Storage for the OCTORA admin panel.

SQLite by default (zero-config local dev). Set DATABASE_URL to a Postgres
URL for hosted deploys (recommended — free hosts wipe SQLite files on
redeploy; see ADMIN_SETUP.md). SQL is written with `?` placeholders and
translated to `%s` for Postgres automatically.
"""
from datetime import datetime, timedelta, timezone

from contextlib import contextmanager

from . import config


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_connection_error(exc: Exception) -> bool:
    """True when `exc` means the Postgres link itself died (a retry is safe).

    SQLSTATE class 08 covers every connection exception. The message fallback
    catches drivers/proxies that don't set sqlstate.
    """
    if str(getattr(exc, "sqlstate", "") or "").startswith("08"):
        return True
    msg = str(exc).lower()
    return any(s in msg for s in (
        "connection is closed", "connection failed", "connection refused",
        "server closed the connection", "terminating connection",
        "ssl connection has been closed", "broken pipe", "connection reset",
        "connection timed out",
    ))


class DB:
    def __init__(self, url: str | None = None):
        self.url = url or config.DATABASE_URL
        self.pg = self.url.startswith("postgres://") or self.url.startswith("postgresql://")
        self._tx_depth = 0
        self._connect()
        self.init_schema()

    def _connect(self):
        """(Re)open the DB connection. Called at boot and after a dropped link."""
        if self.pg:
            import psycopg
            from psycopg.rows import dict_row
            self._conn = psycopg.connect(self.url, autocommit=True, row_factory=dict_row)
        else:
            import sqlite3
            path = self.url.split(":///", 1)[1] if ":///" in self.url else self.url
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

    # -- low-level ---------------------------------------------------------
    def _q(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.pg else sql

    def _aid(self) -> str:
        return "SERIAL PRIMARY KEY" if self.pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    def execute(self, sql, params=()):
        try:
            return self._execute_inner(sql, params)
        except Exception as e:
            # Hosted Postgres (Neon) drops idle pooled connections while the
            # app keeps running. Reconnect once and retry so a cold database
            # shows up as a slightly slow request instead of a 500. Never
            # retry inside an explicit transaction (state would be unclear).
            if self.pg and self._tx_depth == 0 and _is_connection_error(e):
                self._connect()
                return self._execute_inner(sql, params)
            raise

    def _execute_inner(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(self._q(sql), params)
        if not self.pg and self._tx_depth == 0:
            self._conn.commit()
        return cur

    @contextmanager
    def transaction(self):
        """Run a block as ONE atomic database transaction.

        SQLite: BEGIN IMMEDIATE takes the write lock up-front, so concurrent
        writers serialize instead of racing. Postgres: explicit transaction
        (the connection normally runs in autocommit mode); callers that need
        per-key serialization should also call serialize_key().
        Nested use is a no-op (joins the outer transaction).
        """
        if self._tx_depth:
            yield self
            return
        if self.pg:
            self._conn.autocommit = False
        else:
            self._conn.execute("BEGIN IMMEDIATE")
        self._tx_depth = 1
        try:
            yield self
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            self._tx_depth = 0
            if self.pg:
                self._conn.autocommit = True

    def serialize_key(self, key: str):
        """Mutual exclusion for one logical key inside a transaction.

        Postgres: transaction-scoped advisory lock. SQLite: writers are
        already serialized by BEGIN IMMEDIATE, so this is a no-op.
        """
        if self.pg:
            self.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (key,))

    @staticmethod
    def is_unique_violation(exc: Exception) -> bool:
        """True when `exc` is a duplicate-key error (sqlite3 / psycopg)."""
        mod = type(exc).__module__
        name = type(exc).__name__
        if "sqlite3" in mod and name == "IntegrityError":
            return "UNIQUE" in str(exc).upper()
        if "psycopg" in mod and name in ("UniqueViolation",):
            return True
        # psycopg2-style fallback
        return name == "UniqueViolation"

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
            first_seen TEXT, last_seen TEXT, notes TEXT,
            trial_started_at TEXT DEFAULT '')""")
        self.execute(f"""CREATE TABLE IF NOT EXISTS platforms(
            id {aid}, user_id INTEGER, platform TEXT,
            channel_id TEXT, channel_name TEXT, subscriber_count INTEGER DEFAULT 0,
            updated_at TEXT, UNIQUE(user_id, platform))""")
        self.execute(f"""CREATE TABLE IF NOT EXISTS heartbeats(
            id {aid}, user_id INTEGER, ts TEXT, app_version TEXT,
            uploads_total INTEGER DEFAULT 0, uploads_today INTEGER DEFAULT 0)""")
        self.execute("""CREATE TABLE IF NOT EXISTS payments(
            txid TEXT PRIMARY KEY, plan TEXT, amount_usdt REAL,
            hwid_hash TEXT, name TEXT, email TEXT, from_address TEXT,
            status TEXT DEFAULT 'confirmed', created_at TEXT)""")
        self.execute(f"""CREATE TABLE IF NOT EXISTS audit_log(
            id {aid}, ts TEXT, admin TEXT, action TEXT, target TEXT, details TEXT)""")
        self.execute(f"""CREATE TABLE IF NOT EXISTS rebind_requests(
            id {aid}, key_id TEXT, old_hwid_hash TEXT,
            new_hwid TEXT, new_hwid_hash TEXT, new_key_id TEXT,
            status TEXT DEFAULT 'pending', requested_at TEXT,
            decided_at TEXT, decided_by TEXT, notes TEXT)""")
        # ---- lightweight migrations for DBs created by older versions ----
        for ddl in ("ALTER TABLE sessions ADD COLUMN csrf_token TEXT",
                    "ALTER TABLE licenses ADD COLUMN hwid_raw TEXT DEFAULT ''",
                    "ALTER TABLE users ADD COLUMN trial_started_at TEXT DEFAULT ''"):
            try:
                self.execute(ddl)
            except Exception:
                pass  # column already exists

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

    def create_session(self, token_hash, admin_id, expires_at, csrf_token=""):
        self.execute("INSERT INTO sessions(token_hash,admin_id,expires_at,csrf_token) "
                     "VALUES(?,?,?,?)",
                     (token_hash, admin_id, expires_at, csrf_token))

    def set_session_csrf(self, token_hash, csrf_token):
        self.execute("UPDATE sessions SET csrf_token=? WHERE token_hash=?",
                     (csrf_token, token_hash))

    def delete_sessions_for_admin(self, admin_id):
        """Kill every session (used after a password change)."""
        self.execute("DELETE FROM sessions WHERE admin_id=?", (admin_id,))

    def get_session(self, token_hash):
        return self.query_one("SELECT * FROM sessions WHERE token_hash=?", (token_hash,))

    def delete_session(self, token_hash):
        self.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def prune_sessions(self):
        self.execute("DELETE FROM sessions WHERE expires_at < ?", (utcnow(),))

    # -- licenses ------------------------------------------------------------
    def issue_license(self, key_id, name, email, hwid_bound, issued_at, expires_at,
                      days, armored, notes="", hwid_raw=""):
        self.execute("""INSERT INTO licenses(key_id,name,email,hwid_bound,hwid_raw,issued_at,
                      expires_at,days,status,armored,notes)
                      VALUES(?,?,?,?,?,?,?,?,'active',?,?)""",
                     (key_id, name, email, hwid_bound, hwid_raw, issued_at, expires_at,
                      days, armored, notes))

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

    def get_active_license_by_hwid(self, hwid_hash):
        """Newest non-expired active license bound to this machine, if any."""
        return self.query_one(
            "SELECT * FROM licenses WHERE hwid_bound=? AND status='active' "
            "AND expires_at >= ? ORDER BY expires_at DESC LIMIT 1",
            (hwid_hash, utcnow()))

    def extend_license_expiry(self, key_id, extra_days):
        """Extend a license's expiry WITHOUT minting a new envelope.

        Call inside db.transaction(). Takes a row lock (FOR UPDATE on
        Postgres) so concurrent renewals can't compute from the same base
        and lose an extension. Returns (license_row, new_expires_at).
        The caller is responsible for minting + storing a fresh envelope
        (see rotate_license_envelope) — never return a stale envelope.
        """
        lic = self.query_one(
            "SELECT * FROM licenses WHERE key_id=?" + (" FOR UPDATE" if self.pg else ""),
            (key_id,))
        if not lic:
            return None, None
        base = lic["expires_at"] if lic["expires_at"] >= utcnow() else utcnow()
        cur = datetime.strptime(base, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        new_exp = (cur + timedelta(days=max(1, extra_days))).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.execute("UPDATE licenses SET expires_at=?, days=days+? WHERE key_id=?",
                     (new_exp, max(1, extra_days), key_id))
        return lic, new_exp

    def rotate_license_envelope(self, old_key_id, new_key_id, new_armored):
        """Store a freshly-minted envelope for a license.

        The key_id is the SHA-256 of the armored envelope, so a new envelope
        means a new key_id: the row is updated in place (same license, new
        file). Call inside db.transaction() together with the change that
        made the old envelope stale (renewal / rebind / admin extend).
        """
        self.execute("UPDATE licenses SET key_id=?, armored=? WHERE key_id=?",
                     (new_key_id, new_armored, old_key_id))

    def reset_license_hwid(self, key_id):
        """Unbind a license from its machine (e.g. customer reinstalled Windows).
        The next activation re-binds it to the new machine."""
        self.execute("UPDATE licenses SET hwid_bound='' WHERE key_id=?", (key_id,))

    # -- HWID rebind requests --------------------------------------------------
    # A rebind moves a license to a NEW machine with admin approval. The old
    # "reset HWID" flow only cleared the DB column while the signed envelope
    # still contained the original HWID, so it could never work — it is
    # disabled in favor of this flow, which mints a FRESH envelope for the
    # new HWID on approval.
    def create_rebind_request(self, key_id, old_hwid_hash, new_hwid, new_hwid_hash):
        """Insert a pending rebind request.

        Returns (request_id, "ok") | (None, "exists") when one is already
        pending | (None, "cooldown") inside the cooldown window.
        """
        if self.query_one("SELECT id FROM rebind_requests WHERE key_id=? "
                          "AND status='pending'", (key_id,)):
            return None, "exists"
        # Cooldown follows the key chain: approving a rebind rotates the
        # license to a NEW key_id, so match on new_key_id too — otherwise a
        # customer could rebind again immediately using the fresh license file.
        last = self.query_one(
            "SELECT decided_at FROM rebind_requests "
            "WHERE (key_id=? OR new_key_id=?) AND status='approved' "
            "ORDER BY decided_at DESC LIMIT 1", (key_id, key_id))
        if last:
            cutoff = (datetime.now(timezone.utc)
                      - timedelta(days=config.REBIND_COOLDOWN_DAYS)
                      ).strftime("%Y-%m-%dT%H:%M:%SZ")
            if last["decided_at"] >= cutoff:
                return None, "cooldown"
        self.execute("""INSERT INTO rebind_requests(key_id, old_hwid_hash, new_hwid,
                        new_hwid_hash, status, requested_at)
                        VALUES(?,?,?,?, 'pending', ?)""",
                     (key_id, old_hwid_hash, new_hwid, new_hwid_hash, utcnow()))
        row = self.query_one("SELECT id FROM rebind_requests WHERE key_id=? "
                             "AND status='pending' ORDER BY requested_at DESC LIMIT 1",
                             (key_id,))
        return (row["id"] if row else None), "ok"

    def get_rebind_request(self, req_id, for_update=False):
        return self.query_one(
            "SELECT * FROM rebind_requests WHERE id=?"
            + (" FOR UPDATE" if for_update and self.pg else ""), (req_id,))

    def latest_rebind_request(self, key_id):
        # Matches on new_key_id too: after approval the license row lives
        # under the rotated key, and the customer may poll with the new file.
        return self.query_one("SELECT * FROM rebind_requests "
                              "WHERE key_id=? OR new_key_id=? "
                              "ORDER BY requested_at DESC LIMIT 1", (key_id, key_id))

    def list_rebind_requests(self, status="pending", limit=100):
        return self.query("SELECT * FROM rebind_requests WHERE status=? "
                          "ORDER BY requested_at DESC LIMIT ?", (status, limit))

    def decide_rebind(self, req_id, approve, decided_by, new_key_id="", notes=""):
        """Approve/reject a pending request. Call inside db.transaction()."""
        r = self.get_rebind_request(req_id, for_update=True)
        if not r or r["status"] != "pending":
            return None
        # re-check the cooldown inside the lock: no double-approvals racing
        # (matches on new_key_id too — see create_rebind_request).
        last = self.query_one(
            "SELECT decided_at FROM rebind_requests "
            "WHERE (key_id=? OR new_key_id=?) AND status='approved' "
            "ORDER BY decided_at DESC LIMIT 1", (r["key_id"], r["key_id"]))
        if approve and last:
            cutoff = (datetime.now(timezone.utc)
                      - timedelta(days=config.REBIND_COOLDOWN_DAYS)
                      ).strftime("%Y-%m-%dT%H:%M:%SZ")
            if last["decided_at"] >= cutoff:
                return "cooldown"
        status = "approved" if approve else "rejected"
        self.execute("UPDATE rebind_requests SET status=?, decided_at=?, decided_by=?, "
                     "new_key_id=?, notes=? WHERE id=?",
                     (status, utcnow(), decided_by, new_key_id, notes, req_id))
        return status

    # -- audit log ---------------------------------------------------------------
    def audit(self, admin, action, target="", details=""):
        self.execute("INSERT INTO audit_log(ts, admin, action, target, details) "
                     "VALUES(?,?,?,?,?)",
                     (utcnow(), admin or "", action, target or "", details or ""))

    def list_audit(self, limit=200):
        return self.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))

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

    # ---- one-trial-per-PC -------------------------------------------------
    def get_trial_started(self, hwid_hash):
        """ISO timestamp of this PC's first recorded trial, or ''."""
        u = self.query_one("SELECT trial_started_at FROM users WHERE hwid_hash=?",
                           (hwid_hash,))
        return (u["trial_started_at"] or "") if u else ""

    def record_trial_started(self, hwid_hash, iso):
        """Remember this PC's trial start. First write wins — never overwritten."""
        self.execute("""UPDATE users SET trial_started_at=?
                        WHERE hwid_hash=? AND (trial_started_at IS NULL OR trial_started_at='')""",
                     (iso, hwid_hash))

    def trial_check(self, hwid_hash, trial_started_at):
        """One-trial-per-PC verdict.

        trial_started_at = ''  -> client asks "may I start a trial?"
        trial_started_at = iso -> client reports "my trial started at <iso>".

        Returns (allowed: bool, recorded: str).
        """
        from datetime import datetime, timedelta, timezone
        self.upsert_user(hwid_hash)  # ensure the row exists before recording
        recorded = self.get_trial_started(hwid_hash)
        if not recorded:
            if trial_started_at:
                self.record_trial_started(hwid_hash, trial_started_at)
            return True, ""
        if not trial_started_at:
            return False, recorded  # this PC already had its trial
        try:
            rec = datetime.fromisoformat(recorded)
            rep = datetime.fromisoformat(trial_started_at)
            if rec.tzinfo is None:
                rec = rec.replace(tzinfo=timezone.utc)
            if rep.tzinfo is None:
                rep = rep.replace(tzinfo=timezone.utc)
            # Same trial being reported (5 min tolerance for clock skew).
            # A later timestamp means local data was wiped for a fresh trial.
            if rep <= rec + timedelta(minutes=5):
                return True, recorded
        except ValueError:
            pass
        return False, recorded

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

    # -- payments (USDT TRC-20) --------------------------------------------------
    def record_payment(self, txid, plan, amount_usdt, hwid_hash, name, email,
                       from_address):
        self.execute("""INSERT INTO payments(txid,plan,amount_usdt,hwid_hash,name,
                        email,from_address,status,created_at)
                        VALUES(?,?,?,?,?,?,?,'confirmed',?)""",
                     (txid, plan, amount_usdt, hwid_hash, name, email,
                      from_address, utcnow()))

    def get_payment(self, txid):
        return self.query_one("SELECT * FROM payments WHERE txid=?", (txid,))

    def list_payments(self, limit=200):
        return self.query("SELECT * FROM payments ORDER BY created_at DESC LIMIT ?",
                          (limit,))

    # -- overview --------------------------------------------------------------
    def overview(self):
        total_users = self.query_one("SELECT COUNT(*) c FROM users")["c"]
        active_lic = self.query_one(
            "SELECT COUNT(*) c FROM licenses WHERE status='active' AND expires_at >= ?",
            (utcnow(),))["c"]
        channels = self.query_one("SELECT COUNT(*) c FROM platforms")["c"]
        revenue = self.query_one(
            "SELECT COALESCE(SUM(amount_usdt),0) s FROM payments")["s"] or 0
        pay_count = self.query_one("SELECT COUNT(*) c FROM payments")["c"]
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
                "revenue_usdt": round(float(revenue), 2), "payments_count": pay_count,
                "recent_users": recent, "uploads_per_day": per_day}
