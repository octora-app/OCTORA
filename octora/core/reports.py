"""CSV report exports."""
import csv
from pathlib import Path


def export_uploads_csv(db, path: str | Path) -> Path:
    p = Path(path)
    rows = db.query("SELECT id, platform, asset, status, message, at "
                    "FROM uploads_log ORDER BY at DESC")
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "platform", "asset", "status", "message", "at_ist"])
        for r in rows:
            w.writerow([r["id"], r["platform"], r["asset"], r["status"],
                        r["message"], r["at"]])
    return p


def export_queue_csv(db, path: str | Path) -> Path:
    p = Path(path)
    rows = db.query("SELECT id, platform, priority, status, attempts, last_error,"
                    " next_retry_at, created_at FROM upload_queue ORDER BY id DESC")
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "platform", "priority", "status", "attempts",
                    "last_error", "next_retry_at", "created_at"])
        for r in rows:
            w.writerow([r["id"], r["platform"], r["priority"], r["status"],
                        r["attempts"], r["last_error"], r["next_retry_at"],
                        r["created_at"]])
    return p
