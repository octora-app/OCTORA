"""Settings: demo/live toggle, pipeline, folders, API credentials, license, theme."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QFormLayout, QFileDialog, QComboBox, QCheckBox,
                             QMessageBox, QScrollArea)

from ...core.license import LicenseManager
from ..activation import ActivationDialog
from ..widgets import h1, muted, Card, h2, icon_button, h2_icon


class Settings(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(h1("Settings"))
        head.addStretch()
        save = icon_button("Save all", "check")
        save.clicked.connect(self._save)
        head.addWidget(save)
        outer.addLayout(head)
        outer.addWidget(muted("Preferences — credentials are stored only in your local config file, never hardcoded."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(10)

        # ---- mode ----
        mode = Card()
        mode.add(h2("⚙ Operation Mode"))
        self.demo = QCheckBox("Demo mode (simulate the full pipeline — recommended until credentials are added)")
        self.demo.setChecked(app.cfg.demo_mode)
        mode.add(self.demo)
        mode.add(muted("Live mode attempts real provider calls:\n"
                       "• Google Drive upload — REAL (one-click Connect, OAuth).\n"
                       "• YouTube Shorts upload — REAL (one-click Connect, OAuth).\n"
                       "• Instagram / TikTok / Facebook — connect with one click; "
                       "provider posting calls are honest stubs in v1.2 and report "
                       "exactly what is missing."))
        lay.addWidget(mode)

        # ---- pipeline automation ----
        pipe = Card()
        pipe.add(h2_icon("cpu", "Pipeline Automation"))
        pform = QFormLayout()
        self.auto_queue = QCheckBox("Auto-queue for publishing after Drive upload")
        self.auto_queue.setChecked(bool(app.cfg.get("auto_queue_after_drive", True)))
        pform.addRow("", self.auto_queue)
        self.default_platform = QComboBox()
        self.default_platform.addItems(["YT Shorts", "IG Reels", "TikTok", "FB Reels"])
        plat_label = {"youtube": "YT Shorts", "instagram": "IG Reels",
                      "tiktok": "TikTok", "facebook": "FB Reels"}.get(
            app.cfg.get("default_platform_id", "instagram"), "IG Reels")
        self.default_platform.setCurrentText(plat_label)
        pform.addRow("Default platform", self.default_platform)
        self.auto_delete = QCheckBox("Auto-delete local file AFTER verified success "
                                     "(Drive done + posted)")
        self.auto_delete.setChecked(bool(app.cfg.get("auto_delete_after_success", True)))
        pform.addRow("", self.auto_delete)
        self.keep_backup = QCheckBox("Keep backup — move to backup folder instead of deleting")
        self.keep_backup.setChecked(bool(app.cfg.get("keep_backup", False)))
        pform.addRow("", self.keep_backup)
        pipe.add(pform)
        brow = QHBoxLayout()
        self.backup = QLineEdit(app.cfg.get("backup_folder") or "")
        self.backup.setPlaceholderText("Backup folder (optional)")
        bb = QPushButton("Browse…")
        bb.clicked.connect(lambda: self._pick(self.backup))
        brow.addWidget(self.backup, 1)
        brow.addWidget(bb)
        pipe.add(brow)
        pipe.add(muted("Safety: files are NEVER deleted unless the Drive upload succeeded AND "
                       "the post was verified. Failures always keep the local file."))
        lay.addWidget(pipe)

        # ---- folders ----
        folders = Card()
        folders.add(h2_icon("database", "Folders"))
        fform = QFormLayout()
        self.drive = QLineEdit(app.cfg.get("drive_folder"))
        dbtn = QPushButton("Browse…")
        dbtn.clicked.connect(lambda: self._pick(self.drive))
        drow = QHBoxLayout()
        drow.addWidget(self.drive, 1)
        drow.addWidget(dbtn)
        self.assets = QLineEdit(app.cfg.get("asset_folder"))
        abtn = QPushButton("Browse…")
        abtn.clicked.connect(lambda: self._pick(self.assets))
        arow = QHBoxLayout()
        arow.addWidget(self.assets, 1)
        arow.addWidget(abtn)
        fform.addRow("Drive watch folder", drow)
        fform.addRow("Asset library", arow)
        folders.add(fform)
        lay.addWidget(folders)

        # ---- google / drive (seller-managed OAuth; customer just clicks Connect) ----
        gcard = Card()
        gcard.add(h2("☁ Google (Drive + YouTube)"))
        gcard.add(muted("Sign-in is handled by the seller's registered Google app — "
                        "you never enter API keys. Connect on the Platforms screen."))
        gform = QFormLayout()
        self.drive_folder_id = QLineEdit(app.cfg.get("drive_folder_id"))
        self.drive_folder_id.setPlaceholderText("Optional: Drive folder ID for backups")
        gform.addRow("Drive folder ID (optional)", self.drive_folder_id)
        gcard.add(gform)
        gconn = icon_button("Connect Google now", "link")
        gconn.clicked.connect(lambda: self.app.nav_to("platforms"))
        gcard.add(gconn)
        lay.addWidget(gcard)

        # ---- seller connection (v1.3 admin panel, optional, consent-gated) ----
        tcard = Card()
        tcard.add(h2_icon("globe", "Seller connection (optional)"))
        tcard.add(muted("Lets your seller's support see your connected channels & "
                        "upload results so they can help you faster.\n"
                        "You can turn this OFF anytime — then OCTORA sends nothing."))
        self.tele_consent = QCheckBox("Share anonymous usage stats with the seller")
        self.tele_consent.setChecked(bool(app.cfg.get("telemetry_consent", False)))
        tcard.add(self.tele_consent)
        tform = QFormLayout()
        self.admin_url = QLineEdit(app.cfg.get("admin_server_url") or "")
        self.admin_url.setPlaceholderText("https://… (from your seller)")
        tform.addRow("Admin server URL", self.admin_url)
        tcard.add(tform)
        prow = QHBoxLayout()
        priv = icon_button("View privacy policy", "external")
        priv.clicked.connect(self._show_privacy)
        prow.addWidget(priv)
        prow.addStretch()
        tcard.add(prow)
        lay.addWidget(tcard)

        # ---- license ----
        lic = Card()
        lic.add(h2_icon("lock", "License"))
        self.lic_status = QLabel()
        self.lic_status.setWordWrap(True)
        lic.add(self.lic_status)
        lrow = QHBoxLayout()
        act = QPushButton("Enter / change license key")
        act.clicked.connect(self._license_dialog)
        lrow.addWidget(act)
        lrow.addStretch()
        lic.add(lrow)
        lay.addWidget(lic)

        # ---- appearance ----
        appc = Card()
        appc.add(h2_icon("eye", "Appearance"))
        aform = QFormLayout()
        self.accent = QComboBox()
        self.accent.addItems(["red", "cyan", "violet"])
        self.accent.setCurrentText(app.cfg.get("accent", "red"))
        aform.addRow("Accent color", self.accent)
        self.tray = QCheckBox("Minimize to system tray")
        self.tray.setChecked(bool(app.cfg.get("minimize_to_tray", True)))
        aform.addRow("", self.tray)
        self.op = QLineEdit(app.cfg.get("operator", "docock_op"))
        aform.addRow("Operator name", self.op)
        appc.add(aform)
        appc.add(muted("Accent applies after restart."))
        lay.addWidget(appc)
        lay.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.refresh()

    def _pick(self, line):
        d = QFileDialog.getExistingDirectory(self, "Choose folder")
        if d:
            line.setText(d)


    def _show_privacy(self):
        """Show the bundled PRIVACY.md in a dialog."""
        from ...core.config import resource_path
        from pathlib import Path
        text = ""
        for cand in (Path(resource_path("PRIVACY.md")), Path("PRIVACY.md")):
            try:
                if cand.exists():
                    text = cand.read_text(encoding="utf-8")
                    break
            except Exception:  # noqa: BLE001
                pass
        if not text:
            text = ("Privacy policy file not found.\n\nOCTORA only sends anonymous "
                    "usage stats (app version, connected platforms, upload counts) "
                    "to the seller's server, and only if you allow it in this screen.")
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle("OCTORA — Privacy policy")
        dlg.resize(600, 480)
        lay = QVBoxLayout(dlg)
        tb = QTextBrowser()
        tb.setMarkdown(text)
        lay.addWidget(tb)
        ok = QPushButton("Close")
        ok.clicked.connect(dlg.accept)
        lay.addWidget(ok)
        dlg.exec()

    def _license_dialog(self):
        dlg = ActivationDialog(LicenseManager(self.app.cfg), self)
        if dlg.exec():
            self.refresh()

    def _save(self):
        pid = {"YT Shorts": "youtube", "IG Reels": "instagram",
               "TikTok": "tiktok", "FB Reels": "facebook"}[self.default_platform.currentText()]
        data = {
            "demo_mode": self.demo.isChecked(),
            "auto_queue_after_drive": self.auto_queue.isChecked(),
            "default_platform_id": pid,
            "auto_delete_after_success": self.auto_delete.isChecked(),
            "keep_backup": self.keep_backup.isChecked(),
            "backup_folder": self.backup.text().strip(),
            "drive_folder": self.drive.text().strip(),
            "asset_folder": self.assets.text().strip(),
            "drive_folder_id": self.drive_folder_id.text().strip(),
            "accent": self.accent.currentText(),
            "minimize_to_tray": self.tray.isChecked(),
            "operator": self.op.text().strip() or "docock_op",
            "telemetry_consent": self.tele_consent.isChecked(),
            "admin_server_url": self.admin_url.text().strip(),
        }
        self.app.cfg.update(data)
        self.app.log.info("settings saved (demo_mode=%s)", self.demo.isChecked())
        QMessageBox.information(self, "Settings", "Saved. Pipeline settings apply immediately.")

    def refresh(self):
        st = LicenseManager(self.app.cfg).status()
        self.lic_status.setText(
            f"Mode: <b>{st['mode'].upper()}</b> — {st['message']}"
            + (f"<br>Licensed to: {st['name']} ({st['email']})" if st.get("name") and st["mode"] == "licensed" else ""))
