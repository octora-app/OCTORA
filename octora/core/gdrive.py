"""Google Drive uploads with urllib only (no google API client needed).

Real code path: resumable upload session -> PUT file bytes -> returns file id.
In demo mode the caller simulates instead; this module is only used in live mode.

v1.2: zero-setup folders — ensure_octora_folder() creates the "OCTORA" root
folder on first connect (cached in config), and ensure_campaign_folder()
creates per-campaign subfolders. Uploads always land inside them.
"""
import json
import mimetypes
import os
import urllib.request

from . import oauth

DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
DRIVE_API = "https://www.googleapis.com/drive/v3/files"
ROOT_FOLDER_NAME = "OCTORA"


def _api(token: str, method: str, path: str = "", payload: dict | None = None,
         params: dict | None = None, timeout: int = 30) -> dict:
    """Small Drive v3 JSON helper. Raises RuntimeError on HTTP errors."""
    import urllib.error
    import urllib.parse
    url = DRIVE_API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Drive API {method} {path or '/'} HTTP {e.code}: "
                           f"{e.read()[:200].decode(errors='replace')}")


def _valid_token(cfg) -> str | None:
    return oauth.google_access_token(cfg)


def folder_link(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else ""


def _find_folder(cfg, token: str, name: str, parent_id: str | None = None) -> str | None:
    q = (f"name='{name.replace(chr(39), chr(92)+chr(39))}' and "
         f"mimeType='application/vnd.google-apps.folder' and trashed=false")
    if parent_id:
        q += f" and '{parent_id}' in parents"
    body = _api(token, "GET", params={"q": q, "fields": "files(id,name)",
                                      "pageSize": 5, "spaces": "drive"})
    files = body.get("files", [])
    return files[0]["id"] if files else None


def _create_folder(cfg, token: str, name: str, parent_id: str | None = None) -> str:
    meta: dict = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    body = _api(token, "POST", payload=meta, params={"fields": "id"})
    fid = body.get("id")
    if not fid:
        raise RuntimeError("Drive did not return a folder id")
    return fid


def ensure_octora_folder(cfg) -> tuple[str | None, str]:
    """Creates the OCTORA root folder on first use. Returns (folder_id, message).

    Zero user setup: called automatically after Google connect and before the
    first real Drive upload. The id is cached in config afterwards."""
    cached = cfg.get("drive_octora_folder_id", "")
    if cached:
        return cached, "Drive folder already set up."
    token = _valid_token(cfg)
    if not token:
        return None, "Google not connected."
    try:
        fid = _find_folder(cfg, token, ROOT_FOLDER_NAME) or \
            _create_folder(cfg, token, ROOT_FOLDER_NAME)
    except Exception as e:  # noqa: BLE001
        return None, f"Drive folder setup failed: {e}"
    cfg.set("drive_octora_folder_id", fid)
    return fid, f"OCTORA Drive folder ready: {folder_link(fid)}"


def ensure_campaign_folder(cfg, campaign_name: str) -> tuple[str | None, str]:
    """Per-campaign subfolder OCTORA/<CampaignName>. Cached per campaign name."""
    root, msg = ensure_octora_folder(cfg)
    if not root:
        return None, msg
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in (campaign_name or "")).strip() or "Untitled"
    key = f"drive_subfolder_{safe}"
    cached = cfg.get(key, "")
    if cached:
        return cached, "ok"
    token = _valid_token(cfg)
    if not token:
        return None, "Google not connected."
    try:
        fid = _find_folder(cfg, token, safe, parent_id=root) or \
            _create_folder(cfg, token, safe, parent_id=root)
    except Exception as e:  # noqa: BLE001
        return None, f"Campaign folder setup failed: {e}"
    cfg.set(key, fid)
    return fid, f"ok"


def _req(url, token, data=None, headers=None, method=None, timeout=60):
    h = {"Authorization": f"Bearer {token}"}
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()


def upload_file(cfg, path: str, folder_id: str = "") -> tuple[bool, str]:
    """Uploads a file to Google Drive. Returns (ok, file_id_or_error)."""
    token = oauth.google_access_token(cfg)
    if not token:
        return False, "Google not connected — click 'Connect Google' in Platforms/Settings."
    if not os.path.exists(path):
        return False, "Local file not found."
    size = os.path.getsize(path)
    mime, _ = mimetypes.guess_type(path)
    meta = {"name": os.path.basename(path)}
    if folder_id:
        meta["parents"] = [folder_id]
    # --- resumable session: init session URL, then PUT the bytes ---
    try:
        session_url = _init_session(cfg, token, meta, mime, size)
        file_id = _put_bytes(session_url, token, path, size, mime)
        return True, file_id
    except Exception as e:  # noqa: BLE001
        return False, f"Drive upload failed: {e}"


def _refresh(cfg):
    cfg.set("google_access_token", "")
    oauth.google_access_token(cfg)


def _init_session(cfg, token, meta, mime, size) -> str:
    import urllib.error
    data = json.dumps(meta).encode()
    req = urllib.request.Request(
        DRIVE_UPLOAD_URL, data=data, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": mime or "application/octet-stream",
                 "X-Upload-Content-Length": str(size)})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            loc = resp.headers.get("Location")
            if not loc:
                raise RuntimeError("Drive did not return an upload session URL")
            return loc
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            _refresh(cfg)
            token = oauth.google_access_token(cfg)
            if not token:
                raise RuntimeError("Google authorization expired — reconnect in Settings")
            return _init_session(cfg, token, meta, mime, size)
        raise RuntimeError(f"Drive session init HTTP {e.code}")


def _put_bytes(session_url, token, path, size, mime) -> str:
    import urllib.error
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        session_url, data=data, method="PUT",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": mime or "application/octet-stream",
                 "Content-Length": str(len(data))})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode() or "{}")
            fid = body.get("id")
            if not fid:
                raise RuntimeError("Drive upload finished without a file id")
            return fid
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Drive upload HTTP {e.code}")
