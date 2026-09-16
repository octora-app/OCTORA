"""Platforms screen — one-click Connect buttons (v1.1).

CUSTOMER MODEL: no API keys, ever. The seller bundles their cloud-app
credentials in octora/seller_config.json; the customer just clicks a Connect
button, signs in with their OWN account in the browser, and OCTORA stores
their personal tokens per-machine. Disconnect wipes them.
"""
import threading

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
                             QPushButton, QCheckBox, QMessageBox, QComboBox)

from ...core import oauth, seller_config
from ...platforms import PLUGINS, platform_enabled
from ..widgets import Card, h2, muted, svg_label, icon_button, h2_icon


class PlatformsScreen(QWidget):
    connect_done = pyqtSignal(str, bool, str)  # provider, ok, message

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.connect_done.connect(self._on_connect_done)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.addLayout(h2_icon("link", "Platforms"))
        head.addStretch()
        go = icon_button("Open Settings", "settings")
        go.clicked.connect(lambda: self.app.nav_to("Settings"))
        head.addWidget(go)
        root.addLayout(head)
        root.addWidget(muted("No API keys needed — click Connect and sign in with your own "
                             "account. Your tokens stay on this machine only."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(12)

        # ---- Google account (YouTube + Drive share one sign-in) ----
        lay.addWidget(self._google_card())

        # ---- plugin cards ----
        self._badge = {}
        self._chk = {}
        self._status_lbl = {}
        self._page_combo = None
        for plug in PLUGINS:
            lay.addWidget(self._plugin_card(plug, lay))
        lay.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll)
        self.refresh()

    # ------------------------------------------------------------------
    def _google_card(self) -> Card:
        card = Card()
        cl = QVBoxLayout()
        cl.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(svg_label("link", 20, "#F2F7F8"))
        t = QLabel("Google Account")
        t.setObjectName("PipeTitle")
        top.addWidget(t)
        top.addStretch()
        self._g_badge = QLabel()
        self._g_badge.setObjectName("Badge")
        top.addWidget(self._g_badge)
        cl.addLayout(top)
        cl.addWidget(muted("One Google sign-in connects BOTH YouTube (Shorts uploads) "
                           "AND Google Drive (cloud backup). Uses the seller's registered "
                           "app — you just log in."))
        self._g_status = QLabel()
        self._g_status.setObjectName("Muted")
        self._g_status.setWordWrap(True)
        cl.addWidget(self._g_status)
        brow = QHBoxLayout()
        self._g_yt_btn = QPushButton("▶  Connect to YouTube")
        self._g_yt_btn.setMinimumHeight(44)
        self._g_yt_btn.clicked.connect(lambda: self._connect("google"))
        self._g_drive_btn = QPushButton("☁  Connect to Google Drive")
        self._g_drive_btn.setMinimumHeight(44)
        self._g_drive_btn.clicked.connect(lambda: self._connect("google"))
        self._g_disc_btn = QPushButton("Disconnect")
        self._g_disc_btn.clicked.connect(lambda: self._disconnect("google"))
        brow.addWidget(self._g_yt_btn, 1)
        brow.addWidget(self._g_drive_btn, 1)
        brow.addWidget(self._g_disc_btn)
        cl.addLayout(brow)
        card.layout_().addLayout(cl)
        return card

    def _plugin_card(self, plug, parent_lay) -> Card:
        card = Card()
        cl = QVBoxLayout()
        cl.setSpacing(8)
        top = QHBoxLayout()
        name = QLabel(f"{plug.icon}  {plug.name}")
        name.setObjectName("PipeTitle")
        top.addWidget(name)
        top.addStretch()
        badge = QLabel()
        badge.setObjectName("Badge")
        top.addWidget(badge)
        self._badge[plug.id] = badge
        chk = QCheckBox("Enabled")
        chk.setChecked(platform_enabled(self.app.cfg, plug.id))
        chk.toggled.connect(lambda v, pid=plug.id: self._toggle(pid, v))
        top.addWidget(chk)
        self._chk[plug.id] = chk
        cl.addLayout(top)
        d = QLabel(plug.description)
        d.setObjectName("Muted")
        d.setWordWrap(True)
        cl.addWidget(d)
        help_l = QLabel(plug.setup_help())
        help_l.setObjectName("Muted")
        help_l.setWordWrap(True)
        cl.addWidget(help_l)

        st = QLabel()
        st.setObjectName("Muted")
        st.setWordWrap(True)
        self._status_lbl[plug.id] = st
        cl.addWidget(st)

        brow = QHBoxLayout()
        if plug.id == "youtube":
            b = icon_button("Connect to YouTube", "play")
            b.setMinimumHeight(40)
            b.clicked.connect(lambda: self._connect("google"))
            brow.addWidget(b, 1)
            db = QPushButton("Disconnect")
            db.clicked.connect(lambda: self._disconnect("google"))
            brow.addWidget(db)
        elif plug.id == "instagram":
            b = icon_button("Connect Instagram", "link")
            b.setMinimumHeight(40)
            b.clicked.connect(lambda: self._connect("meta"))
            brow.addWidget(b, 1)
            db = QPushButton("Disconnect")
            db.clicked.connect(lambda: self._disconnect("meta"))
            brow.addWidget(db)
        elif plug.id == "facebook":
            b = icon_button("Connect Facebook", "link")
            b.setMinimumHeight(40)
            b.clicked.connect(lambda: self._connect("meta"))
            brow.addWidget(b, 1)
            db = QPushButton("Disconnect")
            db.clicked.connect(lambda: self._disconnect("meta"))
            brow.addWidget(db)
            self._page_combo = QComboBox()
            self._page_combo.setMinimumWidth(200)
            self._page_combo.currentIndexChanged.connect(self._page_picked)
            brow.addWidget(self._page_combo)
        elif plug.id == "tiktok":
            b = icon_button("Connect TikTok", "link")
            b.setMinimumHeight(40)
            b.clicked.connect(lambda: self._connect("tiktok"))
            brow.addWidget(b, 1)
            db = QPushButton("Disconnect")
            db.clicked.connect(lambda: self._disconnect("tiktok"))
            brow.addWidget(db)
        brow.addStretch()
        cl.addLayout(brow)
        card.layout_().addLayout(cl)
        return card

    # ------------------------------------------------------------------
    def _toggle(self, pid, val):
        self.app.cfg.set(f"platform_{pid}_enabled", "1" if val else "0")
        self.refresh()

    def _page_picked(self, idx):
        if self._page_combo is None or idx < 0:
            return
        pid = self._page_combo.itemData(idx)
        if pid:
            self.app.cfg.set("meta_page_id", pid)

    # ------------------------------------------------------------------
    def _seller_ok(self, provider: str) -> bool:
        return {"google": seller_config.google_ready(),
                "meta": seller_config.meta_ready(),
                "tiktok": seller_config.tiktok_ready()}.get(provider, False)

    def _connect(self, provider: str):
        if not self._seller_ok(provider):
            QMessageBox.warning(
                self, "Not set up yet",
                "The seller hasn't configured this connection yet.\n"
                "Please contact support — no action needed from you.")
            return
        QMessageBox.information(
            self, "Connect",
            "Your browser will open for sign-in.\n"
            "Approve OCTORA, then return here.\n\n"
            "No passwords or keys are typed into OCTORA.")
        threading.Thread(target=self._do_connect, args=(provider,), daemon=True).start()

    def _do_connect(self, provider: str):
        cfg = self.app.cfg
        try:
            if provider == "google":
                tok, email = oauth.google_connect()
                if tok:
                    cfg.update({"google_refresh_token": tok["refresh_token"],
                                "google_access_token": tok.get("access_token", ""),
                                "google_account_email": email})
                    # v1.2: zero-setup — create the OCTORA Drive folder right away
                    try:
                        from ...core import gdrive
                        fid, fmsg = gdrive.ensure_octora_folder(cfg)
                        if fid:
                            self.app.log.info("drive: auto-folder ready (%s)", fid)
                        else:
                            self.app.log.warning("drive: auto-folder: %s", fmsg)
                    except Exception as e:  # noqa: BLE001
                        self.app.log.warning("drive: auto-folder error: %s", e)
                    # v1.3: cache channel identity for telemetry display (best-effort)
                    try:
                        from ...core.oauth import _get_json
                        info = _get_json(
                            "https://www.googleapis.com/youtube/v3/channels"
                            "?part=snippet,statistics&mine=true",
                            token=tok.get("access_token", ""), timeout=15) or {}
                        item = (info.get("items") or [{}])[0]
                        cfg.set("google_channel_name",
                                item.get("snippet", {}).get("title", ""))
                        cfg.set("google_subscriber_count",
                                int(item.get("statistics", {}).get("subscriberCount", 0) or 0))
                    except Exception:  # noqa: BLE001
                        pass
                    self.connect_done.emit("google", True,
                                           f"Google connected ✅\nSigned in as {email or 'your Google account'}.\n"
                                           "Your OCTORA Drive folder is ready — uploads go there automatically.")
                else:
                    self.connect_done.emit("google", False, f"Google connect failed: {email}")
            elif provider == "meta":
                info, msg = oauth.meta_connect()
                if info:
                    cfg.update({"meta_access_token": info["access_token"],
                                "meta_token_obtained_at": info["obtained_at"],
                                "meta_user_name": info["user_name"],
                                "meta_user_email": info["user_email"],
                                "meta_pages": info["pages"],
                                "instagram_business_id": info["instagram_business_id"],
                                "instagram_username": info["instagram_username"]})
                    if info["pages"] and not cfg.get("meta_page_id"):
                        cfg.set("meta_page_id", info["pages"][0]["id"])
                    self.connect_done.emit("meta", True, f"Facebook connected ✅\n{msg}")
                else:
                    self.connect_done.emit("meta", False, f"Facebook connect failed: {msg}")
            elif provider == "tiktok":
                tok, msg = oauth.tiktok_connect()
                if tok:
                    cfg.update({"tiktok_access_token": tok["access_token"],
                                "tiktok_refresh_token": tok.get("refresh_token", ""),
                                "tiktok_open_id": tok.get("open_id", ""),
                                "tiktok_display_name": tok.get("display_name", ""),
                                "tiktok_token_obtained_at": tok.get("obtained_at", 0)})
                    self.connect_done.emit("tiktok", True, f"TikTok connected ✅\n{msg}")
                else:
                    self.connect_done.emit("tiktok", False, f"TikTok connect failed: {msg}")
        except Exception as e:  # noqa: BLE001
            self.connect_done.emit(provider, False, f"Connect error: {e}")

    def _disconnect(self, provider: str):
        cfg = self.app.cfg
        if provider == "google":
            cfg.update({"google_refresh_token": "", "google_access_token": "",
                        "google_account_email": ""})
        elif provider == "meta":
            cfg.update({"meta_access_token": "", "meta_token_obtained_at": 0,
                        "meta_user_name": "", "meta_user_email": "", "meta_pages": [],
                        "meta_page_id": "", "instagram_business_id": "",
                        "instagram_username": ""})
        elif provider == "tiktok":
            cfg.update({"tiktok_access_token": "", "tiktok_refresh_token": "",
                        "tiktok_open_id": "", "tiktok_display_name": "",
                        "tiktok_token_obtained_at": 0})
        self.app.log.info("%s disconnected by user", provider)
        # v1.3: tell the admin panel about the change (consent-gated, fail-silent)
        try:
            from ...core import telemetry
            telemetry.notify_platform_change(self.app.db, self.app.cfg)
        except Exception:  # noqa: BLE001
            pass
        self.refresh()

    def _on_connect_done(self, provider, ok, msg):
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Connect", msg)
        # v1.3: tell the admin panel about the change (consent-gated, fail-silent)
        if ok:
            try:
                from ...core import telemetry
                telemetry.notify_platform_change(self.app.db, self.app.cfg)
            except Exception:  # noqa: BLE001
                pass
        self.refresh()

    # ------------------------------------------------------------------
    def showEvent(self, ev):  # noqa: N802
        super().showEvent(ev)
        self.refresh()

    def _set_badge(self, badge, text, color):
        badge.setText(text)
        badge.setProperty("color", color)
        badge.style().unpolish(badge)
        badge.style().polish(badge)

    def refresh(self):
        cfg = self.app.cfg
        demo = cfg.demo_mode

        # ---- Google card ----
        g_connected = bool(cfg.get("google_refresh_token")) and seller_config.google_ready()
        if not seller_config.google_ready():
            self._set_badge(self._g_badge, "SELLER SETUP NEEDED", "red")
            self._g_status.setText("The seller hasn't configured Google sign-in yet.")
        elif g_connected:
            self._set_badge(self._g_badge, "CONNECTED", "green")
            self._g_status.setText(f"Signed in as {cfg.get('google_account_email') or 'your Google account'} "
                                   "— YouTube uploads + Drive backup active.")
        else:
            self._set_badge(self._g_badge, "NOT CONNECTED", "gray")
            self._g_status.setText("Not connected yet — click a Connect button above.")
        self._g_yt_btn.setEnabled(seller_config.google_ready())
        self._g_drive_btn.setEnabled(seller_config.google_ready())
        self._g_disc_btn.setEnabled(g_connected)

        # ---- plugin cards ----
        for plug in PLUGINS:
            if not platform_enabled(cfg, plug.id):
                self._set_badge(self._badge[plug.id], "DISABLED", "gray")
                self._status_lbl[plug.id].setText("")
                continue
            if demo:
                self._set_badge(self._badge[plug.id], "DEMO", "amber")
            else:
                ok = plug.is_configured(cfg)
                self._set_badge(self._badge[plug.id],
                                "READY" if ok else "NOT CONNECTED",
                                "green" if ok else "gray")
            self._status_lbl[plug.id].setText(self._conn_line(plug.id))

        # ---- FB page picker ----
        if self._page_combo is not None:
            pages = cfg.get("meta_pages") or []
            self._page_combo.blockSignals(True)
            self._page_combo.clear()
            for p in pages:
                self._page_combo.addItem(p.get("name", p.get("id", "?")), p.get("id"))
            sel = cfg.get("meta_page_id", "")
            if sel:
                idx = self._page_combo.findData(sel)
                if idx >= 0:
                    self._page_combo.setCurrentIndex(idx)
            self._page_combo.setVisible(bool(pages))
            self._page_combo.blockSignals(False)

    def _conn_line(self, pid: str) -> str:
        cfg = self.app.cfg
        if pid == "youtube":
            if cfg.get("google_refresh_token") and seller_config.google_ready():
                return f"✅ Connected as {cfg.get('google_account_email') or 'your Google account'}"
            if not seller_config.google_ready():
                return "⚠ Seller hasn't configured Google sign-in yet."
            return "Not connected — click 'Connect to YouTube'."
        if pid == "instagram":
            if cfg.get("meta_access_token") and seller_config.meta_ready():
                ig = cfg.get("instagram_username")
                base = f"✅ Connected as {cfg.get('meta_user_name') or 'Facebook user'}"
                return base + (f" — Instagram @{ig} linked" if ig
                               else " — ⚠ no Instagram Business account linked yet")
            if not seller_config.meta_ready():
                return "⚠ Seller hasn't configured Meta sign-in yet."
            return "Not connected — click 'Connect Instagram'."
        if pid == "facebook":
            if cfg.get("meta_access_token") and seller_config.meta_ready():
                return f"✅ Connected as {cfg.get('meta_user_name') or 'Facebook user'} — pick a Page above"
            if not seller_config.meta_ready():
                return "⚠ Seller hasn't configured Meta sign-in yet."
            return "Not connected — click 'Connect Facebook'."
        if pid == "tiktok":
            if (cfg.get("tiktok_refresh_token") or cfg.get("tiktok_access_token")) \
                    and seller_config.tiktok_ready():
                return f"✅ Connected as {cfg.get('tiktok_display_name') or 'TikTok user'}"
            if not seller_config.tiktok_ready():
                return "⚠ Seller hasn't configured TikTok sign-in yet."
            return "Not connected — click 'Connect TikTok'."
        return ""
