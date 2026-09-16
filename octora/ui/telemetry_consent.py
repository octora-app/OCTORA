"""First-run telemetry consent dialog (v1.3 admin panel).

Plain-language opt-in. Shown ONCE — only when the seller has configured a
server URL and the user hasn't made a choice yet. Declining sets the master
flag to False, which guarantees zero network calls from telemetry.
"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from .widgets import svg_label


def maybe_ask_consent(cfg, parent=None) -> bool:
    """Ask once if needed. Returns the stored consent value."""
    try:
        if cfg.get("telemetry_consent", False):
            return True  # already allowed
        if str(cfg.get("consent_asked", "")).strip() == "1":
            return False  # already declined once
        if not (cfg.get("admin_server_url", "") or "").strip():
            return False  # seller hasn't set up the admin server — nothing to ask
    except Exception:
        return False
    dlg = _ConsentDialog(parent)
    allowed = dlg.exec() == QDialog.DialogCode.Accepted
    try:
        cfg.set("telemetry_consent", bool(allowed))
        cfg.set("consent_asked", "1")
    except Exception:
        pass
    return allowed


class _ConsentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OCTORA — Help & monitoring")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        trow = QHBoxLayout()
        trow.addWidget(svg_label("info", 24))
        t = QLabel("Help &amp; monitoring")
        t.setObjectName("PipeTitle")
        trow.addWidget(t, 1)
        lay.addLayout(trow)

        body = QLabel(
            "May OCTORA send <b>anonymous usage stats</b> to your seller's server "
            "so support can help you faster?<br><br>"
            "• <b>Sent:</b> app version, connected platforms (e.g. YouTube channel "
            "name, subscriber count), upload counts.<br>"
            "• <b>Never sent:</b> your videos, files, passwords or personal data.<br>"
            "• You can turn this <b>off anytime</b> in Settings → Seller connection.<br><br>"
            "Full details: <b>PRIVACY.md</b> (in the app folder).")
        body.setWordWrap(True)
        lay.addWidget(body)

        row = QHBoxLayout()
        row.addStretch()
        no = QPushButton("Don't allow")
        no.clicked.connect(self.reject)
        yes = QPushButton("Allow")
        yes.setObjectName("RedButton")
        yes.clicked.connect(self.accept)
        row.addWidget(no)
        row.addWidget(yes)
        lay.addLayout(row)
