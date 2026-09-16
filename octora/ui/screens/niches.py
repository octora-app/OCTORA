"""Niches: Autopilot sources — per-niche stock-video fetching.

Each niche spreads `videos_per_day` evenly across 24h. The NicheScheduler
queues one fresh stock video per due interval into downloads; the pipeline
then runs download -> render -> drive -> publish -> cleanup untouched.
Mode 'auto' lets Gemini write metadata; 'manual' reuses your templates."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QDialog, QFormLayout,
                             QLineEdit, QTextEdit, QCheckBox, QSpinBox,
                             QDialogButtonBox, QHeaderView, QMessageBox,
                             QAbstractItemView, QGroupBox, QRadioButton, QScrollArea)

from ...core.database import iso_ist, now_ist
from ..widgets import h1, muted


class NicheDialog(QDialog):
    def __init__(self, parent, data=None):
        super().__init__(parent)
        self.setWindowTitle("Niche" if data is None else "Edit Niche")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        blay = QVBoxLayout(body)

        basic = QGroupBox("Basics")
        form = QFormLayout(basic)
        self.name = QLineEdit(data["name"] if data else "")
        self.name.setPlaceholderText("e.g. Motivation")
        srow = QHBoxLayout()
        self.st_stock = QRadioButton("Stock API — Pexels / Pixabay (legal, reliable)")
        self.st_links = QRadioButton("Social links — YouTube")
        if data and (data.get("source_type") or "stock") == "links":
            self.st_links.setChecked(True)
        else:
            self.st_stock.setChecked(True)
        srow.addWidget(self.st_stock)
        srow.addWidget(self.st_links)
        self.st_stock.toggled.connect(self._on_source)
        self.keywords_lbl = QLabel("Keywords")
        self.keywords = QLineEdit(data["keywords"] if data else "")
        self.keywords.setPlaceholderText("comma,separated,search terms (blank = niche name)")
        self.links_lbl = QLabel("Source links")
        self.links = QTextEdit((data["source_links"] if data else "") or "")
        self.links.setFixedHeight(84)
        self.links.setPlaceholderText(
            "One URL per line — video, channel, or playlist URLs:\n"
            "https://www.youtube.com/@somechannel\n"
            "https://www.youtube.com/watch?v=VIDEO_ID")
        self.disclaimer = QLabel("Only add content you have the right to repost.")
        self.disclaimer.setWordWrap(True)
        self.vpd = QSpinBox()
        self.vpd.setRange(1, 100)
        self.vpd.setValue(int(data["videos_per_day"]) if data else 5)
        mrow = QHBoxLayout()
        self.mode_auto = QRadioButton("Auto — Gemini writes title/description/tags/caption")
        self.mode_manual = QRadioButton("Manual — reuse my templates below for every video")
        if data and (data.get("mode") or "auto") == "manual":
            self.mode_manual.setChecked(True)
        else:
            self.mode_auto.setChecked(True)
        mrow.addWidget(self.mode_auto)
        mrow.addWidget(self.mode_manual)
        self.mode_auto.toggled.connect(self._on_mode)
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(True if not data else bool(data["enabled"]))
        form.addRow("Name", self.name)
        form.addRow("Source", srow)
        form.addRow(self.keywords_lbl, self.keywords)
        form.addRow(self.links_lbl, self.links)
        form.addRow("", self.disclaimer)
        form.addRow("Videos / day", self.vpd)
        form.addRow("Mode", mrow)
        form.addRow("", self.enabled)
        blay.addWidget(basic)

        self.mgroup = QGroupBox("Manual templates — applied to every video in this niche")
        mlay = QVBoxLayout(self.mgroup)
        mlay.addWidget(QLabel("Variables: {niche} {date} {index} {filename} {keyword}"))
        mform = QFormLayout()
        self.mtitle = QLineEdit(data["manual_title"] if data else "")
        self.mtitle.setPlaceholderText("{keyword} | Daily {niche} #{index}")
        self.mdesc = QTextEdit((data["manual_description"] if data else "") or "")
        self.mdesc.setFixedHeight(56)
        self.mtags = QLineEdit(data["manual_tags"] if data else "")
        self.mtags.setPlaceholderText("motivation, mindset, {keyword}")
        self.mcap = QTextEdit((data["manual_caption"] if data else "") or "")
        self.mcap.setFixedHeight(56)
        mform.addRow("Title", self.mtitle)
        mform.addRow("Description", self.mdesc)
        mform.addRow("Tags", self.mtags)
        mform.addRow("Caption", self.mcap)
        mlay.addLayout(mform)
        blay.addWidget(self.mgroup)
        self._on_mode()
        self._on_source()

        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_source(self):
        is_links = self.st_links.isChecked()
        for w in (self.links_lbl, self.links, self.disclaimer):
            w.setVisible(is_links)
        for w in (self.keywords_lbl, self.keywords):
            w.setVisible(not is_links)

    def _on_mode(self):
        self.mgroup.setVisible(self.mode_manual.isChecked())

    def values(self):
        return {
            "name": self.name.text().strip(),
            "keywords": self.keywords.text().strip(),
            "videos_per_day": self.vpd.value(),
            "mode": "manual" if self.mode_manual.isChecked() else "auto",
            "source_type": "links" if self.st_links.isChecked() else "stock",
            "source_links": self.links.toPlainText().strip(),
            "manual_title": self.mtitle.text().strip(),
            "manual_description": self.mdesc.toPlainText().strip(),
            "manual_tags": self.mtags.text().strip(),
            "manual_caption": self.mcap.toPlainText().strip(),
            "enabled": 1 if self.enabled.isChecked() else 0,
        }


class Niches(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(h1("Niches"))
        head.addStretch()
        add = QPushButton("＋ New Niche")
        add.clicked.connect(self._add)
        head.addWidget(add)
        lay.addLayout(head)
        lay.addWidget(muted(
            "Autopilot sources — each enabled niche auto-fetches videos "
            "(Stock API: Pexels → Pixabay, or your own Social links), uploads "
            "them to Drive, posts them, then cleans up. No duplicates, ever."))

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Source", "Keywords / Links", "Videos/day",
             "Mode", "Enabled", "Last run"])
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
        toggle = QPushButton("Toggle Enabled")
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
        rows = self.app.db.list_niches()
        self.table.setRowCount(len(rows))
        for i, n in enumerate(rows):
            last = (n["last_run"] or "")[:16].replace("T", " ")
            stype = (n.get("source_type") or "stock")
            if stype == "links":
                first_link = ((n.get("source_links") or "").splitlines() or ["—"])[0]
                srctext = first_link[:44]
            else:
                srctext = (n["keywords"] or "—")[:44]
            vals = [n["id"], n["name"], stype, srctext,
                    n["videos_per_day"], n["mode"],
                    "✅" if n["enabled"] else "⏸️",
                    last or "never"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, it)

    def _add(self):
        d = NicheDialog(self)
        if d.exec():
            v = d.values()
            if not v["name"]:
                QMessageBox.warning(self, "Niche", "Name is required.")
                return
            try:
                self.app.db.execute(
                    "INSERT INTO niches(name,keywords,videos_per_day,mode,manual_title,"
                    "manual_description,manual_tags,manual_caption,source_type,"
                    "source_links,enabled,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (v["name"], v["keywords"], v["videos_per_day"], v["mode"],
                     v["manual_title"], v["manual_description"], v["manual_tags"],
                     v["manual_caption"], v["source_type"], v["source_links"],
                     v["enabled"], iso_ist(now_ist())))
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Niche", f"Could not save: {e}")
                return
            self.app.log.info("niche created: %s (%d/day, %s, %s)",
                              v["name"], v["videos_per_day"], v["mode"],
                              v["source_type"])
            self.refresh()

    def _edit(self):
        nid = self._selected_id()
        if nid is None:
            return
        data = self.app.db.get_niche(nid)
        d = NicheDialog(self, data)
        if d.exec():
            v = d.values()
            if not v["name"]:
                QMessageBox.warning(self, "Niche", "Name is required.")
                return
            try:
                self.app.db.execute(
                    "UPDATE niches SET name=?,keywords=?,videos_per_day=?,mode=?,"
                    "manual_title=?,manual_description=?,manual_tags=?,"
                    "manual_caption=?,source_type=?,source_links=?,enabled=? WHERE id=?",
                    (v["name"], v["keywords"], v["videos_per_day"], v["mode"],
                     v["manual_title"], v["manual_description"], v["manual_tags"],
                     v["manual_caption"], v["source_type"], v["source_links"],
                     v["enabled"], nid))
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Niche", f"Could not save: {e}")
                return
            self.app.log.info("niche updated: %s", v["name"])
            self.refresh()

    def _delete(self):
        nid = self._selected_id()
        if nid is None:
            return
        data = self.app.db.get_niche(nid)
        name = data["name"] if data else nid
        if QMessageBox.question(self, "Delete",
                                f"Delete niche '{name}'?\nAlready-downloaded videos are kept.") \
                == QMessageBox.StandardButton.Yes:
            self.app.db.execute("DELETE FROM niches WHERE id=?", (nid,))
            self.app.log.info("niche deleted: %s", name)
            self.refresh()

    def _toggle(self):
        nid = self._selected_id()
        if nid is None:
            return
        self.app.db.execute("UPDATE niches SET enabled = 1 - enabled WHERE id=?", (nid,))
        self.refresh()
