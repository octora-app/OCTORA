"""OCTORA admin panel: FastAPI backend + server-rendered dashboard."""
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Form, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import auth, config, license_ops
from .db import DB, utcnow


# ---------------------------------------------------------------- rate limit
# Simple in-memory sliding-window limiter (per client IP) for abuse-sensitive
# endpoints. Render runs a single worker by default; good enough at this scale.
_hits: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """Real client IP behind Render's reverse proxy. Trust the leftmost
    X-Forwarded-For entry (set by the proxy); fall back to the direct peer."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip() or "?"
    return request.client.host if request.client else "?"


def rate_limited(request: Request, key: str, per_minute: int) -> bool:
    now = time.time()
    ident = f"{key}:{_client_ip(request)}"
    dq = _hits[ident]
    while dq and dq[0] < now - 60:
        dq.popleft()
    # evict stale buckets so the table can't grow forever
    if not dq and len(_hits) > 4096:
        stale = [k for k, v in _hits.items() if not v or v[-1] < now - 60]
        for k in stale:
            del _hits[k]
    if len(dq) >= per_minute:
        return True
    dq.append(now)
    return False

BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "dashboard" / "templates"))

db = DB()
auth.ensure_admin(db)

app = FastAPI(title="OCTORA Admin", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE / "dashboard" / "static")), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp


# ---------------------------------------------------------------- CSRF
def csrf_token_for(request: Request) -> str:
    """CSRF token bound to the current admin session (empty when logged out)."""
    return auth.session_csrf_token(db, request.cookies.get("octora_admin_session"))


async def require_csrf(request: Request):
    """Dependency: reject admin POSTs whose CSRF token doesn't match."""
    form = await request.form()
    if not auth.csrf_valid(db, request.cookies.get("octora_admin_session"),
                            form.get("csrf_token", "")):
        raise HTTPException(403, "CSRF token invalid or expired — reload the page and retry.")


def page(request: Request, template: str, ctx: dict) -> HTMLResponse:
    """Render an admin page with the CSRF token injected for POST forms."""
    ctx = {"request": request, "csrf_token": csrf_token_for(request), **ctx}
    return templates.TemplateResponse(request, template, ctx)


# ---------------------------------------------------------------- public API
class PlatformBeat(BaseModel):
    platform: str = ""
    channel_id: str = ""
    channel_name: str = ""
    subscriber_count: int = 0


class Heartbeat(BaseModel):
    license_key_id: str = ""
    hwid_hash: str = Field(min_length=8, max_length=128)
    app_version: str = ""
    platforms: list[PlatformBeat] = []
    uploads_total: int = 0
    uploads_today: int = 0
    trial_started_at: str = ""  # local trial start (ISO); "" when no trial


@app.get("/health")
def health():
    return {"ok": True, "app": "octora-admin"}


@app.post("/api/v1/heartbeat")
def heartbeat(p: Heartbeat):
    uid = db.upsert_user(hwid_hash=p.hwid_hash.lower(), app_version=p.app_version,
                         license_key_id=p.license_key_id,
                         uploads_total=p.uploads_total, uploads_today=p.uploads_today)
    for pl in p.platforms:
        if pl.platform:
            db.upsert_platform(uid, pl.platform[:32], pl.channel_id[:128],
                               pl.channel_name[:128], max(0, pl.subscriber_count))
    db.add_heartbeat(uid, p.app_version, p.uploads_total, p.uploads_today)
    # Opportunistic trial registration: the server remembers each PC's first
    # trial so a wiped local config can't grab a fresh one later.
    trial_allowed = True
    if p.trial_started_at:
        trial_allowed, _ = db.trial_check(p.hwid_hash.lower(), p.trial_started_at)
    return {"ok": True, "trial_allowed": trial_allowed}


class TrialCheck(BaseModel):
    hwid_hash: str = Field(min_length=8, max_length=128)
    trial_started_at: str = ""  # "" = "may I start a trial?"; iso = "my trial started at"


@app.post("/api/v1/trial/check")
def trial_check(p: TrialCheck, request: Request):
    """One-trial-per-PC gate. Called by the app when starting a trial and by
    the background sync on every launch."""
    if rate_limited(request, "trial_check", config.RATE_LIMIT_TRIAL_CHECK):
        raise HTTPException(429, "Too many attempts — try again in a minute.")
    allowed, recorded = db.trial_check(p.hwid_hash.lower(), p.trial_started_at)
    return {"allowed": allowed, "trial_started_at": recorded}


