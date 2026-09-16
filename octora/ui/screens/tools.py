"""Tools: caption generator, hashtag helper, best-time IST heatmap, bulk import."""
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QComboBox, QTextEdit, QTableWidget,
                             QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
                             QAbstractItemView, QSplitter)

from ...core.captions import generate_caption, hashtag_suggestions, best_time_heatmap
from ...core import metadata as seo
from ...core.drive_sync import scan_folder
from ..widgets import h1, h2, muted, Card, icon_button, h2_icon


class Tools(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        lay.addWidget(h1("Tools"))
        lay.addWidget(muted("Metadata & Utilities — everything runs locally, no internet needed."))

        split = QSplitter(Qt.Orientation.Vertical)

        # ---- caption generator ----
        gen = Card()
        gen.add(h2_icon("terminal", "Caption + Hashtag Generator"))
        row = QHBoxLayout()
        self.kw = QLineEdit()
        self.kw.setPlaceholderText("Keyword / topic, e.g. morning productivity")
        self.plat = QComboBox()
        self.plat.addItems(["YT Shorts"])
        go = QPushButton("Generate")
        go.clicked.connect(self._generate)
        copy = QPushButton("Copy")
        copy.clicked.connect(self._copy)
        row.addWidget(self.kw, 1)
        row.addWidget(self.plat)
        row.addWidget(go)
        row.addWidget(copy)
        gen.add(row)
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setFixedHeight(110)
        gen.add(self.out)
        hrow = QHBoxLayout()
        hrow.addWidget(QLabel("Topic tags (comma separated):"))
        self.tags_in = QLineEdit()
        self.tags_in.setPlaceholderText("fitness, motivation")
        htags = QPushButton("Get hashtags")
        htags.clicked.connect(self._hashtags)
        hrow.addWidget(self.tags_in, 1)
        hrow.addWidget(htags)
        gen.add(hrow)
        self.tags_out = QLineEdit()
        self.tags_out.setReadOnly(True)
        self.tags_out.setPlaceholderText("Hashtags will appear here…")
        gen.add(self.tags_out)
        split.addWidget(gen)

        # ---- SEO metadata lab (v1.2) ----
        lab = Card()
        lab.add(h2_icon("zap", "SEO Metadata Lab — test the upload-time engine"))
        lab.add(muted("This is exactly what the upload engine applies automatically: "
                      "keyword from filename, best-practice templates, warnings. "
                      "Rules-based — no AI claims."))
        lrow = QHBoxLayout()
        self.lab_file = QLineEdit()
        self.lab_file.setPlaceholderText("Video filename, e.g. morning-productivity-tips_014.mp4")
        self.lab_plat = QComboBox()
        self.lab_plat.addItems(["YT Shorts"])
        self.lab_niche = QComboBox()
        self.lab_niche.setEditable(True)
        self.lab_niche.addItems(sorted(seo.NICHE_BANKS.keys()))
        lgo = QPushButton("Render metadata")
        lgo.clicked.connect(self._lab_render)
        lrow.addWidget(self.lab_file, 1)
        lrow.addWidget(self.lab_plat)
        lrow.addWidget(self.lab_niche)
        lrow.addWidget(lgo)
        lab.add(lrow)
        self.lab_out = QTextEdit()
        self.lab_out.setReadOnly(True)
        self.lab_out.setFixedHeight(150)
        lab.add(self.lab_out)
        self.lab_warn = QLabel()
        self.lab_warn.setWordWrap(True)
        lab.add(self.lab_warn)
        split.addWidget(lab)

        # ---- heatmap ----
        heat = Card()
        heat.add(h2_icon("analytics", "Best time to post (IST) — from your history"))
        heat.add(muted("Darker = more of your past posts went out at that hour. Heuristic from local DB."))
        self.heat_table = QTableWidget(7, 24)
        self.heat_table.setHorizontalHeaderLabels([f"{h:02d}" for h in range(24)])
        self.heat_table.setVerticalHeaderLabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        self.heat_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.heat_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.heat_table.setFixedHeight(210)
        heat.add(self.heat_table)
        split.addWidget(heat)

        # ---- bulk import ----
        bulk = Card()
        bulk.add(h2_icon("upload", "Bulk import videos"))
        brow = QHBoxLayout()
        brow.addWidget(QLabel("Copy every video from a folder into the asset library:"))
        bgo = QPushButton("Choose folder…")
        bgo.clicked.connect(self._bulk)
        brow.addWidget(bgo)
        brow.addStretch()
        bulk.add(brow)
        split.addWidget(bulk)

        # ---- URL download ----
        dl = Card()
        dl.add(h2("⬇ Download from URL (yt-dlp)"))
        dl.add(muted("Paste video page URLs — they queue into the pipeline: download → "
                     "render → Drive → publish → cleanup. In live mode yt-dlp does the "
                     "real download; in demo mode it's simulated."))
        drow = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://… (one URL per line also works)")
        drow.addWidget(self.url_edit, 1)
        qbtn = QPushButton("Queue download")
        qbtn.clicked.connect(self._queue_dl)
        drow.addWidget(qbtn)
        dl.add(drow)
        self.dl_status = QLabel("")
        self.dl_status.setObjectName("Muted")
        dl.add(self.dl_status)
        split.addWidget(dl)

        lay.addWidget(split, 1)
        self._heatmap()

    def _generate(self):
        g = generate_caption(self.kw.text(), self.plat.currentText())
        self.out.setPlainText(g["caption"])

    def _copy(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.out.toPlainText())
        QMessageBox.information(self, "Tools", "Caption copied to clipboard.")

    def _hashtags(self):
        tags = hashtag_suggestions(self.tags_in.text(), self.plat.currentText())
        self.tags_out.setText(" ".join(tags))

    def _lab_render(self):
        from ...platforms import LABEL_TO_ID
        pid = LABEL_TO_ID.get(self.lab_plat.currentText(), "youtube")
        fname = self.lab_file.text().strip() or "my-video_001.mp4"
        niche = self.lab_niche.currentText().strip().lower() or "tech"
        r = seo.render(pid, {"niche": niche}, fname)
        lines = [f"TITLE ({len(r['title'])} chars):\n{r['title']}"]
        if r["description"]:
            lines.append(f"\nDESCRIPTION:\n{r['description'][:400]}")
        if r["tags"]:
            lines.append(f"\nTAGS: {', '.join(r['tags'])}")
        lines.append(f"\nCAPTION:\n{r['caption'][:400]}")
        self.lab_out.setPlainText("\n".join(lines))
        if r["warnings"]:
            self.lab_warn.setText("⚠ " + " ".join(r["warnings"]))
            self.lab_warn.setStyleSheet("color:#f0a35e;")
        else:
            self.lab_warn.setText("✅ All best-practice checks pass.")
            self.lab_warn.setStyleSheet("color:#3fd08c;")

    def _heatmap(self):
        grid = best_time_heatmap(self.app.db.posted_hours())
        mx = max((max(r) for r in grid), default=1) or 1
        for d in range(7):
            for hh in range(24):
                v = grid[d][hh]
                it = QTableWidgetItem(str(v) if v else "")
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # red glow intensity by value
                a = int(40 + 150 * v / mx) if v else 20
                it.setBackground(QColor(255, 59, 71, a if v else 18))
                self.heat_table.setItem(d, hh, it)

    def _queue_dl(self):
        urls = [u.strip() for u in self.url_edit.text().replace(",", "\n").splitlines()
                if u.strip()]
        if not urls:
            self.dl_status.setText("Paste at least one URL.")
            return
        n = 0
        for u in urls:
            if u.startswith("http"):
                self.app.engine.enqueue_download(u)
                n += 1
        self.url_edit.clear()
        self.dl_status.setText(f"Queued {n} download(s) — watch the ⬇ Download card on the Dashboard.")
        self.app.log.info("tools: queued %d download(s)", n)

    def _bulk(self):
        src = QFileDialog.getExistingDirectory(self, "Folder with videos")
        if not src:
            return
        dest = Path(self.app.cfg.get("asset_folder"))
        dest.mkdir(parents=True, exist_ok=True)
        from ...core.validators import VIDEO_EXTS
        n = 0
        for p in Path(src).iterdir():
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                try:
                    shutil.copy2(p, dest / p.name)
                    n += 1
                except OSError:
                    pass
        added, skipped = scan_folder(self.app.db, dest)
        QMessageBox.information(self, "Bulk import",
                                f"Copied {n} file(s).\nLibrary: {added} new, {skipped} duplicates skipped.")
        self.app.log.info("bulk import: %d copied, %d new assets", n, added)
