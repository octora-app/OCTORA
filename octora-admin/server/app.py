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


def rate_limited(request: Request, key: str, per_minute: int) -> bool:
    now = time.time()
    ident = f"{key}:{(request.client.host if request.client else '?')}"
    dq = _hits[ident]
    while dq and dq[0] < now - 60:
        dq.popleft()
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
    return {"ok": True}


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
    expected = (lic["hwid_bound"] or license_ops.hwid_hash_of(payload.get("hwid", "")))
    if not expected or expected != hh:
        raise HTTPException(403, "This license is bound to ANOTHER machine.")
    if not lic["hwid_bound"] and payload.get("hwid"):
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
    instead of minting a second overlapping license.
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

    # --- same PC already licensed? extend it instead of double-issuing ---
    existing = db.get_active_license_by_hwid(hh)
    if existing:
        new_exp = db.extend_license(existing["key_id"], plan["days"])
        db.record_payment(txid, req.plan, pay["amount_usdt"], hh, name, email,
                          pay["from_address"])
        db.upsert_user(hwid_hash=hh, license_key_id=existing["key_id"])
        return {"ok": True, "plan": req.plan, "plan_name": plan["name"],
                "armored": existing["armored"], "key_id": existing["key_id"],
                "amount_usdt": pay["amount_usdt"], "extended": True,
                "expires_at": new_exp,
                "message": (f"Payment verified ({pay['amount_usdt']} USDT). "
                            f"Your existing license was extended by {plan['days']} days.")}

    try:
        armored = license_ops.issue_armored(name, email, hwid_clean, plan["days"])
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    key_id = license_ops.key_id_of(armored)
    db.issue_license(key_id, name, email, hh,
                     now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     (now + timedelta(days=plan["days"])).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     plan["days"], armored,
                     f"plan={req.plan} txid={txid[:16]}… amount={pay['amount_usdt']} USDT")
    db.record_payment(txid, req.plan, pay["amount_usdt"], hh, name, email,
                      pay["from_address"])
    db.upsert_user(hwid_hash=hh, license_key_id=key_id)
    return {"ok": True, "plan": req.plan, "plan_name": plan["name"],
            "armored": armored, "key_id": key_id,
            "amount_usdt": pay["amount_usdt"],
            "message": f"Payment verified ({pay['amount_usdt']} USDT). License issued!"}


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
    if auth.verify_login(db, password):
        admin = db.get_admin("admin")
        token = auth.create_session(db, admin["id"])
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie("octora_admin_session", token, httponly=True, samesite="lax",
                        max_age=config.SESSION_HOURS * 3600)
        return resp
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
    return templates.TemplateResponse(request, "users.html",
                                      {"request": request, "users": users, "q": q})


@app.get("/users/{uid}", response_class=HTMLResponse)
def user_detail_page(request: Request, uid: int, admin=Depends(admin_or_redirect)):
    u = db.get_user(uid)
    if not u:
        raise HTTPException(404, "User not found")
    plats = db.user_platforms(uid)
    hist = db.heartbeat_history(uid, 60)
    hist.reverse()
    return templates.TemplateResponse(request, "user_detail.html",
                                      {"request": request, "u": u, "plats": plats,
                                       "hist": hist})


@app.get("/licenses", response_class=HTMLResponse)
def licenses_page(request: Request, q: str = "", admin=Depends(admin_or_redirect)):
    lics = db.list_licenses(search=q)
    return templates.TemplateResponse(request, "licenses.html",
                                      {"request": request, "lics": lics, "q": q,
                                       "seller_ok": license_ops.seller_configured(),
                                       "issued": request.query_params.get("issued", ""),
                                       "error": request.query_params.get("error", "")})


@app.post("/licenses/issue")
def issue_license(request: Request, name: str = Form(""), email: str = Form(""),
                  hwid: str = Form(""), days: int = Form(365),
                  notes: str = Form(""), admin=Depends(admin_or_redirect)):
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
                     max(1, days), armored, notes.strip())
    return RedirectResponse(f"/licenses?issued={key_id}", status_code=302)


@app.post("/licenses/{key_id}/status")
def license_status(request: Request, key_id: str, to: str = Form(""),
                   admin=Depends(admin_or_redirect)):
    if to in ("active", "revoked", "suspended"):
        db.set_license_status(key_id, to)
    return RedirectResponse("/licenses", status_code=302)


@app.post("/licenses/{key_id}/extend")
def license_extend(request: Request, key_id: str, days: int = Form(30),
                   admin=Depends(admin_or_redirect)):
    new_exp = db.extend_license(key_id, max(1, min(days, 36500)))
    if not new_exp:
        return RedirectResponse("/licenses?error=license+not+found", status_code=302)
    return RedirectResponse(f"/licenses?issued={key_id}", status_code=302)


@app.post("/licenses/{key_id}/reset-hwid")
def license_reset_hwid(request: Request, key_id: str,
                       admin=Depends(admin_or_redirect)):
    db.reset_license_hwid(key_id)
    return RedirectResponse("/licenses", status_code=302)


@app.get("/payments", response_class=HTMLResponse)
def payments_page(request: Request, admin=Depends(admin_or_redirect)):
    payments = db.list_payments()
    total = round(sum(p["amount_usdt"] or 0 for p in payments), 2)
    return templates.TemplateResponse(request, "payments.html",
                                      {"request": request, "payments": payments,
                                       "total_usdt": total,
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
                admin=Depends(admin_or_redirect)):
    if to in ("active", "trial", "suspended"):
        db.set_user_status(uid, to)
    return RedirectResponse(f"/users/{uid}", status_code=302)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, admin=Depends(admin_or_redirect)):
    return templates.TemplateResponse(request, "settings.html",
                                      {"request": request,
                                       "seller_ok": license_ops.seller_configured(),
                                       "db_url": ("Postgres" if db.pg else "SQLite"),
                                       "msg": request.query_params.get("msg", "")})


@app.post("/settings/password")
def change_password(request: Request, new_password: str = Form(""),
                    admin=Depends(admin_or_redirect)):
    if len(new_password) < 8:
        return RedirectResponse("/settings?msg=too+short+(min+8)", status_code=302)
    import hashlib, secrets
    salt = secrets.token_bytes(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", new_password.encode(), salt, 200_000).hex()
    db.update_admin_pw(admin["id"], pw_hash, salt.hex())
    return RedirectResponse("/settings?msg=password+updated", status_code=302)


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
