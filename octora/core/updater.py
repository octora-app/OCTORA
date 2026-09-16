"""One-click auto-updates for OCTORA.

How it works
------------
1. On startup the app fetches a small JSON manifest (default:
   https://octora.pages.dev/releases/latest.json, overridable via the
   `update_manifest_url` setting):
     {"version": "1.4.1", "download_url": "https://…/OCTORA-Setup.exe",
      "changelog": "…", "mandatory": false,
      "sha256": "<hex of the installer>", "signature": "<base64 RSA sig>"}
2. The manifest MUST carry a valid RSA signature (seller private key) over the
   canonical JSON of {version, download_url, changelog, mandatory, sha256}.
   A missing/invalid signature means the update is silently skipped (fail
   closed) — this stops anyone who compromises the website from pushing a
   malicious "update" to every user.
3. If manifest version > current app version AND the signature verifies, the
   user gets a popup with the changelog and an "Update now" button.
4. "Update now" downloads the installer, verifies its SHA-256 against the
   manifest, then runs it silently and restarts OCTORA.

The seller ships an update by: building the new Setup.exe, computing its
SHA-256, signing the manifest with tools/sign_manifest.py (seller private
key), and publishing releases/latest.json on the website.
"""
import base64
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

DEFAULT_MANIFEST_URL = "https://octora.pages.dev/releases/latest.json"

# Fields covered by the manifest signature (anything else is ignored).
_SIGNED_FIELDS = ("version", "download_url", "changelog", "mandatory", "sha256")


def _manifest_signature_ok(manifest: dict) -> bool:
    """Verify the seller's RSA signature over the canonical manifest JSON."""
    try:
        from .license import _canonical, _pkcs1v15_verify
        sig_b64 = manifest.get("signature", "")
        if not sig_b64:
            return False
        payload = {k: manifest.get(k, "") for k in _SIGNED_FIELDS}
        # normalize types so both sides sign identical bytes
        payload["mandatory"] = bool(manifest.get("mandatory", False))
        return _pkcs1v15_verify(_canonical(payload), base64.b64decode(sig_b64))
    except Exception:
        return False