class ActivateReq(BaseModel):
    license: str = Field(min_length=50)
    hwid_hash: str = Field(min_length=8, max_length=128)


@app.post("/api/v1/license/activate")
def license_activate(req: ActivateReq, request: Request):
    if rate_limited(request, "activate", config.RATE_LIMIT_ACTIVATE):
        raise HTTPException(429, "Too many attempts — try again in a minute.")
    try:
        env = license_ops.parse_armored(req.license)
        payload = license_ops.verify_envelope(env)
    except Exception as e:
        raise HTTPException(400, f"Invalid license: {e}")
    key_id = license_ops.key_id_of(req.license)
    lic = db.get_license(key_id)
    if not lic:
        raise HTTPException(404, "License not issued by this server.")
    if lic["status"] != "active":
        raise HTTPException(403, f"License is {lic['status']}. Contact support.")
    if lic["expires_at"] < utcnow():
        raise HTTPException(403, "License expired. Please renew.")
    hh = req.hwid_hash.lower()
    expected = (lic["hwid_bound"] or license_ops.hwid_hash_of(payload.get("hwid") or ""))
    if not expected or expected != hh:
        raise HTTPException(403, "This license is bound to ANOTHER machine.")
    if not lic["hwid_bound"] and payload.get("hwid"):
        # First bind: re-check under a write lock so two machines racing to
        # activate the same unbound license can't both succeed.
        with db.transaction():
            fresh = db.get_license(key_id, for_update=True)
            if fresh and not fresh["hwid_bound"]:
                db.bind_license(key_id, hh)
    uid = db.upsert_user(hwid_hash=hh, license_key_id=key_id)
    return {"ok": True, "name": lic["name"], "expires_at": lic["expires_at"],
            "message": f"Activated for {lic['name']}."}


class ValidateReq(BaseModel):
    key_id: str = Field(min_length=16, max_length=128)
    hwid_hash: str = Field(min_length=8, max_length=128)


@app.post("/api/v1/license/validate")
def license_validate(req: ValidateReq):
    lic = db.get_license(req.key_id)
    if not lic:
        return {"valid": False, "message": "Unknown license."}
    if lic["status"] != "active":
        return {"valid": False, "message": f"License is {lic['status']}."}
    if lic["expires_at"] < utcnow():
        return {"valid": False, "expires_at": lic["expires_at"],
                "message": "License expired."}
    if lic["hwid_bound"] and lic["hwid_bound"] != req.hwid_hash.lower():
        return {"valid": False, "message": "License bound to another machine."}
    return {"valid": True, "expires_at": lic["expires_at"], "name": lic["name"]}


# ---------------------------------------------------------------- payments
@app.get("/api/v1/plans")
def plans():
    """Public: subscription plans + the USDT (TRC-20) address to pay to."""
    return {"currency": "USDT", "network": "TRC-20",
            "seller_address": config.SELLER_USDT_TRC20,
            "plans": [{"id": pid, **p} for pid, p in config.PLANS.items()]}


class PayVerifyReq(BaseModel):
    txid: str = Field(min_length=64, max_length=64)
    plan: str = Field(min_length=3, max_length=16)
    hwid: str = Field(min_length=8, max_length=128)  # raw HWID hex from the app
    name: str = ""
    email: str = ""


