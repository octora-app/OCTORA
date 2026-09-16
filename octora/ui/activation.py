"""License activation dialog — shown when no valid license/trial is present."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTextEdit, QMessageBox)

from ..core.license import LicenseManager, hwid
from .widgets import svg_label, icon_button


class ActivationDialog(QDialog):
    def __init__(self, lm: LicenseManager, parent=None):
        super().__init__(parent)
        self.lm = lm
        self.setWindowTitle("OCTORA — Activation")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        trow = QHBoxLayout()
        trow.addWidget(svg_label("brand/octora-logo", 44))
        t = QLabel("OCTORA Activation")
        t.setObjectName("PipeTitle")
        trow.addWidget(t, 1)
        lay.addLayout(trow)
        lay.addWidget(QLabel("OCTORA needs a license. Start the free 1-day trial, "
                             "buy a subscription with USDT, "
                             "or paste a license key from your seller."))

        hw = QLabel(f"Your machine HWID:  <b>{hwid()}</b><br>"
                    "Send this HWID to the seller to receive your license file.")
        hw.setWordWrap(True)
        hw.setTextInteractionFlags(hw.textInteractionFlags() |
                                   Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(hw)

        lay.addWidget(QLabel("<b>Paste license key:</b>"))
        self.key_edit = QTextEdit()
        self.key_edit.setPlaceholderText("-----BEGIN OCTORA LICENSE-----\n…\n-----END OCTORA LICENSE-----")
        self.key_edit.setMaximumHeight(130)
        lay.addWidget(self.key_edit)

        brow = QHBoxLayout()
        trial = icon_button("Start 1-day free trial", "zap")
        trial.clicked.connect(self._start_trial)
        buy = icon_button("Buy license (USDT)", "shield")
        buy.setObjectName("RedButton")
        buy.clicked.connect(self._buy)
        activate = icon_button("Activate license", "lock")
        activate.clicked.connect(self._activate)
        online = icon_button("Activate online", "globe")
        online.setToolTip("Activate with a license key emailed by your seller — "
                          "validated against the seller's server.")
        online.clicked.connect(self._activate_online)
        self._online_btn = online
        quit_ = QPushButton("Quit")
        quit_.clicked.connect(self.reject)
        brow.addWidget(trial)
        brow.addWidget(buy)
        brow.addWidget(activate)
        brow.addWidget(online)
        brow.addStretch()
        brow.addWidget(quit_)
        lay.addLayout(brow)
        self._online_thread = None
        self._online_worker = None
        self._dismissed = False

    def done(self, result):
        self._dismissed = True
        super().done(result)

    def _start_trial(self):
        if self.lm._trial_hours_left() is not None:
            QMessageBox.warning(self, "Trial", "A trial was already used on this machine.")
            return
        if not self.lm.start_trial():
            QMessageBox.warning(
                self, "Trial",
                "This PC has already used its free 1-day trial.\n\n"
                "Please purchase a license to continue using OCTORA.")
            return
        QMessageBox.information(self, "Trial", "1-day trial started — full features unlocked.")
        self.accept()

    def _buy(self):
        from .buy_dialog import BuyDialog
        dlg = BuyDialog(self.lm, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.accept()

    def _activate(self):
        text = self.key_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "License", "Paste your license key first.")
            return
        ok, msg = self.lm.activate(text)
        QMessageBox.information(self, "License", msg) if ok else \
            QMessageBox.warning(self, "License", msg)
        if ok:
            self.accept()

    def _activate_online(self):
        """Online activation against the seller's admin server (optional)."""
        text = self.key_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "License", "Paste your license key first.")
            return
        from ..core import telemetry
        url = telemetry.server_url(self.lm.cfg)
        if not url:
            QMessageBox.warning(
                self, "Online activation",
                "No admin server URL is configured.\n"
                "Ask your seller for the server address, or use file activation.")
            return
        # Network call off the UI thread — the 25s timeout must not freeze
        # the dialog.
        self._online_btn.setEnabled(False)
        self._online_btn.setText("Contacting server…")
        from PyQt6.QtCore import QThread, QObject, pyqtSignal

        class _ActivateWorker(QObject):
            done = pyqtSignal(dict)

            def run(self):
                try:
                    import hashlib, json, urllib.request
                    payload = {"license": text,
                               "hwid_hash": hashlib.sha256(hwid().encode("utf-8")).hexdigest()}
                    req = urllib.request.Request(
                        url + "/api/v1/license/activate",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=25) as r:
                        res = json.loads(r.read().decode("utf-8"))
                    self.done.emit(res if isinstance(res, dict) else {"_error": str(res)})
                except Exception as e:  # noqa: BLE001 — never crash on network issues
                    self.done.emit({"_error": f"Could not reach the seller's server:\n{e}\n\n"
                                              "Try again later, or use file activation instead."})

        self._online_thread = QThread(self)
        worker = _ActivateWorker()
        self._online_worker = worker  # strong ref (see buy_dialog)
        worker.moveToThread(self._online_thread)
        self._online_thread.started.connect(worker.run)
        worker.done.connect(self._on_online_done)
        worker.done.connect(self._online_thread.quit)
        worker.done.connect(worker.deleteLater)
        self._online_thread.finished.connect(self._online_thread.deleteLater)
        self._online_thread.start()

    def _on_online_done(self, res: dict):
        self._online_btn.setEnabled(True)
        self._online_btn.setText("Activate online")
        self._online_thread = None
        self._online_worker = None
        if self._dismissed:
            return
        if res.get("_error"):
            QMessageBox.warning(self, "Online activation", res["_error"])
            return
        if res.get("ok"):
            ok, msg = self.lm.activate(self.key_edit.toPlainText().strip())
            (QMessageBox.information if ok else QMessageBox.warning)(self, "License", msg)
            if ok:
                self.accept()
        else:
            QMessageBox.warning(self, "Online activation",
                                res.get("message", "Activation refused by the server."))

    @staticmethod
    def ensure_licensed(lm: LicenseManager) -> bool:
        """Returns True if the app may start. Shows dialog when needed."""
        import os
        st = lm.status()
        if st["mode"] in ("licensed", "trial", "grace"):
            return True
        if os.environ.get("OCTORA_AUTO_TRIAL") == "1":
            # CI / headless testing convenience (documented in README)
            if lm._trial_hours_left() is None:
                lm.start_trial()
            return True
        dlg = ActivationDialog(lm)
        return dlg.exec() == QDialog.DialogCode.Accepted
