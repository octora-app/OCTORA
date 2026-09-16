"""Video file validation: ffprobe when available, else file-size heuristic."""
import json
import shutil
import subprocess
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def validate_video(path: str | Path) -> dict:
    p = Path(path)
    info = {"ok": False, "path": str(p), "size": 0, "duration": 0.0,
            "width": 0, "height": 0, "note": "", "method": "none"}
    if not p.exists():
        info["note"] = "File not found"
        return info
    info["size"] = p.stat().st_size
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", str(p)],
                capture_output=True, text=True, timeout=20)
            data = json.loads(out.stdout or "{}")
            fmt = data.get("format", {})
            info["duration"] = float(fmt.get("duration", 0) or 0)
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    info["width"] = int(s.get("width", 0) or 0)
                    info["height"] = int(s.get("height", 0) or 0)
                    break
            info["method"] = "ffprobe"
        except Exception as e:  # noqa: BLE001
            info["note"] = f"ffprobe error: {e}"
    else:
        info["method"] = "size-heuristic"
        # assume ~1.5 Mbps average -> rough duration estimate
        if info["size"] > 0:
            info["duration"] = round(info["size"] * 8 / 1_500_000, 1)
            info["note"] = "ffprobe not found — duration estimated from file size"
    vertical = info["height"] >= info["width"] and info["height"] > 0
    big_enough = info["size"] >= 50_000
    info["vertical"] = vertical
    info["ok"] = big_enough and (info["method"] == "size-heuristic" or info["duration"] > 0)
    if not big_enough:
        info["note"] = (info["note"] + " | " if info["note"] else "") + "file too small (<50KB)"
    if info["method"] == "ffprobe" and not vertical:
        info["note"] = (info["note"] + " | " if info["note"] else "") + "not vertical 9:16"
    return info