@app.post("/api/v1/pay/verify")
def pay_verify(req: PayVerifyReq, request: Request):
    """Verify an on-chain USDT (TRC-20) payment, then auto-issue the license.

    Flow: customer pays -> pastes TXID in the app -> we confirm the transfer
    on the Tron blockchain (existence, SUCCESS receipt, finality age, exact
    seller address, exact plan amount) -> mint an HWID-bound license -> return
    it so the app activates immediately. Each TXID can be used exactly once.

    If this machine already holds an active license, the new plan EXTENDS it
    instead of minting a second overlapping license — and the client receives
    a FRESH signed envelope carrying the extended expiry (the old envelope
    would make the app expire at the old date).

    Atomicity: the on-chain check happens first WITHOUT holding any lock
    (it is slow network I/O). Everything after that — duplicate-TXID check,
    license extend/issue, envelope rotation, payment recording — runs inside
    ONE database transaction with a per-HWID serialization lock, so two
    simultaneous requests can neither spend one TXID twice nor record a
    payment without its matching license/envelope.
    """
    if rate_limited(request, "pay_verify", config.RATE_LIMIT_PAY_VERIFY):
        raise HTTPException(429, "Too many attempts — try again in a minute.")
    from . import tron
    plan = config.PLANS.get(req.plan.strip().lower())
    if not plan:
        raise HTTPException(400, "Unknown plan.")
    txid = req.txid.strip().lower()
    if db.get_payment(txid):
        raise HTTPException(409, "This transaction was already used for a license.")
    if not license_ops.seller_configured():
        raise HTTPException(503, "Seller key not configured on the server.")
    try:
        pay = tron.find_usdt_payment(txid, plan["price_usdt"])
    except ValueError as e:
        raise HTTPException(402, str(e))
    hwid_clean = req.hwid.strip().lower()
    name = req.name.strip() or "OCTORA user"
    email = req.email.strip()
    hh = license_ops.hwid_hash_of(hwid_clean)

    try:
        with db.transaction():
            # Serialize concurrent payment attempts for this machine.
            db.serialize_key("pay:" + hh)
            # Double-check inside the lock: the TXID may have landed while
            # we were verifying on-chain or waiting for the lock.
            if db.get_payment(txid):
                raise HTTPException(409, "This transaction was already used for a license.")
            existing = db.get_active_license_by_hwid(hh)
            if existing:
                return _renew_license(req, plan, txid, pay, hwid_clean, hh,
                                      name, email, existing)
            return _issue_new_license(req, plan, txid, pay, hwid_clean, hh,
                                      name, email)
    except HTTPException:
        raise
    except Exception as e:
        # A concurrent request won the race and inserted first: the PRIMARY
        # KEY on payments.txid makes the loser fail here.
        if DB.is_unique_violation(e):
            raise HTTPException(409, "This transaction was already used for a license.")
        raise


def _renew_license(req, plan, txid, pay, hwid_clean, hh, name, email, existing):
    """Extend an existing license: fresh envelope, rotated atomically."""
    lic, new_exp = db.extend_license_expiry(existing["key_id"], plan["days"])
    if not lic:
        raise HTTPException(404, "License not found.")
    # Fresh signed envelope carrying the EXACT extended expiry from the DB.
    try:
        new_armored = license_ops.issue_armored(name, email, hwid_clean,
                                                expires=new_exp[:10])
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    new_key_id = license_ops.key_id_of(new_armored)
    db.rotate_license_envelope(existing["key_id"], new_key_id, new_armored)
    db.execute("UPDATE licenses SET hwid_raw=? WHERE key_id=?", (hwid_clean, new_key_id))
    db.record_payment(txid, req.plan, pay["amount_usdt"], hh, name, email,
                      pay["from_address"])
    db.upsert_user(hwid_hash=hh, license_key_id=new_key_id)
    db.audit("customer:auto", "renew", new_key_id[:16],
             f"plan={req.plan} txid={txid[:16]}… +{plan['days']}d -> {new_exp[:10]}")
    return {"ok": True, "plan": req.plan, "plan_name": plan["name"],
            "armored": new_armored, "key_id": new_key_id,
            "amount_usdt": pay["amount_usdt"], "extended": True,
            "expires_at": new_exp,
            "message": (f"Payment verified ({pay['amount_usdt']} USDT). "
                        f"Your existing license was extended by {plan['days']} days.")}


