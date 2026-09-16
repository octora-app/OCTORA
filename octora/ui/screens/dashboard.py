"""Dashboard: Live Operations, stat tiles, tentacle pipeline, scheduler timeline,
tentacle status rail — reference-mockup layout."""
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QScrollArea, QPushButton, QSizePolicy, QFrame)

from ...core.config import resource_path
from ...core.database import now_ist
from .. import theme
from ..widgets import (StatTile, TimelineCard, Card, h2, muted, HealthRow,
                       BracketFrame, TentacleLink, HubEye, pill, icon_button,
                       svg_label)


def _qpix(name, h):
    p = resource_path(f"octora/assets/{name}")
    if not os.path.exists(p):
        return None
    return QPixmap(p).scaledToHeight(h, Qt.TransformationMode.SmoothTransformation)


def _chip_html(text):
    return (f'<span style="background-color:{theme.PANEL3}; color:{theme.TEXT}; '
            f'border:1px solid {theme.STEEL}; padding:2px 6px; font-size:11px;">'
            f'{text}</span>')


class TimelineRuler(QWidget):
    """Horizontal steel timeline with glowing time markers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._marks = ["14:00", "15:30", "16:45", "18:00", "19:30"]
        self.setFixedHeight(40)

    def paintEvent(self, e):
        from PyQt6.QtCore import QPointF as QPF
        from PyQt6.QtGui import QPainter, QPen, QColor, QRadialGradient, QBrush
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        y = H - 8
        p.setPen(QPen(QColor(theme.STEEL), 2))
        p.drawLine(30, y, W - 30, y)
        n = len(self._marks)
        for i, m in enumerate(self._marks):
            x = 30 + (W - 60) * i / max(1, n - 1)
            glow = QRadialGradient(x, y, 10)
            gc = QColor(theme.GREEN)
            gc.setAlpha(90)
            glow.setColorAt(0, gc)
            glow.setColorAt(1, QColor(47, 224, 122, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPF(x, y), 10, 10)
            p.setBrush(QBrush(QColor(theme.GREEN)))
            p.drawEllipse(QPF(x, y), 4, 4)
            p.setPen(QPen(QColor(theme.MUTED)))
            p.drawText(int(x) - 22, 4, 44, 16,
                       Qt.AlignmentFlag.AlignHCenter, m)
        p.end()


class Dashboard(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        outer = QHBoxLayout(inner)
        outer.setSpacing(8)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(inner)
        root.addWidget(scroll)

        # ---- center column ----
        center = QVBoxLayout()
        center.setSpacing(10)
        outer.addLayout(center, 1)

        # ---- row 0: Live Operations + 4 stat tiles ----
        row0 = QHBoxLayout()
        row0.setSpacing(6)
        row0.addWidget(self._live_ops(), 4)
        self.tile_reels = StatTile("Reels Published", "red")
        self.tile_shorts = StatTile("Shorts Published", "amber")
        self.tile_rate = StatTile("Success Rate", "green")
        self.tile_active = StatTile("Active Tasks", "blue")
        for w in (self.tile_reels, self.tile_shorts, self.tile_rate, self.tile_active):
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            row0.addWidget(w, 1)
        center.addLayout(row0)

        # ---- row 1: pipeline ----
        center.addWidget(self._pipeline())

        # ---- row 2: scheduler timeline ----
        center.addWidget(self._timeline())

        # ---- right rail: tentacle status ----
        outer.addWidget(self._tentacle_status(), 0)

        # timers
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(1000)
        self._tick_clock()

    # ================= panels =================
    def _live_ops(self):
        f = BracketFrame()
        f.setTint(theme.RED, 40)  # reference: red-tinted glass
        lay = QHBoxLayout(f)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        left = QVBoxLayout()
        left.setSpacing(6)
        trow = QHBoxLayout()
        t = QLabel("Live Operations")
        t.setObjectName("H1")
        t.setStyleSheet("font-size: 18px; font-weight: 800; background: transparent;")
        trow.addWidget(t)
        trow.addWidget(pill("\u25cf Live \u2022 Connected", "live"))
        trow.addStretch()
        left.addLayout(trow)
        left.addWidget(muted("Parallel pipeline processing \u2022 All jobs automated"))
        # chips as a wrapping rich-text label so the panel squeezes gracefully
        self.chips_lbl = QLabel()
        self.chips_lbl.setWordWrap(True)
        self.chips_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.chips_lbl.setStyleSheet("background: transparent;")
        left.addWidget(self.chips_lbl)
        left.addStretch()
        lay.addLayout(left, 1)
        # globe BESIDE the Dr Octopus quote (reference: horizontal, not stacked)
        gp = _qpix("globe-wireframe.png", 60)
        if gp:
            gl = QLabel()
            gl.setPixmap(gp)
            gl.setStyleSheet("background: transparent;")
            gl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(gl, 0)
        q = QLabel("\u201cWITH<br>THE RIGHT TOOLS,<br>EVERYTHING<br>IS POSSIBLE.\u201d<br>\u2014 DR. OCTOPUS")
        q.setObjectName("QuoteBox")
        q.setTextFormat(Qt.TextFormat.RichText)
        q.setFixedWidth(100)
        q.setStyleSheet("font-size: 9px; padding: 6px; letter-spacing: 0px;")
        q.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(q, 0)
        self._render_chips()
        return f

    def _render_chips(self):
        t = now_ist()
        parts = [
            _chip_html("Asia/Kolkata (IST)"),
            _chip_html(t.strftime("%A, %d %b %Y")),
            _chip_html(t.strftime("%H:%M IST")),
        ]
        self.chips_lbl.setText("&nbsp;".join(parts))

    def _pipeline(self):
        from ..widgets import PipelineCard
        f = BracketFrame()
        lay = QVBoxLayout(f)
        lay.setContentsMargins(18, 12, 18, 14)
        lay.setSpacing(6)
        head = QHBoxLayout()
        tt = QVBoxLayout()
        pt = QLabel("Pipeline Visualization")
        pt.setStyleSheet("font-size: 20px; font-weight: 800; background: transparent;")
        tt.addWidget(pt)
        tt.addWidget(muted("Multi-tasking operations — three parallel streams now running"))
        head.addLayout(tt)
        head.addStretch()
        head.addWidget(HubEye(size=46))
        tag = QLabel("SYNCHRONIZE  //  EXECUTE  //  DOMINATE")
        tag.setObjectName("PanelTag")
        head.addWidget(tag)
        lay.addLayout(head)
        stages = QHBoxLayout()
        stages.setSpacing(4)
        self.cards = {}
        defs = [("fetch", "Fetch", "green", "cloud"),
                ("render", "Render", "amber", "render"),
                ("publish", "Upload", "blue", "upload")]
        for i, (key, title, color, icon) in enumerate(defs):
            w = PipelineCard(title, color, icon)
            stages.addWidget(w, 1)
            self.cards[key] = w
            if i < len(defs) - 1:
                stages.addWidget(TentacleLink(flip=(i == 1)), 0)
        lay.addLayout(stages)
        return f

    def _timeline(self):
        f = BracketFrame()
        lay = QVBoxLayout(f)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(4)
        head = QHBoxLayout()
        tt = QVBoxLayout()
        t = QLabel("Today's Scheduler Timeline — Queued Posts")
        t.setStyleSheet("font-size: 18px; font-weight: 800; background: transparent;")
        tt.addWidget(t)
        self.tl_sub = muted("")
        tt.addWidget(self.tl_sub)
        head.addLayout(tt)
        head.addStretch()
        goto = icon_button("View Full Schedule", "chevron-right", 14, theme.TEXT, "GhostBtn")
        goto.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        goto.clicked.connect(lambda: self.app.show_screen("scheduler"))
        head.addWidget(goto)
        lay.addLayout(head)
        lay.addWidget(TimelineRuler())
        tlscroll = QScrollArea()
        tlscroll.setWidgetResizable(True)
        tlscroll.setFixedHeight(118)
        # never force the dashboard wider: scroll horizontally instead
        tlscroll.setSizePolicy(QSizePolicy.Policy.Ignored,
                               QSizePolicy.Policy.Fixed)
        tlscroll.setFrameShape(QScrollArea.Shape.NoFrame)
        tlscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tlscroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tl_inner = QWidget()
        self.tl_lay = QHBoxLayout(self.tl_inner)
        self.tl_lay.setSpacing(10)
        self.tl_lay.setContentsMargins(0, 2, 0, 2)
        tlscroll.setWidget(self.tl_inner)
        lay.addWidget(tlscroll)
        return f

    def _tentacle_status(self):
        f = BracketFrame()
        f.setFixedWidth(188)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        pp = _qpix("rail-portrait.png", 200)
        if pp:
            # fit the rail's inner width exactly (no edge clipping)
            pw = pp.width()
            inner = 188 - 24
            if pw > inner:
                pp = pp.scaledToWidth(inner, Qt.TransformationMode.SmoothTransformation)
            pl = QLabel()
            pl.setPixmap(pp)
            pl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            pl.setStyleSheet("background: transparent; border: 1px solid #2b313b; border-radius: 8px;")
            lay.addWidget(pl)
        q = QLabel("“INTELLIGENCE\nMULTIPLIES\nPOSSIBILITIES.”\n— DR. OCTOPUS")
        q.setObjectName("QuoteBox")
        q.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(q)
        for txt in ["8 Tentacles Online", "All Systems Stable", "AI Assistance Active",
                    "Secure Connection", "No Errors"]:
            lay.addWidget(HealthRow(txt, True))
        lay.addStretch()
        s = QLabel("More Arms.\nMore Results.")
        s.setObjectName("SideScript")
        s.setStyleSheet("font-size: 15px;")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(s)
        return f

    # ================= actions / refresh =================
    def _tick_clock(self):
        self._render_chips()

    def refresh(self):
        s = self.app.db.stats()
        self.tile_reels.set(s["reels"], f"↑ {s['reels_today']} today")
        self.tile_shorts.set(s["shorts"], f"↑ {s['shorts_today']} today")
        self.tile_rate.set(f"{s['success_rate']}%", "↑ this week")
        self.tile_active.set(s["active_tasks"],
                             "Running smoothly" if s["active_tasks"] else "Queue clear")
        self.refresh_timeline()

    def refresh_timeline(self):
        while self.tl_lay.count():
            it = self.tl_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        t = now_ist()
        self.tl_sub.setText(f"Asia/Kolkata (IST) • {t.strftime('%d %b %Y')}")
        rows = self.app.db.query(
            "SELECT * FROM scheduled_posts WHERE substr(scheduled_at,1,10)=? ORDER BY scheduled_at",
            (t.date().isoformat(),))
        if not rows:
            self.tl_lay.addWidget(muted("No posts scheduled today — add some in Scheduler."))
            return
        for i, r in enumerate(rows):
            try:
                from datetime import datetime
                at = datetime.fromisoformat(r["scheduled_at"])
            except Exception:  # noqa: BLE001
                continue
            delta = (at - t).total_seconds()
            if r["status"] == "posted":
                state = "posted"
            elif r["status"] in ("failed",):
                state = "failed"
            elif abs(delta) < 30 * 60:
                state = "now"
            else:
                state = "queued"
            thumb = resource_path(f"octora/assets/thumb-{i % 5}.png")
            card = TimelineCard(at.strftime("%H:%M"), state,
                                (r["caption"] or "Untitled")[:28], r["platform"],
                                thumb=thumb if os.path.exists(thumb) else None)
            card.setFixedWidth(210)
            self.tl_lay.addWidget(card)
        self.tl_lay.addStretch()

    def on_pipeline(self, cards: dict):
        for key, w in self.cards.items():
            c = cards.get(key, {})
            w.update(c.get("label", "?"), c.get("progress", 0),
                     c.get("detail", ""), c.get("retries", 0))
