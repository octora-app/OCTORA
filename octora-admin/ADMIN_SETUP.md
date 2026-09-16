# ADMIN_SETUP.md — hosting the OCTORA admin panel for FREE

> Honest note first: **no legitimate provider offers "unlimited free"
> hosting.** But your load is tiny — one small ping every 6 hours per
> customer plus your occasional dashboard views — so a free tier is
> genuinely enough. When you have paying customers, upgrade (see bottom).

## Recommended path: Render (free web service) + Supabase (free Postgres)

Why this combo: Render free = 750 hours/month (one service runs ~720h, so it
fits), no credit card required for the free tier. We use Supabase Postgres
instead of SQLite because **free hosts wipe local files on redeploy** —
your user/license records must survive restarts. Supabase free = 500MB
(plenty for thousands of users), no credit card.

Known free-tier behaviour (verified, not marketing):
- The service **sleeps after ~15 minutes with no traffic**. The first visit
  or ping after sleep takes **~30–60 seconds to wake up**. This is normal.
  The app's telemetry **retries automatically** (immediate → +45s → +4min),
  so no heartbeat is lost — it just arrives late.
- Supabase free **pauses after 7 days of zero activity** — impossible once
  you have even one active customer (heartbeats every 6h keep it awake).

### Click-by-click

**A. Database (Supabase) — ~5 min**
1. Go to **supabase.com** → "Start your project" (free, sign up with GitHub).
2. **New project** → name `octora-admin` → set a database password (SAVE it
   somewhere) → region **Mumbai** (closest to India) → Create.
3. Wait ~2 minutes. Then **Project Settings (gear) → Database** →
   **Connection string → URI** → copy it. It looks like:
   `postgresql://postgres:[YOUR-PASSWORD]@db.xxxxx.supabase.co:5432/postgres`
   Replace `[YOUR-PASSWORD]` with the password from step 2.

**B. Code on GitHub — ~5 min**
1. **github.com** → New repository → name `octora-admin` → Private is fine →
   Create.
2. **Upload files**: "uploading an existing file" → drag in the entire
   contents of the `octora-admin` folder (server/, dashboard/, requirements.txt,
   render.yaml, …) → Commit.

**C. Web service (Render) — ~10 min**
1. **render.com** → Sign up with GitHub (free).
2. **New + → Web Service** → connect the `octora-admin` repo.
3. Settings: Name `octora-admin` · Region **Singapore** · Runtime **Python 3** ·
   Build command: `pip install -r requirements.txt` ·
   Start command: `uvicorn server.app:app --host 0.0.0.0 --port $PORT` ·
   Instance type **Free** → Create Web Service.
4. Once created: **Environment** → add variables:
   - `OCTORA_ADMIN_PASSWORD` = choose a strong password (you'll log in with this)
   - `DATABASE_URL` = the Supabase URI from step A
   - `OCTORA_SELLER_PEM` = paste your ENTIRE `seller_private.pem` file text
     (open it in Notepad, copy everything including BEGIN/END lines)
5. **Manual Deploy → Deploy latest commit**. Wait 3–5 minutes.
6. Open the URL Render gives you, e.g.
   `https://octora-admin-xxxx.onrender.com` → log in with your admin password.

**D. Point customer apps at it**
- In each OCTORA app: Settings → **Admin server URL** =
  `https://octora-admin-xxxx.onrender.com` (the follow-up integration pass
  adds this field; until then it is the config key `admin_server_url`).
- The app asks for telemetry consent on first run. After that you will see
  users appear in the dashboard within ~6 hours (or immediately after they
  connect a platform / finish an upload).

## Daily use
- **Dashboard**: Overview (users, licenses, channels, uploads today) · Users
  (search, per-user channels + subscriber counts + upload chart) · Licenses
  (issue / suspend / revoke / download key file) · Settings (server URL,
  change password).
- **Issuing a license**: Licenses → enter buyer name + email + their HWID
  (shown on their activation screen) → Issue → download the `.octalicense`
  file → send it to the buyer (Telegram/email).
- **Revoking**: Licenses → set status to `suspended`/`revoked` — the app's
  next online check (or heartbeat) will refuse it.

## When free is no longer enough (upgrade path)
- **Render Starter $7/month** (~₹600): no sleep, always instant. Change
  instance type, done — same database.
- **Or a VPS** (typically **₹200–500/month** — e.g. Hostinger/Contabo-type
  providers; prices change, check current): full control, no limits, run
  `uvicorn server.app:app --host 0.0.0.0 --port 8000` behind any reverse
  proxy. Keep Supabase or switch to local Postgres.
- The server code needs **zero changes** for either upgrade — only where it
  runs and the `DATABASE_URL`.

## Security notes
- Never share `OCTORA_SELLER_PEM` or the admin password.
- The dashboard login uses a hashed password + expiring sessions, but the
  free tier has no WAF — don't publish the URL publicly; share it only
  inside the app config.
- Back up: Supabase dashboard → Database → Backups (free tier: daily).
