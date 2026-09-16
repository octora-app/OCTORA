"""Drive Sync: watch a local folder, import new videos with SHA-256 dedup."""
import hashlib
from pathlib import Path

from .database import iso_ist, now_ist
from .logger import get_logger
from .validators import VIDEO_EXTS, validate_video

log = get_logger("octora.drive")


def sha256_of(path: Path, limit_mb: int = 200) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        remaining = limit_mb * 1024 * 1024
        while remaining > 0:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()


def import_file(db, p: Path) -> tuple[bool, str]:
    """Import one video file. Returns (added, reason)."""
    try:
        digest = sha256_of(p)
    except OSError:
        return False, "unreadable"
    if db.query_one("SELECT id FROM assets WHERE sha256=?", (digest,)):
        return False, "duplicate"
    info = validate_video(p)
    db.execute(
        "INSERT INTO assets(filename,path,sha256,size,duration,width,height,"
        "status,note,added_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (p.name, str(p), digest, info["size"], info["duration"],
         info["width"], info["height"],
         "new" if info["ok"] else "failed",
         info["note"], iso_ist(now_ist())))
    log.info("drive sync: imported %s (%s)", p.name,
             "ok" if info["ok"] else info["note"])
    return True, "ok"


def scan_folder(db, folder: str | Path) -> tuple[int, int]:
    """Import new video files. Returns (added, skipped_duplicates)."""
    folder = Path(folder)
    if not folder.is_dir():
        return 0, 0
    added, skipped = 0, 0
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.suffix.lower() not in VIDEO_EXTS:
            continue
        ok, reason = import_file(db, p)
        if ok:
            added += 1
        elif reason == "duplicate":
            skipped += 1
    return added, skipped