def _issue_new_license(req, plan, txid, pay, hwid_clean, hh, name, email):
    """Issue a brand-new license: envelope + row + payment, all or nothing."""
    try:
        armored = license_ops.issue_armored(name, email, hwid_clean, plan["days"])
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    key_id = license_ops.key_id_of(armored)
    expires_at = (now + timedelta(days=plan["days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.issue_license(key_id, name, email, hh,
                     now.strftime("%Y-%m-%dT%H:%M:%SZ"), expires_at,
                     plan["days"], armored,
                     f"plan={req.plan} txid={txid[:16]}… amount={pay['amount_usdt']} USDT",
                     hwid_raw=hwid_clean)
    db.record_payment(txid, req.plan, pay["amount_usdt"], hh, name, email,
                      pay["from_address"])
    db.upsert_user(hwid_hash=hh, license_key_id=key_id)
    db.audit("customer:auto", "issue", key_id[:16],
             f"plan={req.plan} txid={txid[:16]}… amount={pay['amount_usdt']} USDT")
    return {"ok": True, "plan": req.plan, "plan_name": plan["name"],
            "armored": armored, "key_id": key_id, "expires_at": expires_at,
            "amount_usdt": pay["amount_usdt"],
            "message": f"Payment verified ({pay['amount_usdt']} USDT). License issued!"}


# ---------------------------------------------------------------- HWID rebind
class RebindReq(BaseModel):
    license: str = Field(min_length=50)   # current armored license file
    hwid: str = Field(min_length=8, max_length=128)  # raw HWID of the NEW machine


@app.post("/api/v1/license/rebind-request")
def rebind_request(req: RebindReq, request: Request):
    """Customer asks to move their license to a new machine.

    The request is stored as pending; nothing changes until the seller
    approves it in the admin panel, at which point a FRESH signed envelope
    for the new HWID is minted. At most one approved rebind per license per
    REBIND_COOLDOWN_DAYS (default 30), and one pending request at a time.
    """
    if rate_limited(request, "rebind", config.RATE_LIMIT_REBIND):
        raise HTTPException(429, "Too many attempts — try again in a minute.")
    try:
        env = license_ops.parse_armored(req.license)
        license_ops.verify_envelope(env)
    except Exception as e:
        raise HTTPException(400, f"Invalid license: {e}")
    key_id = license_ops.key_id_of(req.license)
    lic = db.get_license(key_id)
    if not lic:
        raise HTTPException(404, "License not issued by this server.")
    if lic["status"] != "active":
        raise HTTPException(403, f"License is {lic['status']}. Contact support.")
    new_hwid_clean = req.hwid.strip().lower()
    new_hh = license_ops.hwid_hash_of(new_hwid_clean)
    if lic["hwid_bound"] and new_hh == lic["hwid_bound"]:
        raise HTTPException(400, "This license is already bound to that machine.")
    rid, outcome = db.create_rebind_request(key_id, lic["hwid_bound"] or "",
                                            new_hwid_clean, new_hh)
    if outcome == "exists":
        raise HTTPException(409, "A rebind request for this license is already pending.")
    if outcome == "cooldown":
        raise HTTPException(403, "Rebind cooldown: only one approved rebind per "
                                 f"{config.REBIND_COOLDOWN_DAYS} days per license.")
    db.audit("customer", "rebind_request", key_id[:16],
             f"request_id={rid} old_hwid={ (lic['hwid_bound'] or '')[:12]}… "
             f"new_hwid={new_hh[:12]}…")
    return {"ok": True, "request_id": rid,
            "message": "Rebind requested. The seller will review it; your app can "
                       "pick up the new license automatically once approved."}


class RebindStatusReq(BaseModel):
    license: str = Field(min_length=50)   # current (possibly old) armored license


@app.post("/api/v1/license/rebind-status")
def rebind_status(req: RebindStatusReq):
    """Poll the latest rebind request. When approved, returns the NEW envelope."""
    try:
        env = license_ops.parse_armored(req.license)
        license_ops.verify_envelope(env)
    except Exception as e:
        raise HTTPException(400, f"Invalid license: {e}")
    key_id = license_ops.key_id_of(req.license)
    r = db.latest_rebind_request(key_id)
    if not r:
        return {"status": "none"}
    if r["status"] == "approved" and r["new_key_id"]:
        lic = db.get_license(r["new_key_id"])
        if lic:
            return {"status": "approved", "armored": lic["armored"],
                    "key_id": lic["key_id"], "expires_at": lic["expires_at"]}
    return {"status": r["status"]}


# ---------------------------------------------------------------- updates
@app.get("/api/v1/updates/latest")
def updates_latest():
    """Auto-update manifest polled by the desktop app on startup."""
    return config.UPDATE_MANIFEST


# ---------------------------------------------------------------- admin auth
def admin_or_redirect(request: Request):
    admin = auth.session_admin(db, request.cookies.get("octora_admin_session"))
    if not admin:
        raise HTTPException(307, headers={"Location": "/login"})
    return admin


def admin_or_401(request: Request):
    admin = auth.session_admin(db, request.cookies.get("octora_admin_session"))
    if not admin:
        raise HTTPException(401, "Login required")
    return admin


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if auth.session_admin(db, request.cookies.get("octora_admin_session")):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": ""})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form("")):
    ip = _client_ip(request)
    allowed, retry_in = auth.login_allowed(ip)
    if not allowed:
        return templates.TemplateResponse(
            request, "login.html",
            {"request": request,
             "error": f"Too many failed attempts — try again in {retry_in // 60 + 1} min."},
            status_code=429)
    if auth.verify_login(db, password):
        auth.clear_login_failures(ip)
        admin = db.get_admin("admin")
        token, _csrf = auth.create_session(db, admin["id"])
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie("octora_admin_session", token, httponly=True, samesite="lax",
                        max_age=config.SESSION_HOURS * 3600, path="/",
                        secure=(request.url.scheme == "https"))
        return resp
    auth.record_login_failure(ip)
    return templates.TemplateResponse(request, "login.html", {"request": request,
                                                     "error": "Wrong password."})


@app.get("/logout")
def logout(request: Request):
    auth.destroy_session(db, request.cookies.get("octora_admin_session"))
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("octora_admin_session")
    return resp


# ---------------------------------------------------------------- dashboard
@app.get("/", response_class=HTMLResponse)
def overview_page(request: Request, admin=Depends(admin_or_redirect)):
    ov = db.overview()
    return templates.TemplateResponse(request, "overview.html",
                                      {"request": request, "ov": ov,
                                       "seller_ok": license_ops.seller_configured()})


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, q: str = "", admin=Depends(admin_or_redirect)):
    users = db.list_users(search=q)
    return page(request, "users.html", {"users": users, "q": q})


@app.get("/users/{uid}", response_class=HTMLResponse)
def user_detail_page(request: Request, uid: int, admin=Depends(admin_or_redirect)):
    u = db.get_user(uid)
    if not u:
        raise HTTPException(404, "User not found")
    plats = db.user_platforms(uid)
    hist = db.heartbeat_history(uid, 60)
    hist.reverse()
    return page(request, "user_detail.html",
                {"u": u, "plats": plats, "hist": hist})


@app.get("/licenses", response_class=HTMLResponse)
def licenses_page(request: Request, q: str = "", admin=Depends(admin_or_redirect)):
    lics = db.list_licenses(search=q)
    rebinds = db.list_rebind_requests("pending")
    return page(request, "licenses.html",
                {"lics": lics, "q": q, "rebinds": rebinds,
                 "seller_ok": license_ops.seller_configured(),
                 "issued": request.query_params.get("issued", ""),
                 "error": request.query_params.get("error", "")})


@app.post("/licenses/issue")
def issue_license(request: Request, name: str = Form(""), email: str = Form(""),
                  hwid: str = Form(""), days: int = Form(365),
                  notes: str = Form(""), admin=Depends(admin_or_redirect),
                  csrf=Depends(require_csrf)):
    if not name.strip() or not hwid.strip():
        return RedirectResponse("/licenses?error=" + "Name+and+HWID+required", status_code=302)
    try:
        armored = license_ops.issue_armored(name.strip(), email.strip(), hwid, max(1, days))
    except RuntimeError as e:
        return RedirectResponse("/licenses?error=" + str(e).replace(" ", "+")[:120],
                                status_code=302)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    key_id = license_ops.key_id_of(armored)
    db.issue_license(key_id, name.strip(), email.strip(),
                     license_ops.hwid_hash_of(hwid), now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     (now + timedelta(days=max(1, days))).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     max(1, days), armored, notes.strip(),
                     hwid_raw=hwid.strip().lower())
    db.audit(admin["username"], "issue", key_id[:16],
             f"name={name.strip()} days={max(1, days)}")
    return RedirectResponse(f"/licenses?issued={key_id}", status_code=302)


@app.post("/licenses/{key_id}/status")
def license_status(request: Request, key_id: str, to: str = Form(""),
                   admin=Depends(admin_or_redirect), csrf=Depends(require_csrf)):
    if to in ("active", "revoked", "suspended"):
        db.set_license_status(key_id, to)
        db.audit(admin["username"], to, key_id[:16], "")
    return RedirectResponse("/licenses", status_code=302)


@app.post("/licenses/{key_id}/extend")
def license_extend(request: Request, key_id: str, days: int = Form(30),
                   admin=Depends(admin_or_redirect), csrf=Depends(require_csrf)):
    """Extend a license AND hand the seller a fresh envelope.

    Extending only the DB row would leave the customer's signed envelope
    with the old expiry, so the app would keep expiring at the old date.
    The fresh envelope is minted here and the Licenses page offers it for
    download — send the new .octalicense file to the buyer.
    """
    days = max(1, min(days, 36500))
    try:
        with db.transaction():
            lic, new_exp = db.extend_license_expiry(key_id, days)
            if not lic:
                raise ValueError("not found")
            raw_hwid = (lic.get("hwid_raw") or "").strip()
            if not raw_hwid:
                raise ValueError("HWID unknown for this license (issued before "
                                 "envelope rotation) — ask the buyer for their HWID "
                                 "and issue a new license instead.")
            new_armored = license_ops.issue_armored(lic["name"], lic["email"],
                                                    raw_hwid, expires=new_exp[:10])
            new_key_id = license_ops.key_id_of(new_armored)
            db.rotate_license_envelope(key_id, new_key_id, new_armored)
            db.audit(admin["username"], "extend", new_key_id[:16],
                     f"+{days}d -> {new_exp[:10]} (was key {key_id[:16]}…)")
    except ValueError as e:
        return RedirectResponse("/licenses?error=" + str(e).replace(" ", "+")[:150],
                                status_code=302)
    except RuntimeError as e:
        return RedirectResponse("/licenses?error=" + str(e).replace(" ", "+")[:120],
                                status_code=302)
    return RedirectResponse(f"/licenses?issued={new_key_id}", status_code=302)


@app.post("/licenses/{key_id}/reset-hwid")
def license_reset_hwid(request: Request, key_id: str,
                       admin=Depends(admin_or_redirect), csrf=Depends(require_csrf)):
    # DISABLED: clearing hwid_bound in the DB never worked, because the
    # signed envelope still contained the original HWID. Use the Rebind
    # flow below, which mints a fresh envelope for the new machine.
    db.audit(admin["username"], "reset_hwid_blocked", key_id[:16],
             "legacy reset-hwid attempted (disabled)")
    return RedirectResponse("/licenses?error=" + "Reset+HWID+is+disabled.+Use+the+"
                            "Rebind+flow:+the+customer+requests+it+from+the+app,"
                            "+you+approve+below+and+a+fresh+license+is+minted.",
                            status_code=302)


@app.post("/licenses/rebind/{req_id}/approve")
def rebind_approve(request: Request, req_id: int,
                   admin=Depends(admin_or_redirect), csrf=Depends(require_csrf)):
    """Approve a pending HWID rebind: mint a FRESH envelope for the new
    machine (same expiry), rotate the license row to it, and record the
    decision. The customer app picks the new file up via rebind-status,
    or the seller can download + send it from the Licenses page."""
    try:
        with db.transaction():
            r = db.get_rebind_request(req_id, for_update=True)
            if not r or r["status"] != "pending":
                raise ValueError("request is no longer pending")
            lic = db.get_license(r["key_id"])
            if not lic:
                raise ValueError("license not found")
            if lic["status"] != "active":
                raise ValueError(f"license is {lic['status']}")
            new_armored = license_ops.issue_armored(
                lic["name"], lic["email"], r["new_hwid"],
                expires=lic["expires_at"][:10])  # rebind keeps the same expiry
            new_key_id = license_ops.key_id_of(new_armored)
            db.rotate_license_envelope(lic["key_id"], new_key_id, new_armored)
            db.execute("UPDATE licenses SET hwid_bound=?, hwid_raw=? WHERE key_id=?",
                       (r["new_hwid_hash"], r["new_hwid"], new_key_id))
            outcome = db.decide_rebind(req_id, True, admin["username"],
                                       new_key_id=new_key_id)
            if outcome == "cooldown":
                raise ValueError("rebind cooldown: one approved rebind per "
                                 f"{config.REBIND_COOLDOWN_DAYS} days")
            if outcome != "approved":
                raise ValueError("could not approve request")
            db.audit(admin["username"], "rebind_approve", new_key_id[:16],
                     f"request={req_id} {(r['old_hwid_hash'] or '')[:12]}… -> "
                     f"{r['new_hwid_hash'][:12]}… (was key {lic['key_id'][:16]}…)")
    except ValueError as e:
        return RedirectResponse("/licenses?error=" + str(e).replace(" ", "+")[:150],
                                status_code=302)
    except RuntimeError as e:
        return RedirectResponse("/licenses?error=" + str(e).replace(" ", "+")[:120],
                                status_code=302)
    return RedirectResponse(f"/licenses?issued={new_key_id}", status_code=302)


@app.post("/licenses/rebind/{req_id}/reject")
def rebind_reject(request: Request, req_id: int, notes: str = Form(""),
                  admin=Depends(admin_or_redirect), csrf=Depends(require_csrf)):
    with db.transaction():
        outcome = db.decide_rebind(req_id, False, admin["username"], notes=notes.strip())
        if outcome:
            db.audit(admin["username"], "rebind_reject", f"request={req_id}",
                     notes.strip()[:200])
    return RedirectResponse("/licenses", status_code=302)


@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, admin=Depends(admin_or_redirect)):
    return page(request, "audit.html", {"entries": db.list_audit()})


