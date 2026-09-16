"""Buy-license dialog: pay with USDT (TRC-20), auto-verify, auto-activate.

Flow
----
1. User picks a plan (7-Day / 30-Day / Lifetime).
2. User sends the EXACT USDT amount to the seller's TRC-20 address
   (shown with a QR code).
3. User pastes the Tron transaction ID (TXID) + name/email, taps
   "Verify payment & activate".
4. The app POSTs to <admin_server>/api/v1/pay/verify. The server checks the
   transfer on-chain, mints an HWID-bound license, and returns it — the app
   installs it immediately. Each TXID works exactly once.
"""
import json
import urllib.request

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QMessageBox, QApplication, QRadioButton,
                             QButtonGroup)

from ..core.config import resource_path
from ..core.license import LicenseManager, hwid
from .widgets import svg_label, icon_button

# Fallback plans when the server can't be reached (kept in sync with the
# admin panel's PLANS). Prices are in USDT on the TRC-20 network.
FALLBACK_PLANS = [
    {"id": "weekly", "name": "7-Day", "days": 7, "price_usdt": 10.0},
    {"id": "monthly", "name": "30-Day", "days": 30, "price_usdt": 30.0},
    {"id": "lifetime", "name": "Lifetime", "days": 36500, "price_usdt": 100.0},
]
FALLBACK_ADDRESS = "TVTjQKqYuntgk6EfD6PqeFvezZnVCCimjz"


def _post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "OCTORA-app"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url: str, timeout: int = 12) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