def _ver_tuple(v: str) -> tuple:
    parts = []
    for x in str(v).strip().lstrip("vV").split("."):
        digits = "".join(c for c in x if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def fetch_manifest(cfg) -> dict | None:
    url = (cfg.get("update_manifest_url") or "").strip() or DEFAULT_MANIFEST_URL
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OCTORA-updater"})
        with urllib.request.urlopen(req, timeout=12) as r:
            m = __import__("json").loads(r.read().decode("utf-8"))
        return m if isinstance(m, dict) else None
    except Exception:
        return None  # offline / unreachable -> silently skip the check


def check_for_update(cfg, current_version: str) -> dict | None:
    """Return update info dict when a newer, signature-verified version exists.

    Returns None (silently skips the update) when the manifest is missing,
    older-or-equal, or its seller signature does not verify — fail closed.
    """
    m = fetch_manifest(cfg)
    if not m:
        return None
    latest = str(m.get("version", "")).strip()
    url = str(m.get("download_url", "")).strip()
    if not latest or not url:
        return None
    try:
        if _ver_tuple(latest) <= _ver_tuple(current_version):
            return None
    except Exception:
        return None
    if not _manifest_signature_ok(m):
        return None  # unsigned or forged manifest -> never offer the update
    return {"version": latest, "download_url": url,
            "changelog": str(m.get("changelog", "")),
            "mandatory": bool(m.get("mandatory", False)),
            "sha256": str(m.get("sha256", "")).strip().lower()}


def _install_dir_and_exe() -> tuple[Path, Path]:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return exe.parent, exe
    root = Path(__file__).resolve().parent.parent.parent  # project root (dev)
    return root, Path(sys.executable)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_and_apply(download_url: str, expected_sha256: str = "") -> tuple[bool, str]:
    """Download the update and hand off to the OS installer. Returns (ok, msg).

    When expected_sha256 is given (from the signed manifest), the downloaded
    file's hash must match or the update is aborted and the file deleted.

    On success this function DOES NOT RETURN to the app — it launches the
    updater batch file and the caller must quit immediately afterwards.
    """
    if os.name != "nt":
        return False, "Auto-update is currently supported on Windows only."
    tmp = Path(tempfile.gettempdir()) / "octora-update"
    tmp.mkdir(exist_ok=True)
    fname = download_url.rstrip("/").split("/")[-1].split("?")[0] or "update.bin"
    local = tmp / fname
    try:
        req = urllib.request.Request(download_url,
                                     headers={"User-Agent": "OCTORA-updater"})
        with urllib.request.urlopen(req, timeout=120) as r, open(local, "wb") as f:
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:  # noqa: BLE001
        return False, f"Download failed: {e}"

    if expected_sha256:
        try:
            actual = _sha256_file(local)
        except Exception as e:  # noqa: BLE001
            return False, f"Could not hash the downloaded update: {e}"
        if actual != expected_sha256:
            try:
                local.unlink()
            except Exception:
                pass
            return False, ("Update failed integrity check (hash mismatch). "
                           "The file was deleted and nothing was installed.")

    install_dir, exe = _install_dir_and_exe()
    pid = os.getpid()
    if fname.lower().endswith(".zip"):
        bat = tmp / "apply_update.bat"
        bat.write_text(
            "@echo off\r\n"
            f'set PID={pid}\r\nset ZIP={local}\r\nset DIR={install_dir}\r\nset EXE={exe}\r\n'
            ":wait\r\n"
            'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul\r\n'
            "if not errorlevel 1 ( timeout /t 1 /nobreak >nul & goto wait )\r\n"
            "powershell -NoProfile -ExecutionPolicy Bypass -Command "
            "\"Expand-Archive -Force '%ZIP%' '%DIR%'\"\r\n"
            'start "" "%EXE%"\r\n'
            'del "%ZIP%" 2>nul\r\n'
            "del \"%~f0\" 2>nul\r\n", encoding="utf-8")
    else:
        # Assume a full installer (e.g. Inno Setup .exe): run silently, wait,
        # then restart the app. One click for the user, zero manual steps.
        bat = tmp / "apply_update.bat"
        bat.write_text(
            "@echo off\r\n"
            f'set PID={pid}\r\nset SETUP={local}\r\nset EXE={exe}\r\n'
            ":wait\r\n"
            'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul\r\n'
            "if not errorlevel 1 ( timeout /t 1 /nobreak >nul & goto wait )\r\n"
            'start /wait "" "%SETUP%" /SILENT /NORESTART /SUPPRESSMSGBOXES\r\n'
            'start "" "%EXE%"\r\n'
            'del "%SETUP%" 2>nul\r\n'
            "del \"%~f0\" 2>nul\r\n", encoding="utf-8")
    try:
        subprocess.Popen(["cmd", "/c", str(bat)], cwd=str(tmp),
                         creationflags=subprocess.DETACHED_PROCESS
                         | subprocess.CREATE_NEW_PROCESS_GROUP,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, close_fds=True)
    except Exception as e:  # noqa: BLE001
        return False, f"Could not launch the updater: {e}"
    return True, "updater launched"


# ---------------------------------------------------------------- Qt glue
def check_async(cfg, current_version: str, window) -> None:
    """Non-blocking startup check; shows the popup on the GUI thread."""
    try:
        from PyQt6.QtCore import QObject, QTimer, pyqtSignal

        class _Sig(QObject):
            found = pyqtSignal(dict)

        sig = _Sig()

        def _show(info: dict):
            try:
                from PyQt6.QtWidgets import QApplication, QMessageBox
                from PyQt6.QtCore import Qt
                box = QMessageBox(window)
                box.setWindowTitle("OCTORA update available")
                box.setText(f"<b>OCTORA v{info['version']} is available</b>"
                            f" (you have v{current_version}).")
                if info.get("changelog"):
                    box.setInformativeText(info["changelog"])
                update_btn = box.addButton("Update now",
                                           QMessageBox.ButtonRole.AcceptRole)
                if not info.get("mandatory"):
                    box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
                box.setDefaultButton(update_btn)
                box.exec()
                if box.clickedButton() is update_btn:
                    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                    try:
                        ok, msg = download_and_apply(info["download_url"],
                                                     info.get("sha256", ""))
                    finally:
                        QApplication.restoreOverrideCursor()
                    if ok:
                        # Updater batch file is running detached; quit now so it
                        # can replace files and restart the app.
                        QApplication.instance().quit()
                        os._exit(0)
                    else:
                        QMessageBox.warning(window, "Update", msg)
            except Exception:
                pass

        sig.found.connect(_show)

        def _worker():
            try:
                info = check_for_update(cfg, current_version)
            except Exception:
                info = None
            if info:
                # pyqtSignal.emit() is thread-safe: the slot runs queued on
                # the GUI thread that owns `sig`. (Do NOT use
                # QTimer.singleShot from a worker thread — the timer would
                # live on the wrong thread and never fire reliably.)
                sig.found.emit(info)

        # give the main window a moment to appear first
        QTimer.singleShot(4000, lambda: threading.Thread(
            target=_worker, daemon=True).start())
    except Exception:
        pass
