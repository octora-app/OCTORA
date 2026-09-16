"""Drive Sync: watch a local folder, import new videos with dedup + validation."""
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
                             QAbstractItemView, QSpinBox)

from ...core.drive_sync import scan_folder
from ..widgets import h1, muted, Card, h2, icon_button


class DriveSync(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        lay.addWidget(h1("Drive Sync"))
        lay.addWidget(muted("Assets & Storage — new video files dropped in the watched folder are "
                            "imported automatically with SHA-256 duplicate detection."))

        cfg = Card()
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Watched folder:"))
        self.folder_lbl = QLabel(app.cfg.get("drive_folder"))
        self.folder_lbl.setStyleSheet("font-weight:700;")
        crow.addWidget(self.folder_lbl, 1)
        browse = QPushButton("Change…")
        browse.clicked.connect(self._browse)
        crow.addWidget(browse)
        openf = QPushButton("Open folder")
        openf.clicked.connect(self._open)
        crow.addWidget(openf)
        cfg.layout_().addLayout(crow)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Poll every (sec):"))
        self.poll = QSpinBox()
        self.poll.setRange(5, 600)
        self.poll.setValue(int(app.cfg.get("poll_seconds", 15)))
        self.poll.valueChanged.connect(lambda v: app.cfg.set("poll_seconds", v))
        prow.addWidget(self.poll)
        scan = icon_button("Scan now", "refresh")
        scan.clicked.connect(self._scan)
        prow.addWidget(scan)
        prow.addStretch()
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        prow.addWidget(self.status)
        cfg.layout_().addLayout(prow)
        lay.addWidget(cfg)

        # ---- Google Drive upload ----
        gcard = Card()
        gcard.add(h2("☁ Google Drive Upload"))
        grow = QHBoxLayout()
        self.gdrive_status = QLabel()
        self.gdrive_status.setWordWrap(True)
        grow.addWidget(self.gdrive_status, 1)
        connect = icon_button("Connect Google", "link")
        connect.clicked.connect(lambda: self.app.nav_to("platforms"))
        grow.addWidget(connect)
        retry = QPushButton("↻ Retry failed Drive uploads")
        retry.clicked.connect(self._retry_drive)
        grow.addWidget(retry)
        gcard.layout_().addLayout(grow)
        self.gdrive_folder_lbl = QLabel()
        self.gdrive_folder_lbl.setWordWrap(True)
        self.gdrive_folder_lbl.setOpenExternalLinks(True)
        self.gdrive_folder_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse)
        gcard.layout_().addWidget(self.gdrive_folder_lbl)
        gcard.add(muted("Ready assets are uploaded to your Google Drive automatically. "
                        "Only files with a verified Drive upload are eligible for auto-delete."))
        lay.addWidget(gcard)

        lay.addWidget(h2("Asset Library"))
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Filename", "Size", "Duration", "Resolution", "Status", "Added"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        lay.addWidget(self.table, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scan_quiet)
        self._timer.start(int(app.cfg.get("poll_seconds", 15)) * 1000)
        self.refresh()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Watched folder")
        if d:
            self.app.cfg.set("drive_folder", d)
            self.folder_lbl.setText(d)
            self.app.log.info("drive folder set: %s", d)

    def _open(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.app.cfg.get("drive_folder")))

    def _fmt_size(self, n):
        for u in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {u}"
            n /= 1024
        return f"{n:.1f} TB"

    def _scan_quiet(self):
        added, skipped = scan_folder(self.app.db, self.app.cfg.get("drive_folder"))
        if added or skipped:
            self.refresh()

    def _scan(self):
        added, skipped = scan_folder(self.app.db, self.app.cfg.get("drive_folder"))
        self.status.setText(f"Scan complete: {added} new, {skipped} duplicates skipped")
        self.app.log.info("drive scan: %d new, %d dup", added, skipped)
        self.refresh()

    def _retry_drive(self):
        n = self.app.db.execute(
            "UPDATE assets SET drive_status='pending', note='' WHERE drive_status='failed'").rowcount
        self.app.log.info("drive: %d failed upload(s) re-queued", n)
        self.refresh()

    def refresh(self):
        # google drive status line
        demo = self.app.cfg.demo_mode
        conn = "simulated (demo mode)" if demo else (
            "connected ✅" if self.app.cfg.get("google_refresh_token") else "not connected")
        counts = {}
        for st in ("pending", "uploading", "done", "failed"):
            r = self.app.db.query_one(
                "SELECT COUNT(*) c FROM assets WHERE drive_status=?", (st,))
            counts[st] = r["c"] or 0
        self.gdrive_status.setText(
            f"Google Drive: <b>{conn}</b> &nbsp;•&nbsp; pending {counts['pending']} • "
            f"uploading {counts['uploading']} • done {counts['done']} • failed {counts['failed']}")
        # v1.2: show the auto-created OCTORA folder (zero user setup)
        if demo:
            self.gdrive_folder_lbl.setText(
                "Cloud folder: <b>OCTORA</b> (simulated in demo mode — "
                "connect Google in live mode and it is created for you automatically)")
        else:
            from ...core import gdrive as _gd
            fid = self.app.cfg.get("drive_octora_folder_id", "")
            if fid:
                self.gdrive_folder_lbl.setText(
                    f"Cloud folder: <b>OCTORA</b> — "
                    f"<a href='{_gd.folder_link(fid)}'>open in Google Drive</a> "
                    "&nbsp;•&nbsp; per-campaign subfolders are created automatically")
            elif self.app.cfg.get("google_refresh_token"):
                self.gdrive_folder_lbl.setText(
                    "Cloud folder: will be created automatically on first Drive upload.")
            else:
                self.gdrive_folder_lbl.setText(
                    "Cloud folder: connect Google (Platforms screen) — "
                    "your OCTORA folder is created automatically, no setup needed.")
        rows = self.app.db.query("SELECT * FROM assets ORDER BY id DESC LIMIT 500")
        self.table.setRowCount(len(rows))
        for i, a in enumerate(rows):
            dur = f"{a['duration']:.1f}s" if a["duration"] else "—"
            res = f"{a['width']}x{a['height']}" if a["width"] else "—"
            vals = [a["id"], a["filename"], self._fmt_size(a["size"] or 0), dur, res,
                    f"{a['status']} / drive:{a['drive_status']}",
                    (a["added_at"] or "")[:16].replace("T", " ")]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, it)