class BuyDialog(QDialog):
    def __init__(self, lm: LicenseManager, parent=None):
        super().__init__(parent)
        self.lm = lm
        self.setWindowTitle("OCTORA — Buy license")
        self.setMinimumWidth(600)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        trow = QHBoxLayout()
        trow.addWidget(svg_label("brand/octora-logo", 40))
        t = QLabel("Buy OCTORA license")
        t.setObjectName("PipeTitle")
        trow.addWidget(t, 1)
        lay.addLayout(trow)

        lay.addWidget(QLabel("<b>Step 1 — pick a plan</b> (1 license = 1 PC):"))
        self.plan_group = QButtonGroup(self)
        # Build instantly with fallback plans; the server list (prices,
        # seller address) refreshes asynchronously so the dialog never
        # freezes on open.
        from ..core import telemetry
        self.server_url = telemetry.server_url(self.lm.cfg)
        self.seller_address = FALLBACK_ADDRESS
        self.plans_box = QVBoxLayout()
        self.plans_box.setSpacing(2)
        lay.addLayout(self.plans_box)
        self.plan_rows = []
        self._build_plan_rows(FALLBACK_PLANS)
        self._load_plans_async()

        lay.addWidget(QLabel("<b>Step 2 — send USDT (TRC-20 network ONLY)</b> "
                             "to this address:"))
        addr_row = QHBoxLayout()
        self.addr_edit = QLineEdit(self.seller_address)
        self.addr_edit.setReadOnly(True)
        copy = QPushButton("Copy")
        copy.clicked.connect(self._copy_addr)
        addr_row.addWidget(self.addr_edit, 1)
        addr_row.addWidget(copy)
        lay.addLayout(addr_row)

        qr_path = resource_path("octora/assets/qr-trc20.png")
        pm = QPixmap(qr_path)
        if not pm.isNull():
            qr_lbl = QLabel()
            qr_lbl.setPixmap(pm.scaledToHeight(170,
                             Qt.TransformationMode.SmoothTransformation))
            qr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(qr_lbl)
        warn = QLabel("Only send USDT on the TRC-20 (Tron) network. "
                      "Any other network or token will be lost.")
        warn.setWordWrap(True)
        warn.setObjectName("MutedLabel")
        lay.addWidget(warn)

        lay.addWidget(QLabel("<b>Step 3 — paste your payment details:</b>"))
        form_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Your name")
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Email (for support)")
        form_row.addWidget(self.name_edit, 1)
        form_row.addWidget(self.email_edit, 1)
        lay.addLayout(form_row)
        self.txid_edit = QLineEdit()
        self.txid_edit.setPlaceholderText("Tron transaction ID (TXID, 64 characters)")
        lay.addWidget(self.txid_edit)

        brow = QHBoxLayout()
        verify = icon_button("Verify payment & activate", "check")
        verify.setObjectName("RedButton")
        verify.clicked.connect(self._verify)
        self.verify_btn = verify
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        brow.addWidget(verify)
        brow.addStretch()
        brow.addWidget(close)
        lay.addLayout(brow)
        self._verify_thread = None
        self._verify_worker = None
        self._plans_thread = None
        self._plans_worker = None
        self._dismissed = False

    def done(self, result):
        self._dismissed = True
        super().done(result)

    def _build_plan_rows(self, plans):
        # Clear any previous rows (async server refresh).
        while self.plans_box.count():
            item = self.plans_box.takeAt(0)
            if item.widget():
                self.plan_group.removeButton(item.widget())
                item.widget().deleteLater()
        self.plan_rows = []
        for i, p in enumerate(plans):
            rb = QRadioButton(f"{p['name']}  —  {p['price_usdt']:g} USDT")
            rb.setProperty("plan_id", p["id"])
            self.plan_group.addButton(rb, i)
            if i == 1:
                rb.setChecked(True)
            self.plans_box.addWidget(rb)
            self.plan_rows.append((rb, p))

    # ---- data ----
    def _load_plans_async(self):
        url = self.server_url
        if not url:
            return
        from PyQt6.QtCore import QThread, QObject, pyqtSignal

        class _PlansWorker(QObject):
            done = pyqtSignal(dict)

            def run(self):
                data = _get_json(url + "/api/v1/plans") or {}
                self.done.emit(data if isinstance(data, dict) else {})

        self._plans_thread = QThread(self)
        worker = _PlansWorker()
        self._plans_worker = worker  # strong ref (see _verify)
        worker.moveToThread(self._plans_thread)
        self._plans_thread.started.connect(worker.run)
        worker.done.connect(self._on_plans_done)
        worker.done.connect(self._plans_thread.quit)
        worker.done.connect(worker.deleteLater)
        self._plans_thread.finished.connect(self._plans_thread.deleteLater)
        self._plans_thread.start()

    def _on_plans_done(self, data: dict):
        self._plans_thread = None
        self._plans_worker = None
        if self._dismissed:
            return
        plans = data.get("plans") if isinstance(data, dict) else None
        if plans:
            self._build_plan_rows(plans)
        addr = data.get("seller_address") if isinstance(data, dict) else None
        if addr:
            self.seller_address = addr
            self.addr_edit.setText(addr)

    def _selected_plan(self):
        for rb, p in self.plan_rows:
            if rb.isChecked():
                return p
        return self.plan_rows[0][1]

    def _copy_addr(self):
        QApplication.clipboard().setText(self.seller_address)
        QMessageBox.information(self, "Copied",
                                "Payment address copied to clipboard.")

    # ---- verify ----
    def _verify(self):
        plan = self._selected_plan()
        txid = self.txid_edit.text().strip()
        if len(txid) != 64:
            QMessageBox.warning(self, "Buy license",
                                "Paste the full Tron transaction ID (64 characters).")
            return
        if not self.server_url:
            QMessageBox.warning(
                self, "Buy license",
                "No license server is configured in this build, so automatic "
                "payment verification is unavailable.\n\n"
                "Send the TXID to the seller on Telegram (t.me/batmanjaatwhop) "
                "and you'll receive your license key there.")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        # Verify off the UI thread — the on-chain check can take up to 45s and
        # must never freeze the window.
        self.verify_btn.setEnabled(False)
        self.verify_btn.setText("Verifying payment…")
        payload = {"txid": txid, "plan": plan["id"],
                   "hwid": hwid(),
                   "name": self.name_edit.text().strip(),
                   "email": self.email_edit.text().strip()}
        url = self.server_url + "/api/v1/pay/verify"

        from PyQt6.QtCore import QThread, QObject, pyqtSignal

        class _VerifyWorker(QObject):
            done = pyqtSignal(dict)

            def run(self):
                try:
                    res = _post_json(url, payload, timeout=45)
                except Exception as e:  # noqa: BLE001
                    res = {"_error": f"Could not verify the payment:\n{e}\n\n"
                                     "If the money left your wallet, wait a minute "
                                     "and try again — or contact support on Telegram."}
                self.done.emit(res if isinstance(res, dict) else {"_error": str(res)})

        self._verify_thread = QThread(self)
        worker = _VerifyWorker()
        self._verify_worker = worker  # strong ref: a local would be GC'd and
        worker.moveToThread(self._verify_thread)  # the thread would never run
        self._verify_thread.started.connect(worker.run)
        worker.done.connect(self._on_verify_done)
        worker.done.connect(self._verify_thread.quit)
        worker.done.connect(worker.deleteLater)
        self._verify_thread.finished.connect(self._verify_thread.deleteLater)
        self._verify_thread.start()

    def _on_verify_done(self, res: dict):
        QApplication.restoreOverrideCursor()
        self.verify_btn.setEnabled(True)
        self.verify_btn.setText("Verify payment & activate")
        self._verify_thread = None
        self._verify_worker = None
        if self._dismissed:
            return  # user closed the dialog mid-verification; stay silent
        if res.get("_error"):
            QMessageBox.warning(self, "Buy license", res["_error"])
            return
        if not res.get("ok"):
            QMessageBox.warning(self, "Buy license",
                                res.get("message", "Payment verification failed."))
            return
        ok, msg = self.lm.activate(res["armored"])
        if ok:
            QMessageBox.information(
                self, "Activated",
                f"Payment verified ({res.get('amount_usdt')} USDT).\n\n{msg}")
            self.accept()
        else:
            QMessageBox.warning(self, "License",
                                f"Payment was verified, but the license could not "
                                f"be installed:\n{msg}\n\n"
                                f"Save this key and contact support:\n\n{res['armored'][:120]}…")
