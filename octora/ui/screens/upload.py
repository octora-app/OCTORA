"""Upload Engine: live queue table, pause/resume/cancel, retries, dead-letter list."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QMessageBox, QFileDialog, QTabWidget)

from ...core.reports import export_queue_csv, export_uploads_csv
from ..widgets import h1, muted, h2


class UploadEngine(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(h1("Upload Engine"))
        head.addStretch()
        self.pause_btn = QPushButton("⏸ Pause all")
        self.pause_btn.clicked.connect(self._toggle_pause)
        head.addWidget(self.pause_btn)
        lay.addLayout(head)
        mode = "DEMO MODE — simulated uploads" if app.cfg.demo_mode else "LIVE MODE — real provider calls"
        ml = QLabel(mode)
        ml.setObjectName("Badge")
        ml.setProperty("color", "amber" if app.cfg.demo_mode else "green")
        lay.addWidget(ml)
        lay.addWidget(muted("Bulk Upload & Queue — exponential-backoff retries, dead-letter list, priority ordering."))

        self.tabs = QTabWidget()
        self.qtable = self._make_table(["ID", "Platform", "Asset", "Prio", "Status", "Attempts",
                                       "Next retry", "Last error"])
        self.dtable = self._make_table(["ID", "Platform", "Asset", "Attempts", "Last error", "Failed at"])
        self.tabs.addTab(self.qtable, "Active Queue")
        self.tabs.addTab(self.dtable, "☠ Dead Letter")
        lay.addWidget(self.tabs, 1)

        brow = QHBoxLayout()
        for label, fn in [("⏩ Retry now", self._retry), ("▶ Resume", self._resume),
                          ("⏸ Pause item", self._pause_item), ("✖ Cancel", self._cancel)]:
            b = QPushButton(label)
            b.clicked.connect(fn)
            brow.addWidget(b)
        brow.addStretch()
        exp = QPushButton("⬇ Export CSV")
        exp.clicked.connect(self._export)
        brow.addWidget(exp)
        lay.addLayout(brow)
        self.refresh()

    def _make_table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        return t

    def _sel(self, table):
        r = table.currentRow()
        return int(table.item(r, 0).text()) if r >= 0 else None

    def refresh(self):
        act = self.app.db.query(
            """SELECT q.*, a.filename FROM upload_queue q LEFT JOIN assets a ON a.id=q.asset_id
               WHERE q.status IN ('queued','uploading','paused') ORDER BY q.priority DESC, q.id""")
        self._fill(self.qtable, act, active=True)
        dead = self.app.db.query(
            """SELECT q.*, a.filename FROM upload_queue q LEFT JOIN assets a ON a.id=q.asset_id
               WHERE q.status IN ('dead','failed','cancelled') ORDER BY q.id DESC LIMIT 200""")
        self._fill(self.dtable, dead, active=False)
        self.pause_btn.setText("▶ Resume all" if self.app.engine.upload_paused else "⏸ Pause all")

    def _fill(self, table, rows, active):
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            name = r["filename"] or f"clip_{r['id']:04d}.mp4"
            if active:
                vals = [r["id"], r["platform"], name, r["priority"], r["status"],
                        r["attempts"], (r["next_retry_at"] or "—")[:16].replace("T", " "),
                        (r["last_error"] or "")[:50]]
            else:
                vals = [r["id"], r["platform"], name, r["attempts"],
                        (r["last_error"] or "")[:60], (r["updated_at"] or "")[:16].replace("T", " ")]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(i, j, it)

    def _toggle_pause(self):
        eng = self.app.engine
        eng.set_paused(not eng.upload_paused)
        self.refresh()

    def _retry(self):
        qid = self._sel(self.dtable if self.tabs.currentIndex() == 1 else self.qtable)
        if qid:
            self.app.engine.retry_item(qid)
            self.app.log.info("queue item %d requeued", qid)
            self.refresh()

    def _resume(self):
        qid = self._sel(self.qtable)
        if qid:
            self.app.engine.resume_item(qid)
            self.refresh()

    def _pause_item(self):
        qid = self._sel(self.qtable)
        if qid:
            self.app.engine.pause_item(qid)
            self.refresh()

    def _cancel(self):
        qid = self._sel(self.qtable)
        if qid and QMessageBox.question(self, "Cancel", f"Cancel upload #{qid}?") == QMessageBox.StandardButton.Yes:
            self.app.engine.cancel_item(qid)
            self.refresh()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export queue CSV", "octora-queue.csv",
                                              "CSV (*.csv)")
        if path:
            export_queue_csv(self.app.db, path)
            export_uploads_csv(self.app.db, path.replace("queue", "uploads"))
            QMessageBox.information(self, "Export", f"Saved:\n{path}")
