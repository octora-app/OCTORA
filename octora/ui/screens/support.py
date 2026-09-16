"""Support screen — contact the seller on Telegram."""
import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QApplication)

from ..widgets import Card, muted, icon_button, h2_icon, h1_icon

TELEGRAM_URL = "https://t.me/batmanjaatwhop"
TELEGRAM_USER = "@batmanjaatwhop"


class Support(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.addLayout(h1_icon("info", "Support"))
        head.addStretch()
        root.addLayout(head)
        root.addWidget(muted("Questions about setup, licenses, or anything else — "
                             "reach us directly on Telegram."))

        card = Card()
        card.add(h2_icon("external", "Contact us on Telegram"))
        card.add(muted("Fastest response — usually within a few hours.\n"
                       "Tip: include your HWID (Settings → License) and a screenshot "
                       "so we can help you faster."))

        row = QHBoxLayout()
        open_btn = icon_button("Open Telegram Chat", "external")
        open_btn.setMinimumHeight(46)
        open_btn.clicked.connect(lambda: webbrowser.open(TELEGRAM_URL))
        row.addWidget(open_btn, 1)
        card.add(row)

        urow = QHBoxLayout()
        user_lbl = QLabel(f"<b>{TELEGRAM_USER}</b>")
        user_lbl.setTextInteractionFlags(
            user_lbl.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
        urow.addWidget(user_lbl)
        copy_btn = QPushButton("Copy username")
        copy_btn.clicked.connect(self._copy_username)
        urow.addWidget(copy_btn)
        urow.addStretch()
        card.add(urow)

        self._copied = QLabel("")
        self._copied.setObjectName("Muted")
        card.add(self._copied)

        root.addWidget(card)
        root.addStretch()

    def _copy_username(self):
        QApplication.clipboard().setText(TELEGRAM_USER)
        self._copied.setText("✅ Username copied — paste it in Telegram search.")
        self.app.log.info("support username copied to clipboard")
