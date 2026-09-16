"""OAuth2 installed-app flows using only the standard library (v1.1).

CUSTOMER MODEL (v1.1+): the SELLER registers a Google Cloud project ONCE and
bundles the credentials in octora/seller_config.json (see
core/seller_config.py). The end customer only clicks "Connect to YouTube /
Google Drive" and signs in with their OWN account in the system browser.
Their personal tokens are stored per-machine in the user config file — never
in the bundle.

Providers:
  Google — YouTube Data API (youtube.upload) + Drive (drive.file), offline tokens

OCTORA is YouTube-only: there are no other OAuth providers.
"""
import json
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import seller_config

# --------------------------------------------------------------------------
# generic local-redirect browser flow
# --------------------------------------------------------------------------

def _run_browser_flow(auth_url: str, token_url: str, auth_params: dict,
                      token_params: dict, token_method: str = "POST",
                      timeout: int = 180) -> dict | None:
    """Opens the system browser, captures the ?code= redirect on 127.0.0.1,
    exchanges it for tokens. Returns the token response dict, or a dict with
    an "error" key, or None on timeout."""
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q:
                result["code"] = q["code"][0]
                body = (b"<html><body style='background:#0d1117;color:#e6edf3;"
                        b"font-family:sans-serif;text-align:center;padding-top:60px'>"
                        b"<h2>&#9989; OCTORA connected.</h2>"
                        b"<p>You can close this tab and return to OCTORA.</p>"
                        b"</body></html>")
            else:
                result["error"] = q.get("error", ["cancelled"])[0]
                body = (b"<html><body style='background:#0d1117;color:#e6edf3;"
                        b"font-family:sans-serif;text-align:center;padding-top:60px'>"
                        b"<h2>Authorization did not complete.</h2>"
                        b"<p>You can close this tab and return to OCTORA.</p>"
                        b"</body></html>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    redirect = f"http://127.0.0.1:{port}/"
    params = dict(auth_params)
    params["redirect_uri"] = redirect
    url = auth_url + "?" + urllib.parse.urlencode(params)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline and "code" not in result and "error" not in result:
        time.sleep(0.3)
    server.shutdown()
    server.server_close()
    if "code" not in result:
        return {"error": result.get("error", "timeout")} if "error" in result else None
    tp = dict(token_params)
    tp["code"] = result["code"]
    tp["redirect_uri"] = redirect
    try:
        if token_method == "GET":
            turl = token_url + "?" + urllib.parse.urlencode(tp)
            req = urllib.request.Request(turl)
        else:
            data = urllib.parse.urlencode(tp).encode()
            req = urllib.request.Request(
                token_url, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except Exception as e:  # noqa: BLE001
        return {"error": f"token exchange failed: {e}"}


def _get_json(url: str, token: str | None = None, timeout: int = 30) -> dict | None:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except Exception:
        return None


# --------------------------------------------------------------------------
# Google (YouTube + Drive)
# --------------------------------------------------------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/drive.file",
]


def effective_google_creds(cfg) -> tuple[str, str] | None:
    """Which Google OAuth client to use.

    The CUSTOMER's own Google Cloud project client if they pasted their
    client id/secret on the Platforms screen (their uploads then count
    against THEIR project's 100 uploads/day quota), else the seller's
    bundled client (uploads count against the seller's shared quota).
    Quota is always billed to the project that owns the OAuth client —
    signing in with your own YouTube account alone does NOT move quota.
    """
    if cfg is not None:
        cid = str(cfg.get("google_client_id", "") or "").strip()
        csec = str(cfg.get("google_client_secret", "") or "").strip()
        if cid and csec:
            return cid, csec
    return seller_config.google()


def google_creds_source(cfg) -> str:
    """'user' if the customer uses their own Google API client, 'seller' if
    the seller's bundled client is used, '' if none is configured."""
    if cfg is not None:
        cid = str(cfg.get("google_client_id", "") or "").strip()
        csec = str(cfg.get("google_client_secret", "") or "").strip()
        if cid and csec:
            return "user"
    return "seller" if seller_config.google() else ""


def google_ready_for(cfg) -> bool:
    """True when EITHER the seller's or the customer's own Google client is
    configured — i.e. the Connect buttons can work."""
    return effective_google_creds(cfg) is not None


def google_connect(cfg=None, timeout: int = 240) -> tuple[dict | None, str]:
    """Runs the Google OAuth flow with the effective credentials.

    Returns (token_info, account_email). token_info is None on failure."""
    creds = effective_google_creds(cfg)
    if not creds:
        return None, "Google API client not configured yet."
    client_id, client_secret = creds
    tok = _run_browser_flow(
        GOOGLE_AUTH_URL, GOOGLE_TOKEN_URL,
        {"client_id": client_id, "response_type": "code",
         "scope": " ".join(GOOGLE_SCOPES),
         "access_type": "offline", "prompt": "consent"},
        {"client_id": client_id, "client_secret": client_secret,
         "grant_type": "authorization_code"},
        timeout=timeout)
    if not tok or not tok.get("access_token"):
        return None, tok.get("error", "cancelled") if tok else "cancelled"
    email = ""
    if tok.get("refresh_token"):
        info = _get_json("https://www.googleapis.com/oauth2/v3/userinfo",
                         tok["access_token"])
        if info:
            email = info.get("email", "")
    else:
        # Google only returns a refresh_token on first consent; without it we
        # cannot stay connected — ask the user to revoke & retry is overkill:
        # 'prompt=consent' above forces re-consent, so this is rare.
        return None, "Google did not return a refresh token — please try again."
    return {"refresh_token": tok["refresh_token"],
            "access_token": tok.get("access_token", "")}, email


def google_refresh_token(refresh_token: str, cfg=None) -> dict | None:
    creds = effective_google_creds(cfg)
    if not creds:
        return None
    client_id, client_secret = creds
    data = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def google_access_token(cfg) -> str | None:
    """Valid Google access token for the CUSTOMER's account (auto-refresh)."""
    rtok = cfg.get("google_refresh_token", "")
    if not rtok or not effective_google_creds(cfg):
        return None
    if cfg.get("google_access_token"):
        return cfg.get("google_access_token")
    tok = google_refresh_token(rtok, cfg)
    if tok and tok.get("access_token"):
        cfg.set("google_access_token", tok["access_token"])
        return tok["access_token"]
    return None
