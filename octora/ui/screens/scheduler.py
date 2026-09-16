"""Scheduler: IST timeline view, add/edit/delete scheduled posts, queue management.

v1.2: each queued post shows its SEO metadata preview (title/tags/caption as
the upload engine will apply them); any field can be overridden per video."""
import json
from datetime import datetime

from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QDialog, QFormLayout,
                             QLineEdit, QComboBox, QDateTimeEdit, QDialogButtonBox,
                             QHeaderView, QMessageBox, QAbstractItemView, QTextEdit,
                             QGroupBox)

from ...core.database import IST, iso_ist, now_ist
from ...core.captions import generate_caption
from ...core import metadata as seo
from ..widgets import h1, muted, icon_button


class PostDialog(QDialog):
    def __init__(self, parent, app, data=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("Schedule Post" if data is None else "Edit Scheduled Post")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.platform = QLabel("YouTube Shorts")
        self.campaign = QComboBox()
        self.campaign.addItem("— none —", None)
        for c in app.db.query("SELECT id, name FROM campaigns WHERE active=1"):
            self.campaign.addItem(c["name"], c["id"])
        self.when = QDateTimeEdit(QDateTime.currentDateTime())
        self.when.setDisplayFormat("dd MMM yyyy HH:mm")
        self.when.setCalendarPopup(True)
        self.caption = QTextEdit()
        self.caption.setFixedHeight(60)
        self.caption.setPlaceholderText("Optional caption note (metadata engine builds the real one)")
        ov = {}
        if data:
            self.caption.setPlainText(data["caption"])
            try:
                dt = datetime.fromisoformat(data["scheduled_at"]).replace(tzinfo=None)
                self.when.setDateTime(QDateTime(dt))
            except Exception:  # noqa: BLE001
                pass
            try:
                ov = json.loads(data.get("meta_json") or "{}")
            except Exception:  # noqa: BLE001
                ov = {}
        form.addRow("Platform", self.platform)
        form.addRow("Campaign", self.campaign)
        form.addRow("When (IST)", self.when)
        form.addRow("Caption note", self.caption)
        lay.addLayout(form)

        # ---- per-video metadata override (v1.2) ----
        mbox = QGroupBox("SEO metadata override — leave empty to auto-generate from the campaign")
        mform = QFormLayout(mbox)
        self.m_title = QLineEdit(ov.get("title", ""))
        self.m_title.setPlaceholderText("auto")
        self.m_desc = QTextEdit(ov.get("description", ""))
        self.m_desc.setFixedHeight(52)
        self.m_desc.setPlaceholderText("auto (YouTube description)")
        self.m_tags = QLineEdit(ov.get("tags", ""))
        self.m_tags.setPlaceholderText("auto — comma,separated")
        self.m_cap = QTextEdit(ov.get("caption", ""))
        self.m_cap.setFixedHeight(52)
        self.m_cap.setPlaceholderText("auto")
        mform.addRow("Title", self.m_title)
        mform.addRow("Description", self.m_desc)
        mform.addRow("Tags", self.m_tags)
        mform.addRow("Caption", self.m_cap)
        self.m_preview = QLabel()
        self.m_preview.setWordWrap(True)
        self.m_preview.setObjectName("Muted")
        mform.addRow("Preview", self.m_preview)
        for w in (self.m_title, self.m_desc, self.m_tags, self.m_cap):
            sig = w.textChanged if isinstance(w, QLineEdit) else w.textChanged
            sig.connect(self._preview_meta)
        lay.addWidget(mbox)

        gen = icon_button("Generate caption from template", "zap")
        gen.clicked.connect(self._gen)
        lay.addWidget(gen)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self._preview_meta()

    def _preview_meta(self):
        pid = "youtube"
        camp = None
        cid = self.campaign.currentData()
        if cid:
            r = self.app.db.query_one("SELECT * FROM campaigns WHERE id=?", (cid,))
            camp = dict(r) if r else None
        r = seo.render(pid, camp, "sample-clip.mp4", self._overrides() or None)
        warn = f"  ⚠ {' '.join(r['warnings'])}" if r["warnings"] else "  ✅ checks pass"
        self.m_preview.setText(f"{r['title'][:80]} ({len(r['title'])} chars){warn}")

    def _gen(self):
        g = generate_caption("scheduled drop", "YT Shorts")
        self.caption.setPlainText(g["caption"])

    def _overrides(self):
        ov = {}
        if self.m_title.text().strip():
            ov["title"] = self.m_title.text().strip()
        if self.m_desc.toPlainText().strip():
            ov["description"] = self.m_desc.toPlainText().strip()
        if self.m_tags.text().strip():
            ov["tags"] = self.m_tags.text().strip()
        if self.m_cap.toPlainText().strip():
            ov["caption"] = self.m_cap.toPlainText().strip()
        return ov

    def values(self):
        dt = self.when.dateTime().toPyDateTime().replace(tzinfo=IST)
        return {
            "platform": "YT Shorts",
            "campaign_id": self.campaign.currentData(),
            "scheduled_at": iso_ist(dt),
            "caption": self.caption.toPlainText().strip(),
            "meta_json": json.dumps(self._overrides(), ensure_ascii=False),
        }


class Scheduler(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(h1("Scheduler"))
        head.addStretch()
        add = QPushButton("＋ Schedule Post")
        add.clicked.connect(self._add)
        head.addWidget(add)
        lay.addLayout(head)
        lay.addWidget(muted("Auto-Post Timeline — all times Asia/Kolkata (IST). Due posts flow into the Upload Engine automatically."))

        self.filter = QComboBox()
        self.filter.addItems(["Today", "Upcoming", "All", "Posted", "Failed"])
        self.filter.currentIndexChanged.connect(self.refresh)
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Show:"))
        frow.addWidget(self.filter)
        frow.addStretch()
        lay.addLayout(frow)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "When (IST)", "Platform", "Title (SEO)", "Caption", "Status", "Attempts"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        lay.addWidget(self.table, 1)

        brow = QHBoxLayout()
        edit = QPushButton("Edit")
        edit.clicked.connect(self._edit)
        cancel = QPushButton("Cancel Post")
        cancel.setObjectName("Danger")
        cancel.clicked.connect(self._cancel)
        enqueue = QPushButton("⏩ Send to Upload Queue now")
        enqueue.clicked.connect(self._enqueue_now)
        brow.addWidget(edit)
        brow.addWidget(cancel)
        brow.addWidget(enqueue)
        brow.addStretch()
        lay.addLayout(brow)
        self.refresh()

    def _selected(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        return int(self.table.item(r, 0).text())

    def refresh(self):
        mode = self.filter.currentText()
        today = now_ist().date().isoformat()
        if mode == "Today":
            rows = self.app.db.query(
                "SELECT * FROM scheduled_posts WHERE substr(scheduled_at,1,10)=? ORDER BY scheduled_at",
                (today,))
        elif mode == "Upcoming":
            rows = self.app.db.query(
                "SELECT * FROM scheduled_posts WHERE status IN ('queued','in_queue') ORDER BY scheduled_at")
        elif mode == "Posted":
            rows = self.app.db.query(
                "SELECT * FROM scheduled_posts WHERE status='posted' ORDER BY scheduled_at DESC LIMIT 200")
        elif mode == "Failed":
            rows = self.app.db.query(
                "SELECT * FROM scheduled_posts WHERE status='failed' ORDER BY scheduled_at DESC LIMIT 200")
        else:
            rows = self.app.db.query("SELECT * FROM scheduled_posts ORDER BY scheduled_at DESC LIMIT 300")
        self.table.setRowCount(len(rows))
        for i, p in enumerate(rows):
            title = self._title_preview(p)
            vals = [p["id"], p["scheduled_at"][:16].replace("T", " "), p["platform"],
                    title[:70], (p["caption"] or "")[:50], p["status"], p["attempts"]]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, it)

    def _title_preview(self, p) -> str:
        """What the upload engine will actually use as the title."""
        pid = "youtube"
        try:
            ov = json.loads(p["meta_json"] or "{}")
        except Exception:  # noqa: BLE001
            ov = {}
        camp = None
        if p["campaign_id"]:
            r = self.app.db.query_one("SELECT * FROM campaigns WHERE id=?", (p["campaign_id"],))
            camp = dict(r) if r else None
        fname = ""
        if p["asset_id"]:
            r = self.app.db.query_one("SELECT filename FROM assets WHERE id=?", (p["asset_id"],))
            fname = r["filename"] if r else ""
        r = seo.render(pid, camp, fname or "clip.mp4", ov or None)
        return r["title"]

    def _add(self):
        d = PostDialog(self, self.app)
        if d.exec():
            v = d.values()
            self.app.db.execute(
                "INSERT INTO scheduled_posts(campaign_id,platform,scheduled_at,status,caption,"
                "meta_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (v["campaign_id"], v["platform"], v["scheduled_at"], "queued",
                 v["caption"], v["meta_json"], iso_ist(now_ist())))
            self.app.log.info("scheduled: %s at %s", v["platform"], v["scheduled_at"])
            self.refresh()

    def _edit(self):
        pid = self._selected()
        if pid is None:
            return
        data = dict(self.app.db.query_one("SELECT * FROM scheduled_posts WHERE id=?", (pid,)))
        if data["status"] not in ("queued",):
            QMessageBox.information(self, "Scheduler", "Only queued posts can be edited.")
            return
        d = PostDialog(self, self.app, data)
        if d.exec():
            v = d.values()
            self.app.db.execute(
                "UPDATE scheduled_posts SET platform=?, scheduled_at=?, caption=?, "
                "meta_json=? WHERE id=?",
                (v["platform"], v["scheduled_at"], v["caption"], v["meta_json"], pid))
            self.refresh()

    def _cancel(self):
        pid = self._selected()
        if pid is None:
            return
        self.app.db.execute("UPDATE scheduled_posts SET status='cancelled' WHERE id=?", (pid,))
        self.app.log.info("scheduled post %d cancelled", pid)
        self.refresh()

    def _enqueue_now(self):
        pid = self._selected()
        if pid is None:
            return
        p = self.app.db.query_one("SELECT * FROM scheduled_posts WHERE id=?", (pid,))
        if p["status"] != "queued":
            QMessageBox.information(self, "Scheduler", "Only queued posts can be fast-tracked.")
            return
        from ...core.engine import build_meta
        meta = build_meta(self.app.db, p["platform"], asset_id=p["asset_id"],
                          campaign_id=p["campaign_id"], override_json=p["meta_json"] or "")
        self.app.engine.enqueue(platform=p["platform"], scheduled_post_id=pid,
                                asset_id=p["asset_id"], priority=9,
                                caption=meta["caption"],
                                meta_json=json.dumps(meta, ensure_ascii=False))
        self.app.db.execute("UPDATE scheduled_posts SET status='in_queue' WHERE id=?", (pid,))
        self.app.log.info("fast-tracked scheduled post %d to upload queue", pid)
        self.refresh()
