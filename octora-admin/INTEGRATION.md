# INTEGRATION.md — wiring the v1.3 admin panel into the OCTORA app

> RULE: this is a **follow-up pass**. Do NOT restructure the app — apply the
> insertions below at the exact points named. New file
> `octora/core/telemetry.py` already exists (stdlib-only, fail-silent).

## 0. Config defaults — `octora/core/config.py`

Add to the defaults dict (next to the other keys):

```python
"telemetry_consent": False,          # master switch, set by first-run dialog
"admin_server_url": "",              # e.g. https://octora-admin-xxxx.onrender.com
"telemetry_last_validate": "",       # ISO ts of last successful server validation
"telemetry_last_validate_ok": "",    # "1"/"0"
"google_channel_name": "",           # cached at connect time (telemetry display)
"google_subscriber_count": 0,
```

## 1. App startup — `octora/main.py::main()`

After the licensing gate (`st = lm.status()` block) and **before**
`win.show()`, insert:

```python
    # ---- v1.3 admin-panel wiring ----
    from octora.core import telemetry
    from octora.ui.telemetry_consent import maybe_ask_consent  # new small dialog (see §6)
    maybe_ask_consent(cfg, win)          # first-run only; sets telemetry_consent
    ok, msg = telemetry.validate_online(cfg)
    log.info("license server check: %s", msg)
    if enabled := telemetry.enabled(cfg):
        telemetry.send_heartbeat(db, cfg, reason="startup")
        telemetry.start_background_loop(db, cfg)
```

Behaviour: `validate_online()` never raises and never blocks offline —
it falls back to the cached validation (3-day grace). The app must keep
working fully when the server is unreachable.

## 2. Online activation option — `octora/ui/activation.py`

In `ActivationDialog`, next to the "Load license file" button add
**"Activate online"**: prompts for the armored key text (emailed by seller),
then:

```python
from octora.core import telemetry
import hashlib, json, urllib.request
payload = {"license": armored_text,
           "hwid_hash": hashlib.sha256(hwid().encode()).hexdigest()}
req = urllib.request.Request(server_url + "/api/v1/license/activate", ...)
# on {"ok": true}: write armored text to license.octalicense via lm.activate()
```

Server refuses foreign HWIDs / revoked keys with a clear message — show it
in the dialog. (Manual file activation stays as fallback.)

## 3. Platform connect/disconnect — `octora/ui/screens/platforms.py`

At the end of `_connect(self, provider)` on success, and at the end of
`_disconnect(self, provider)`:

```python
from octora.core import telemetry
telemetry.notify_platform_change(self.app.db, self.app.cfg)
```

Also in `_connect("google")` success path, cache for telemetry display
(one extra API call, best-effort, wrapped in try/except):

```python
# after tokens are stored:
try:
    info = _get_json("https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true",
                     token=access_token, timeout=15) or {}
    item = (info.get("items") or [{}])[0]
    cfg.set("google_channel_name", item.get("snippet", {}).get("title", ""))
    cfg.set("google_subscriber_count", int(item.get("statistics", {}).get("subscriberCount", 0) or 0))
except Exception:
    pass
```

## 4. Upload completion — `octora/core/engine.py::PublishWorker._pump`

Right after the `db.add_upload_log(row["platform"], name, "posted", message)`
line (the success branch), insert:

```python
                try:
                    from .telemetry import notify_upload
                    notify_upload(db, cfg)
                except Exception:
                    pass
```

(`db` and `cfg` are already in scope in `_pump`.)

## 5. Settings screen — `octora/ui/screens/settings.py`

Add a **"Seller connection (optional)"** section:

- Checkbox `telemetry_consent` — "📡 Share anonymous usage stats with the
  seller (lets support see your connected channels & upload results).
  See PRIVACY.md." Toggling OFF immediately stops all sending.
- Text field `admin_server_url` — "Admin server URL (from your seller)".

Both bound to `cfg.set(...)` like the other settings.

## 6. First-run consent dialog — new file `octora/ui/telemetry_consent.py`

Small modal shown once (only if `telemetry_consent` is unset AND
`admin_server_url` is non-empty):

> "📡 Help & monitoring — May OCTORA send anonymous usage stats
> (app version, connected platforms, upload counts — never your videos or
> personal files) to the seller's server so support can help you faster?
> Full details: PRIVACY.md. [Allow] [Don't allow]"

`maybe_ask_consent(cfg, parent)` returns bool and persists the choice.

## 7. Checklist for the pass

- [ ] §0 config keys added
- [ ] §1 startup wiring (consent → validate → heartbeat → loop)
- [ ] §2 online activation button
- [ ] §3 platform change hooks + channel cache
- [ ] §4 upload hook
- [ ] §5 settings toggle + server URL field
- [ ] §6 consent dialog file
- [ ] Ship PRIVACY.md text inside the app (Help menu / activation screen link)
- [ ] Re-run: `python -m py_compile`, headless smoke test, verify no network
      call ever blocks startup (test with server URL pointed at 127.0.0.1:1)
