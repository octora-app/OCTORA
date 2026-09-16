# 🐙 OCTORA Admin Panel (v1.3)

Private seller control panel for OCTORA — see **all customers** in one place:
who they are, which license they hold, which YouTube/Instagram/TikTok
channels they connected, subscriber counts, upload results, last-active —
plus **online license activation** to replace manual key files.

## Structure

```
octora-admin/
├── server/
│   ├── app.py          # FastAPI: public API + admin API + dashboard pages
│   ├── config.py       # env config (DATABASE_URL, admin password, seller key)
│   ├── db.py           # SQLite/Postgres-compatible storage
│   ├── auth.py         # pbkdf2 admin password + token sessions
│   └── license_ops.py  # RSA sign/verify (same envelope scheme as the app)
├── dashboard/
│   ├── templates/      # login, overview, users, user detail, licenses, settings
│   └── static/style.css
├── render.yaml         # one-click Render deploy blueprint
├── requirements.txt
├── ADMIN_SETUP.md      # free hosting, click-by-click (START HERE for deploy)
├── PRIVACY.md          # user-facing telemetry disclosure (ship in the app)
└── INTEGRATION.md      # exact wiring points for the app-side follow-up pass
```

Customer-side telemetry client: `../OCTORA-v1.1/octora/core/telemetry.py`
(new file — stdlib only, consent-gated, fail-silent, cold-start resilient).

## Run locally

```bash
cd octora-admin
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export OCTORA_ADMIN_PASSWORD="choose-a-strong-password"
export OCTORA_SELLER_KEY="/path/to/seller_private.pem"   # or OCTORA_SELLER_PEM="<pem text>"
.venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000  → log in
```

First boot creates the admin account from `OCTORA_ADMIN_PASSWORD`.
SQLite file `octora_admin.db` is created automatically; set `DATABASE_URL`
to a Postgres URL for hosted deploys.

## API (customer app → server)

- `POST /api/v1/heartbeat` — `{license_key_id, hwid_hash, app_version,
  platforms:[{platform, channel_id, channel_name, subscriber_count}],
  uploads_total, uploads_today, timestamp}` → upserts the user record.
- `POST /api/v1/license/activate` — `{license, hwid_hash}` → verifies RSA
  signature, binds HWID on first activation, refuses foreign HWIDs and
  revoked/expired keys.
- `POST /api/v1/license/validate` — `{key_id, hwid_hash}` → lightweight
  startup check (app caches last-good result for offline grace).

Admin pages & JSON under `/` and `/api/admin/*` require login (cookie session).