@app.get("/payments", response_class=HTMLResponse)
def payments_page(request: Request, admin=Depends(admin_or_redirect)):
    payments = db.list_payments()
    total = round(sum(p["amount_usdt"] or 0 for p in payments), 2)
    return page(request, "payments.html",
                {"payments": payments, "total_usdt": total,
                 "seller_address": config.SELLER_USDT_TRC20})


@app.get("/licenses/{key_id}/download")
def license_download(key_id: str, request: Request, admin=Depends(admin_or_401)):
    lic = db.get_license(key_id)
    if not lic:
        raise HTTPException(404, "Not found")
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(lic["armored"], media_type="text/plain",
                             headers={"Content-Disposition":
                                      f"attachment; filename={key_id[:12]}.octalicense"})


@app.post("/users/{uid}/status")
def user_status(request: Request, uid: int, to: str = Form(""),
                admin=Depends(admin_or_redirect), csrf=Depends(require_csrf)):
    if to in ("active", "trial", "suspended"):
        db.set_user_status(uid, to)
        db.audit(admin["username"], f"user_{to}", f"user_id={uid}", "")
    return RedirectResponse(f"/users/{uid}", status_code=302)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, admin=Depends(admin_or_redirect)):
    return page(request, "settings.html",
                {"seller_ok": license_ops.seller_configured(),
                 "db_url": ("Postgres" if db.pg else "SQLite"),
                 "msg": request.query_params.get("msg", "")})


@app.post("/settings/password")
def change_password(request: Request, new_password: str = Form(""),
                    admin=Depends(admin_or_redirect), csrf=Depends(require_csrf)):
    if len(new_password) < 8:
        return RedirectResponse("/settings?msg=too+short+(min+8)", status_code=302)
    import hashlib, secrets
    salt = secrets.token_bytes(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", new_password.encode(), salt, 200_000).hex()
    db.update_admin_pw(admin["id"], pw_hash, salt.hex())
    # All sessions (including this one) die with the old password.
    db.delete_sessions_for_admin(admin["id"])
    db.audit(admin["username"], "password_change", "admin", "all sessions revoked")
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("octora_admin_session", path="/")
    return resp


# ---------------------------------------------------------------- admin JSON
@app.get("/api/admin/overview")
def api_overview(request: Request, admin=Depends(admin_or_401)):
    return db.overview()


@app.get("/api/admin/users")
def api_users(request: Request, q: str = "", admin=Depends(admin_or_401)):
    return {"users": db.list_users(search=q)}


@app.get("/api/admin/payments")
def api_payments(request: Request, admin=Depends(admin_or_401)):
    return {"payments": db.list_payments(),
            "seller_address": config.SELLER_USDT_TRC20}
