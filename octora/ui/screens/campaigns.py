"""Campaigns: full CRUD — name, platform, source folder, IST schedule time,
SEO metadata templates (v1.2)."""
import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QDialog, QFormLayout,
                             QLineEdit, QComboBox, QTimeEdit, QTextEdit, QCheckBox,
                             QDialogButtonBox, QFileDialog, QHeaderView, QMessageBox,
                             QAbstractItemView, QGroupBox, QScrollArea)

from ...core.database import iso_ist, now_ist
from ...core import metadata as seo
from ..widgets import h1, muted, Card, h1_icon


class CampaignDialog(QDialog):
    def __init__(self, parent, data=None):
        super().__init__(parent)
        self.setWindowTitle("Campaign" if data is None else "Edit Campaign")
        self.setMinimumWidth(620)
        self.setMinimumHeight(640)
        lay = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        blay = QVBoxLayout(body)

        # ---- basics ----
        basic = QGroupBox("Basics")
        form = QFormLayout(basic)
        self.name = QLineEdit(data["name"] if data else "")
        self.platform = QLabel("YouTube Shorts")
        self.folder = QLineEdit(data["source_folder"] if data else "")
        browse = QPushButton("Browse…")
        brow = QHBoxLayout()
        brow.addWidget(self.folder, 1)
        brow.addWidget(browse)
        browse.clicked.connect(self._browse)
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        if data:
            from PyQt6.QtCore import QTime
            self.time.setTime(QTime.fromString(data["schedule_time"], "HH:mm"))
        self.niche = QComboBox()
        self.niche.setEditable(True)
        self.niche.addItems(sorted(seo.NICHE_BANKS.keys()))
        if data and data.get("niche"):
            self.niche.setCurrentText(data["niche"])
        self.niche.currentTextChanged.connect(self._preview)
        self.active = QCheckBox("Active")
        self.active.setChecked(True if not data else bool(data["active"]))
        form.addRow("Name", self.name)
        form.addRow("Platform", self.platform)
        form.addRow("Niche", self.niche)
        form.addRow("Source folder", brow)
        form.addRow("Daily time (IST)", self.time)
        form.addRow("", self.active)
        blay.addWidget(basic)

        # ---- SEO metadata templates (v1.2) ----
        meta = QGroupBox("SEO Metadata — applied automatically at upload")
        mlay = QVBoxLayout(meta)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Load preset:"))
        for pid, label in (("youtube", "YouTube Shorts"),):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, p=pid: self._load_preset(p))
            prow.addWidget(b)
        prow.addStretch()
        mlay.addLayout(prow)
        mlay.addWidget(QLabel(f"Variables: {seo.VARIABLES_HELP}"))

        self.title_tpl = QLineEdit(
            (data.get("title_template") if data else "") or "")
        self.title_tpl.setPlaceholderText("Leave empty to use the platform preset")
        self.title_tpl.textChanged.connect(self._preview)
        self.desc_tpl = QTextEdit((data.get("description_template") if data else "") or "")
        self.desc_tpl.setFixedHeight(64)
        self.desc_tpl.setPlaceholderText("Leave empty to use the platform preset")
        self.desc_tpl.textChanged.connect(self._preview)
        self.tags_tpl = QLineEdit((data.get("tags_template") if data else "") or "")
        self.tags_tpl.setPlaceholderText("comma,separated,{keyword} — leave empty for preset")
        self.tags_tpl.textChanged.connect(self._preview)
        self.caption_tpl = QTextEdit((data.get("caption_template") if data else "") or "")
        self.caption_tpl.setFixedHeight(56)
        self.caption_tpl.setPlaceholderText("Caption template (YouTube uses title+description)")
        self.caption_tpl.textChanged.connect(self._preview)
        self.hashtags = QLineEdit(data["hashtags"] if data else "")
        self.hashtags.setPlaceholderText("#shorts #viral …")
        mform = QFormLayout()
        mform.addRow("Title template", self.title_tpl)
        mform.addRow("Description template", self.desc_tpl)
        mform.addRow("Tags template", self.tags_tpl)
        mform.addRow("Caption template", self.caption_tpl)
        mform.addRow("Hashtags", self.hashtags)
        mlay.addLayout(mform)

        # live preview
        mlay.addWidget(QLabel("<b>Live preview</b> (sample file: morning-productivity-tips_014.mp4)"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(130)
        mlay.addWidget(self.preview)
        self.warn_lbl = QLabel()
        self.warn_lbl.setWordWrap(True)
        mlay.addWidget(self.warn_lbl)
        blay.addWidget(meta)

        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self._preview()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Source folder")
        if d:
            self.folder.setText(d)

    def _load_preset(self, pid):
        p = seo.PLATFORM_PRESETS[pid]
        self.title_tpl.setText(p["title_template"])
        self.desc_tpl.setPlainText(p["description_template"])
        self.tags_tpl.setText(p["tags_template"])
        if p.get("caption_template"):
            self.caption_tpl.setPlainText(p["caption_template"])
        self._preview()

    def _preview(self):
        pid = "youtube"
        fake_campaign = {
            "title_template": self.title_tpl.text().strip(),
            "description_template": self.desc_tpl.toPlainText().strip(),
            "tags_template": self.tags_tpl.text().strip(),
            "caption_template": self.caption_tpl.toPlainText().strip(),
            "niche": self.niche.currentText().strip() or "tech",
        }
        r = seo.render(pid, fake_campaign, "morning-productivity-tips_014.mp4")
        lines = [f"<b>{r['title']}</b>  ({len(r['title'])} chars)"]
        if r["description"]:
            lines.append(f"{r['description'][:160].replace(chr(10), ' ')}…")
        if r["tags"]:
            lines.append(f"Tags: {', '.join('#' + t for t in r['tags'][:8])}")
        if pid != "youtube":
            lines.append(f"{r['caption'][:160].replace(chr(10), ' ')}…")
        self.preview.setHtml("<br>".join(lines))
        if r["warnings"]:
            self.warn_lbl.setText("⚠ " + " ".join(r["warnings"]))
            self.warn_lbl.setStyleSheet("color:#f0a35e;")
        else:
            self.warn_lbl.setText("✅ All best-practice checks pass.")
            self.warn_lbl.setStyleSheet("color:#3fd08c;")

    def values(self):
        return {
            "name": self.name.text().strip(),
            "platform": "YT Shorts",
            "niche": self.niche.currentText().strip().lower() or "tech",
            "source_folder": self.folder.text().strip(),
            "schedule_time": self.time.time().toString("HH:mm"),
            "caption_template": self.caption_tpl.toPlainText().strip(),
            "hashtags": self.hashtags.text().strip(),
            "title_template": self.title_tpl.text().strip(),
            "description_template": self.desc_tpl.toPlainText().strip(),
            "tags_template": self.tags_tpl.text().strip(),
            "active": 1 if self.active.isChecked() else 0,
        }


class Campaigns(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(h1("Campaigns"))
        head.addStretch()
        add = QPushButton("＋ New Campaign")
        add.clicked.connect(self._add)
        head.addWidget(add)
        lay.addLayout(head)
        lay.addWidget(muted("Manage & Launch — each campaign watches a folder and posts on its IST schedule."))

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Platform", "Time (IST)", "Source folder", "Active", "Created"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        lay.addWidget(self.table, 1)

        brow = QHBoxLayout()
        edit = QPushButton("Edit")
        edit.clicked.connect(self._edit)
        delete = QPushButton("Delete")
        delete.setObjectName("Danger")
        delete.clicked.connect(self._delete)
        toggle = QPushButton("Toggle Active")
        toggle.clicked.connect(self._toggle)
        brow.addWidget(edit)
        brow.addWidget(toggle)
        brow.addWidget(delete)
        brow.addStretch()
        lay.addLayout(brow)
        self.refresh()

    def _selected_id(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        return int(self.table.item(r, 0).text())

    def refresh(self):
        rows = self.app.db.query("SELECT * FROM campaigns ORDER BY id")
        self.table.setRowCount(len(rows))
        for i, c in enumerate(rows):
            vals = [c["id"], c["name"], c["platform"], c["schedule_time"],
                    c["source_folder"] or "—",
                    "✅" if c["active"] else "⏸️",
                    (c["created_at"] or "")[:10]]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, it)

    def _add(self):
        d = CampaignDialog(self)
        if d.exec():
            v = d.values()
            if not v["name"]:
                QMessageBox.warning(self, "Campaign", "Name is required.")
                return
            self.app.db.execute(
                "INSERT INTO campaigns(name,platform,source_folder,schedule_time,"
                "caption_template,hashtags,title_template,description_template,"
                "tags_template,niche,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (v["name"], v["platform"], v["source_folder"], v["schedule_time"],
                 v["caption_template"], v["hashtags"], v["title_template"],
                 v["description_template"], v["tags_template"], v["niche"],
                 v["active"], iso_ist(now_ist())))
            self.app.log.info("campaign created: %s", v["name"])
            self.refresh()

    def _edit(self):
        cid = self._selected_id()
        if cid is None:
            return
        data = self.app.db.query_one("SELECT * FROM campaigns WHERE id=?", (cid,))
        d = CampaignDialog(self, dict(data))
        if d.exec():
            v = d.values()
            self.app.db.execute(
                "UPDATE campaigns SET name=?,platform=?,source_folder=?,schedule_time=?,"
                "caption_template=?,hashtags=?,title_template=?,description_template=?,"
                "tags_template=?,niche=?,active=? WHERE id=?",
                (v["name"], v["platform"], v["source_folder"], v["schedule_time"],
                 v["caption_template"], v["hashtags"], v["title_template"],
                 v["description_template"], v["tags_template"], v["niche"],
                 v["active"], cid))
            self.app.log.info("campaign updated: %s", v["name"])
            self.refresh()

    def _delete(self):
        cid = self._selected_id()
        if cid is None:
            return
        if QMessageBox.question(self, "Delete", "Delete this campaign?") == QMessageBox.StandardButton.Yes:
            self.app.db.execute("DELETE FROM campaigns WHERE id=?", (cid,))
            self.app.log.info("campaign deleted: id=%d", cid)
            self.refresh()

    def _toggle(self):
        cid = self._selected_id()
        if cid is None:
            return
        self.app.db.execute("UPDATE campaigns SET active = 1 - active WHERE id=?", (cid,))
        self.refresh()
