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
        plans, self.seller_address, self.server_url = self._load_plans()
        self.plan_rows = []
        for i, p in enumerate(plans):
            rb = QRadioButton(f"{p['name']}  —  {p['price_usdt']:g} USDT")
            rb.setProperty("plan_id", p["id"])
            self.plan_group.addButton(rb, i)
            if i == 1:
                rb.setChecked(True)
            lay.addWidget(rb)
            self.plan_rows.append((rb, p))

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
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        brow.addWidget(verify)
        brow.addStretch()
        brow.addWidget(close)
        lay.addLayout(brow)

    # ---- data ----
    def _load_plans(self):
        from ..core import telemetry
        url = telemetry.server_url(self.lm.cfg)
        if url:
            data = _get_json(url + "/api/v1/plans")
            if data and data.get("plans"):
                return data["plans"], data.get("seller_address", FALLBACK_ADDRESS), url
        return FALLBACK_PLANS, FALLBACK_ADDRESS, url

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
        try:
            res = _post_json(self.server_url + "/api/v1/pay/verify",
                             {"txid": txid, "plan": plan["id"],
                              "hwid": hwid(),
                              "name": self.name_edit.text().strip(),
                              "email": self.email_edit.text().strip()},
                             timeout=45)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Buy license",
                                f"Could not verify the payment:\n{e}\n\n"
                                "If the money left your wallet, wait a minute "
                                "and try again — or contact support on Telegram.")
            return
        QApplication.restoreOverrideCursor()
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
