"""Main window: top bar, sidebar nav, stacked screens, live status bar, tray, shortcuts."""
import os
import shutil

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut, QAction, QIcon, QPixmap, QPainter
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QStackedWidget, QSystemTrayIcon, QMenu,
                             QApplication)

from ..core.config import resource_path
from ..core.database import now_ist
from . import theme
from .widgets import (BracketFrame, CircleAvatar, NotifBell, NavItem,
                      svg_label, svg_pixmap)
from .screens.dashboard import Dashboard
from .screens.campaigns import Campaigns
from .screens.scheduler import Scheduler
from .screens.drivesync import DriveSync
from .screens.upload import UploadEngine
from .screens.niches import Niches
from .screens.platforms import PlatformsScreen as Platforms
from .screens.analytics import Analytics
from .screens.tools import Tools
from .screens.logs import Logs
from .screens.settings import Settings
from .screens.support import Support


class AppContext:
    """Shared handles passed to every screen."""
    def __init__(self, db, cfg, engine, log, show_screen):
        self.db = db
        self.cfg = cfg
        self.engine = engine
        self.log = log
        self.show_screen = show_screen


NAV = [
    ("dashboard", "dashboard", "Dashboard", "Overview & Control"),
    ("campaigns", "campaigns", "Campaigns", "Manage & Launch"),
    ("scheduler", "scheduler", "Scheduler", "Auto-Post Timeline"),
    ("drive", "drive-sync", "Drive Sync", "Assets & Storage"),
    ("upload", "upload", "Upload Engine", "Bulk Upload & Queue"),
    ("niches", "zap", "Niches", "Autopilot Sources"),
    ("platforms", "link", "Platforms", "Connections"),
    ("analytics", "analytics", "Analytics", "Performance Insights"),
    ("tools", "tools", "Tools", "AI & Utilities"),
    ("logs", "logs", "Logs", "System Activity"),
    ("settings", "settings", "Settings", "Preferences"),
    ("support", "info", "Support", "Help & Contact"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self._nav_btns = {}
        self.setWindowTitle("OCTORA — Automate Beyond Limits")
        self.resize(1480, 900)
        self.setMinimumSize(1180, 720)
        icon = resource_path("assets/icon.png")
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        # full-bleed background artwork (glass panels float above it)
        self._bg = None
        bgp = resource_path("octora/assets/bg-art.png")
        if os.path.exists(bgp):
            self._bg = QPixmap(bgp)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._topbar())

        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)
        mid.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        mid.addWidget(self.stack, 1)
        v.addLayout(mid, 1)
        v.addWidget(self._statusbar())
        v.addWidget(self._footstrip())

        # screens
        self.screens = {}
        makers = {"dashboard": Dashboard, "campaigns": Campaigns, "scheduler": Scheduler,
                  "drive": DriveSync, "upload": UploadEngine, "niches": Niches, "platforms": Platforms,
                  "analytics": Analytics, "tools": Tools, "logs": Logs, "settings": Settings, "support": Support}
        for key, _, _, _ in NAV:
            scr = makers[key](ctx)
            self.screens[key] = scr
            self.stack.addWidget(scr)
        self.show_screen("dashboard")

        # engine -> ui wiring
        eng = ctx.engine
        eng.pipeline_updated.connect(self.screens["dashboard"].on_pipeline)
        eng.queue_changed.connect(self._on_queue_changed)
        eng.stats_changed.connect(self._refresh_stats)
        eng.notify.connect(self._notify)

        self._stat_timer = QTimer(self)
        self._stat_timer.timeout.connect(self._refresh_stats)
        self._stat_timer.start(5000)
        self._refresh_stats()

        self._setup_tray()
        self._setup_shortcuts()
        ctx.log.info("UI ready — welcome, %s", ctx.cfg.get("operator"))

    def paintEvent(self, e):
        # full-bleed artwork, scaled to cover the window
        if self._bg is not None and not self._bg.isNull():
            p = QPainter(self)
            W, H = self.width(), self.height()
            bw, bh = self._bg.width(), self._bg.height()
            s = max(W / bw, H / bh)
            dw, dh = int(bw * s), int(bh * s)
            p.drawPixmap((W - dw) // 2, (H - dh) // 2, dw, dh, self._bg)
            p.end()
        super().paintEvent(e)

    def _quote_pix(self, name, h):
        p = resource_path(f"octora/assets/{name}")
        lbl = QLabel()
        lbl.setStyleSheet("background: transparent;")
        if os.path.exists(p):
            pm = QPixmap(p).scaledToHeight(h, Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(pm)
        return lbl

    # ---------- top bar ----------
    def _topbar(self):
        bar = QWidget()
        bar.setObjectName("TopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 8, 14, 8)
        lay.setSpacing(12)

        # brand panel: real pack logo badge + OCTORA text stack
        brand = BracketFrame()
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(14, 8, 18, 8)
        bl.setSpacing(12)
        mark = svg_label("brand/octora-logo", 64)
        bl.addWidget(mark)
        logo = QVBoxLayout()
        logo.setSpacing(1)
        lt = QLabel("OCTORA")
        lt.setObjectName("LogoText")
        lt.setStyleSheet("background: transparent;")
        ls = QLabel("AUTOMATE BEYOND LIMITS")
        ls.setObjectName("LogoSub")
        ls.setStyleSheet("background: transparent;")
        pw = QLabel("Powered by <b>Rouqil Tech</b>")
        pw.setObjectName("Powered")
        pw.setStyleSheet("background: transparent;")
        logo.addWidget(lt)
        logo.addWidget(ls)
        logo.addWidget(pw)
        bl.addLayout(logo)
        lay.addWidget(brand)

        # left script quote (reference: beside the logo block)
        lay.addWidget(self._quote_pix("quote-multitasks.png", 64))
        lay.addStretch()
        # right script quote (reference: left of the operator cluster)
        lay.addWidget(self._quote_pix("quote-chaos.png", 58))
        lay.addStretch()

        # operator cluster
        op = BracketFrame()
        op.setFill(theme.PANEL2)
        ol = QHBoxLayout(op)
        ol.setContentsMargins(12, 8, 12, 8)
        ol.setSpacing(10)
        avp = resource_path("octora/assets/operator-portrait.png")
        av = CircleAvatar(QPixmap(avp) if os.path.exists(avp) else None, 44)
        av.setStyleSheet("background: transparent;")
        ol.addWidget(av)
        nm = QVBoxLayout()
        nm.setSpacing(1)
        on = QLabel(self.ctx.cfg.get("operator"))
        on.setObjectName("OpName")
        on.setStyleSheet("background: transparent;")
        orr = QLabel("Operator")
        orr.setObjectName("OpRole")
        orr.setStyleSheet("background: transparent;")
        nm.addWidget(on)
        nm.addWidget(orr)
        ol.addLayout(nm)
        ol.addWidget(NotifBell())
        gear = QPushButton()
        gear.setObjectName("IconBtn")
        gear.setToolTip("Settings")
        _gp = svg_pixmap("settings", 18, theme.TEXT)
        if not _gp.isNull():
            gear.setIcon(QIcon(_gp))
        gear.clicked.connect(lambda: self.show_screen("settings"))
        ol.addWidget(gear)
        door = QPushButton()
        door.setObjectName("IconBtn")
        door.setToolTip("Exit")
        _dp = svg_pixmap("close", 16, theme.TEXT)
        if not _dp.isNull():
            door.setIcon(QIcon(_dp))
        door.clicked.connect(QApplication.instance().quit)
        ol.addWidget(door)
        lay.addWidget(op)

        # live + clock
        lc = QVBoxLayout()
        lc.setSpacing(1)
        self.live_lbl = QLabel("● LIVE")
        self.live_lbl.setObjectName("LiveDot")
        sub = QLabel("Systems Operational")
        sub.setObjectName("LiveSub")
        lc.addWidget(self.live_lbl)
        lc.addWidget(sub)
        lay.addLayout(lc)
        cc = QVBoxLayout()
        cc.setSpacing(1)
        self.clock = QLabel("")
        self.clock.setObjectName("Clock")
        self.clock_date = QLabel("")
        self.clock_date.setObjectName("ClockSub")
        cc.addWidget(self.clock)
        cc.addWidget(self.clock_date)
        lay.addLayout(cc)

        # license badge (compact): lock icon + mode
        from ..core.license import LicenseManager
        st = LicenseManager(self.ctx.cfg).status()
        lic_col = {"licensed": "green", "trial": "amber", "grace": "amber"}.get(st["mode"], "red")
        lic_wrap = QHBoxLayout()
        lic_wrap.setSpacing(6)
        lic_wrap.addWidget(svg_label("lock", 16,
                                     {"green": theme.GREEN, "amber": theme.AMBER,
                                      "red": theme.RED}.get(lic_col, theme.MUTED)))
        self.lic_lbl = QLabel(st["mode"].upper())
        self.lic_lbl.setObjectName("Badge")
        self.lic_lbl.setProperty("color", lic_col)
        self.lic_lbl.setToolTip(st["message"])
        lic_wrap.addWidget(self.lic_lbl)
        lic_box = QWidget()
        lic_box.setLayout(lic_wrap)
        lay.addWidget(lic_box)

        self._ct = QTimer(self)
        self._ct.timeout.connect(self._tick_top_clock)
        self._ct.start(1000)
        self._tick_top_clock()
        return bar

    def _tick_top_clock(self):
        t = now_ist()
        self.clock.setText(t.strftime("%H:%M:%S"))
        self.clock_date.setText(t.strftime("%a, %d %b %Y"))

    # ---------- sidebar ----------
    def _sidebar(self):
        side = QWidget()
        side.setObjectName("SideBar")
        side.setFixedWidth(210)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 10, 0, 8)
        lay.setSpacing(2)
        for key, icon, title, sub in NAV:
            it = NavItem(key, icon, title, sub, self.show_screen)
            self._nav_btns[key] = it
            lay.addWidget(it)
        lay.addSpacing(4)
        lay.addStretch()
        f1 = QLabel("Powered by")
        f1.setObjectName("SideFoot1")
        f1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(f1)
        f2 = QLabel("Rouqil Tech")
        f2.setObjectName("SideFoot2")
        f2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(f2)
        f3 = QLabel("BUILD&nbsp;&nbsp;&bull;&nbsp;&nbsp;AUTOMATE&nbsp;&nbsp;&bull;&nbsp;&nbsp;DOMINATE")
        f3.setObjectName("SideFoot3")
        f3.setTextFormat(Qt.TextFormat.RichText)
        f3.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(f3)
        lay.addSpacing(6)
        # red script signature (reference: "DISCIPLINE CREATES FREEDOM." + RQ mark)
        sc = self._quote_pix("side-discipline.png", 66)
        sc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sc)
        ver = QLabel("v2.4.1")
        ver.setObjectName("VerTag")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver)
        return side

    def show_screen(self, key):
        idx = [k for k, _, _, _ in NAV].index(key)
        self.stack.setCurrentIndex(idx)
        for k, it in self._nav_btns.items():
            it.set_active(k == key)

    # ---------- status bar ----------
    def _statusbar(self):
        bar = QWidget()
        bar.setObjectName("StatusBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(14)
        lay.addWidget(svg_label("shield", 24, theme.RED))
        self.err_lbl = QLabel("0 Errors")
        self.err_lbl.setObjectName("ErrZero")
        lay.addWidget(self.err_lbl)
        self.warn_lbl = QLabel("")
        self.warn_lbl.setObjectName("Muted")
        lay.addWidget(self.warn_lbl)
        lay.addStretch()
        self.sync_lbl = QLabel("")
        self.sync_lbl.setObjectName("Muted")
        lay.addWidget(self.sync_lbl)
        self.queue_lbl = QLabel("")
        self.queue_lbl.setObjectName("Muted")
        lay.addWidget(self.queue_lbl)
        ticon = svg_label("link", 22, theme.BLUE)
        lay.addWidget(ticon)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        th = QLabel("Tentacle network healthy")
        th.setStyleSheet(f"color: {theme.BLUE}; font-size: 12px; font-weight: 600;"
                         "background: transparent;")
        tl = QLabel("Latency: 18ms")
        tl.setStyleSheet(f"color: {theme.BLUE}; font-size: 11px; background: transparent;")
        tcol.addWidget(th)
        tcol.addWidget(tl)
        lay.addLayout(tcol)
        burst = QPushButton("INITIATE\nHIGHER OUTPUT")
        burst.setObjectName("RedButton")
        _cp = svg_pixmap("chevron-right", 20, "#ffffff")
        if not _cp.isNull():
            burst.setIcon(QIcon(_cp))
            burst.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        burst.setToolTip("Queue demo downloads — watch the full pipeline run end-to-end")
        burst.clicked.connect(lambda: self.ctx.engine.demo_burst(6))
        lay.addWidget(burst)
        return bar

    def _footstrip(self):
        f = QWidget()
        f.setFixedHeight(24)
        f.setStyleSheet(f"background: {theme.BG}; border-top: 1px solid {theme.STEEL};")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(14, 0, 14, 0)
        l = QLabel("OCTORA&nbsp;&nbsp;//&nbsp;&nbsp;POWERED BY ROUQIL TECH&nbsp;&nbsp;//&nbsp;&nbsp;HUMAN IDEAS. AMPLIFIED.")
        l.setObjectName("FootStrip")
        l.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(l)
        lay.addStretch()
        v = QLabel("v2.4.1")
        v.setObjectName("VerTag")
        lay.addWidget(v)
        return f

    def _storage_str(self):
        try:
            total, used, _ = shutil.disk_usage(str(self.ctx.cfg.data_dir
                                                   if hasattr(self.ctx.cfg, "data_dir") else "."))
            return f"Storage: {used/1e9:.1f}GB / {total/1e9:.1f}GB used"
        except Exception:  # noqa: BLE001
            return "Storage: —"

    def _refresh_stats(self):
        s = self.ctx.db.stats()
        e = s["errors_today"]
        self.err_lbl.setText(f"{e} Error{'s' if e != 1 else ''}")
        self.err_lbl.setObjectName("ErrZero" if e == 0 else "ErrSome")
        self.err_lbl.style().unpolish(self.err_lbl)
        self.err_lbl.style().polish(self.err_lbl)
        self.warn_lbl.setText(f"• 0 warnings\n• {self._storage_str()}")
        q = self.ctx.db.query_one(
            "SELECT COUNT(*) c FROM upload_queue WHERE status IN ('queued','uploading')")
        self.queue_lbl.setText(f"Queue: {(q['c'] or 0)} pending")
        last = self.ctx.db.query_one("SELECT at FROM uploads_log ORDER BY id DESC LIMIT 1")
        self.sync_lbl.setText(f"Last sync: {(last['at'][11:19] + ' IST') if last else '—'}")
        if hasattr(self.screens["dashboard"], "refresh"):
            self.screens["dashboard"].refresh()

    def _on_queue_changed(self):
        scr = self.screens.get("upload")
        if scr and self.stack.currentWidget() is scr:
            scr.refresh()

    # ---------- tray ----------
    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("OCTORA — Automate Beyond Limits")
        menu = QMenu()
        show_a = QAction("Show", self)
        show_a.triggered.connect(self._tray_show)
        quit_a = QAction("Quit", self)
        quit_a.triggered.connect(QApplication.instance().quit)
        menu.addAction(show_a)
        menu.addAction(quit_a)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._tray_show() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _tray_show(self):
        self.showNormal()
        self.activateWindow()

    def _notify(self, title, msg):
        if self.tray:
            self.tray.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, 5000)

    def closeEvent(self, event):
        if self.ctx.cfg.get("minimize_to_tray") and self.tray and self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage("OCTORA", "Running in background — tentacles still working",
                                  QSystemTrayIcon.MessageIcon.Information, 3000)
        else:
            event.accept()

    # ---------- shortcuts ----------
    def _setup_shortcuts(self):
        for i, (key, _, _, _) in enumerate(NAV[:10], start=1):
            seq = "Ctrl+0" if i == 10 else f"Ctrl+{i}"
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(lambda k=key: self.show_screen(k))
        r = QShortcut(QKeySequence("Ctrl+R"), self)
        r.activated.connect(lambda: self.show_screen(
            [k for k, _, _, _ in NAV][self.stack.currentIndex()]))
