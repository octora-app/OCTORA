"""Logs: live viewer over the app_logs table."""
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QPlainTextEdit)

from ..widgets import h1, muted


class Logs(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(h1("Logs"))
        head.addStretch()
        head.addWidget(QLabel("Level:"))
        self.level = QComboBox()
        self.level.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.level.currentIndexChanged.connect(self.refresh)
        head.addWidget(self.level)
        clear = QPushButton("Clear view")
        clear.clicked.connect(lambda: self.view.clear())
        head.addWidget(clear)
        lay.addLayout(head)
        lay.addWidget(muted("System Activity — every worker and action writes here in real time."))
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setStyleSheet("font-family: 'Consolas','Cascadia Mono',monospace; font-size: 12px;")
        lay.addWidget(self.view, 1)
        self._last_id = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1500)

    def _poll(self):
        if not self.isVisible():
            return
        lvl = self.level.currentText()
        if lvl == "ALL":
            rows = self.app.db.query("SELECT * FROM app_logs WHERE id>? ORDER BY id", (self._last_id,))
        else:
            rows = self.app.db.query("SELECT * FROM app_logs WHERE id>? AND level=? ORDER BY id",
                                     (self._last_id, lvl))
        for r in rows:
            self._last_id = max(self._last_id, r["id"])
            color = {"ERROR": "#ff3b47", "WARNING": "#f5a623",
                     "INFO": "#eef1f4", "DEBUG": "#8b95a3"}.get(r["level"], "#eef1f4")
            self.view.appendHtml(
                f'<span style="color:#8b95a3">{r["at"][11:19]}</span> '
                f'<span style="color:{color};font-weight:bold">[{r["level"]}]</span> '
                f'<span style="color:#22d3ee">{r["source"]}</span> '
                f'<span style="color:{color}">{r["message"]}</span>')
        if rows:
            self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def refresh(self):
        self._last_id = 0
        self.view.clear()
        self._poll()
