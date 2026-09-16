"""Reusable Doc Ock-styled widgets — reference-mockup edition.

Custom-painted pieces: BracketFrame (chamfered panel + red glowing corner
brackets), SparkBars (mini bar charts), TentacleLink (metallic tentacle
connector with red glowing joints), HubEye (red glowing eye medallion),
ThumbLabel (video thumbnail placeholder).
"""
import math
import random

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (QColor, QPainter, QPainterPath, QPen, QBrush,
                         QRadialGradient, QLinearGradient, QPolygonF,
                         QPixmap, QIcon)
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QProgressBar, QFrame, QPushButton)

from ..core.config import resource_path
from . import theme


# --------------------------------------------------------------------------
# SVG asset icons (official pack). Icons use currentColor strokes, so we
# substitute the requested color at load time and render via QSvgRenderer.
_svg_cache = {}


def _svg_asset_path(name):
    if "/" in name:
        rel = f"octora/assets/{name}.svg"
    else:
        rel = f"octora/assets/icons/{name}.svg"
    return resource_path(rel)


def svg_pixmap(name, px=20, color=None):
    """Render a pack SVG to a QPixmap at px*px, recolored when given."""
    key = (name, px, color)
    pm = _svg_cache.get(key)
    if pm is not None:
        return pm
    pm = QPixmap()  # null = missing
    try:
        with open(_svg_asset_path(name), "rb") as f:
            data = f.read().decode("utf-8")
        if color and "currentColor" in data:
            data = data.replace("currentColor", color)
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QByteArray
        renderer = QSvgRenderer(QByteArray(data.encode("utf-8")))
        if renderer.isValid():
            pm = QPixmap(px, px)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(p)
            p.end()
    except OSError:
        pass
    _svg_cache[key] = pm
    return pm


def svg_label(name, px=20, color=None, parent=None):
    """QLabel showing a pack SVG icon (transparent background)."""
    lbl = QLabel(parent)
    pm = svg_pixmap(name, px, color)
    if not pm.isNull():
        lbl.setPixmap(pm)
    lbl.setStyleSheet("background: transparent;")
    return lbl


def icon_button(text, icon, px=16, color=None, obj=""):
    """QPushButton with a pack SVG icon left of the text."""
    b = QPushButton(text)
    pm = svg_pixmap(icon, px, color or theme.TEXT)
    if not pm.isNull():
        b.setIcon(QIcon(pm))
    if obj:
        b.setObjectName(obj)
    return b


def h1(text): return _lbl(text, "H1")
def h2(text): return _lbl(text, "H2")
def muted(text): return _lbl(text, "Muted")


def h1_icon(icon, text, px=30, color=None):
    """H1 header row: pack SVG icon + title."""
    row = QHBoxLayout()
    row.setSpacing(10)
    row.addWidget(svg_label(icon, px, color or theme.TEXT))
    row.addWidget(h1(text), 1)
    return row


def h2_icon(icon, text, px=24, color=None):
    """H2 header row: pack SVG icon + title."""
    row = QHBoxLayout()
    row.setSpacing(10)
    row.addWidget(svg_label(icon, px, color or theme.TEXT))
    row.addWidget(h2(text), 1)
    return row


def _lbl(text, obj=""):
    l = QLabel(text)
    if obj:
        l.setObjectName(obj)
    return l


def pill(text, color="gray"):
    p = QLabel(text)
    p.setObjectName("Pill")
    p.setProperty("color", color)
    return p


# --------------------------------------------------------------------------
class BracketFrame(QFrame):
    """Dark steel panel with chamfered corners and red glowing corner brackets.

    Glass edition: the default fill is semi-transparent so the full-bleed
    background artwork shows through, like the reference mockup."""

    GLASS_FILL = (10, 12, 16, 212)

    def __init__(self, parent=None, chamfer=16, glow=theme.RED):
        super().__init__(parent)
        self._chamfer = chamfer
        self._glow = QColor(glow)
        self._fill = QColor(*self.GLASS_FILL)
        self._tint = None  # (QColor, alpha)

    def setFill(self, hexstr):
        self._fill = QColor(hexstr)
        self.update()

    def setTint(self, hexstr, alpha=48):
        """Wash the glass with a color tint (e.g. red for Live Operations)."""
        self._tint = (QColor(hexstr), alpha)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        c = self._chamfer
        L, T, R, B = r.left(), r.top(), r.right(), r.bottom()
        path = QPainterPath()
        path.moveTo(L + c, T)
        path.lineTo(R - c, T)
        path.lineTo(R, T + c)
        path.lineTo(R, B - c)
        path.lineTo(R - c, B)
        path.lineTo(L + c, B)
        path.lineTo(L, B - c)
        path.lineTo(L, T + c)
        path.closeSubpath()
        p.fillPath(path, QBrush(self._fill))
        if self._tint:
            tc, ta = self._tint
            tc = QColor(tc)
            tc.setAlpha(ta)
            p.fillPath(path, QBrush(tc))
        p.setPen(QPen(QColor(theme.STEEL), 1.2))
        p.drawPath(path)
        # red corner brackets (glow pass + core pass)
        glow_c = QColor(self._glow)
        glow_c.setAlpha(70)
        seg = 30
        corners = [
            ((L + c + 6, T), (L + c + 6 + seg, T), (L, T + c + 6), (L, T + c + 6 + seg)),
            ((R - c - 6, T), (R - c - 6 - seg, T), (R, T + c + 6), (R, T + c + 6 + seg)),
            ((L + c + 6, B), (L + c + 6 + seg, B), (L, B - c - 6), (L, B - c - 6 - seg)),
            ((R - c - 6, B), (R - c - 6 - seg, B), (R, B - c - 6), (R, B - c - 6 - seg)),
        ]
        for (x1, y1), (x2, y2), (x3, y3), (x4, y4) in corners:
            p.setPen(QPen(glow_c, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
            p.drawLine(int(x3), int(y3), int(x4), int(y4))
            p.setPen(QPen(self._glow, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
            p.drawLine(int(x3), int(y3), int(x4), int(y4))
        p.end()


# --------------------------------------------------------------------------
class SparkBars(QWidget):
    """Mini bar chart, values in 0..1, painted in the given color."""

    def __init__(self, color=theme.RED, parent=None, bars=12):
        super().__init__(parent)
        self._color = QColor(color)
        self._bars = bars
        self._vals = [0.3] * bars
        self.setMinimumHeight(34)
        self.setMaximumHeight(44)

    def setValues(self, vals):
        self._vals = list(vals)[:self._bars]
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = self._bars
        w = self.width() / n
        base = QColor(self._color)
        for i, v in enumerate(self._vals):
            v = max(0.06, min(1.0, v))
            bh = v * (self.height() - 6)
            x = i * w + 1.5
            rect = QRectF(x, self.height() - bh, w - 3, bh)
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            hi = QColor(base)
            lo = QColor(base)
            lo.setAlpha(90)
            grad.setColorAt(0, hi)
            grad.setColorAt(1, lo)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(rect, 2, 2)
        p.end()


def _seeded_bars(seed_text, n=12):
    rnd = random.Random(abs(hash(seed_text)) % (2 ** 32))
    return [0.25 + rnd.random() * 0.75 for _ in range(n)]


# --------------------------------------------------------------------------
class TentacleLink(QWidget):
    """Mechanical tentacle connector (asset pack decor) between stage cards."""

    def __init__(self, parent=None, flip=False):
        super().__init__(parent)
        self._flip = flip
        self.setFixedWidth(66)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        pm = svg_pixmap("decor/tentacle-trace", 240)
        if not pm.isNull():
            # 1200x360 artwork -> fit width, keep aspect, center vertically
            dw, dh = W - 4, int((W - 4) * 360 / 1200)
            y = (H - dh) // 2
            if self._flip:
                p.save()
                p.translate(W, 0)
                p.scale(-1, 1)
                p.drawPixmap(2, y, dw, dh, pm)
                p.restore()
            else:
                p.drawPixmap(2, y, dw, dh, pm)
            p.end()
            return
        # compact fallback: steel curve with red joints
        p.setPen(QPen(QColor(theme.STEEL), 3))
        p.drawLine(2, H // 2, W - 2, H // 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(theme.RED)))
        for x in (W * 0.25, W * 0.5, W * 0.75):
            p.drawEllipse(QPointF(x, H / 2), 4, 4)
        p.end()


# --------------------------------------------------------------------------
class HubEye(QWidget):
    """Reactor-core ornament (asset pack) — the pipeline hub medallion."""

    def __init__(self, parent=None, size=58):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pm = svg_pixmap("decor/reactor-core", max(64, self.width() * 2))
        if not pm.isNull():
            s = self.width()
            p.drawPixmap(0, 0, s, s, pm)
            p.end()
            return
        # compact fallback: red glowing core
        cx, cy = self.width() / 2, self.height() / 2
        R = min(cx, cy) - 2
        g0 = QRadialGradient(cx, cy, R + 8)
        rc = QColor(theme.RED)
        rc.setAlpha(80)
        g0.setColorAt(0, rc)
        g0.setColorAt(1, QColor(255, 59, 48, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g0))
        p.drawEllipse(QPointF(cx, cy), R + 8, R + 8)
        p.setBrush(QBrush(QColor(theme.RED)))
        p.drawEllipse(QPointF(cx, cy), R - 6, R - 6)
        p.end()


# --------------------------------------------------------------------------
class ThumbLabel(QLabel):
    """Video thumbnail: shows a real image when image_path is given,
    otherwise the dark placeholder with a play glyph."""

    def __init__(self, accent=theme.BLUE, parent=None, w=58, h=58, image_path=None):
        super().__init__(parent)
        self._accent = QColor(accent)
        self._img = None
        if image_path:
            from PyQt6.QtGui import QPixmap
            import os as _os
            if _os.path.exists(image_path):
                self._img = QPixmap(image_path)
        self.setFixedSize(w, h)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        if self._img and not self._img.isNull():
            # cover-crop the image into a rounded rect
            path = QPainterPath()
            path.addRoundedRect(r, 6, 6)
            p.setClipPath(path)
            iw, ih = self._img.width(), self._img.height()
            s = max(r.width() / iw, r.height() / ih)
            dw, dh = iw * s, ih * s
            p.drawPixmap(int(r.x() + (r.width() - dw) / 2),
                         int(r.y() + (r.height() - dh) / 2),
                         int(dw), int(dh), self._img)
            p.setClipping(False)
            p.setPen(QPen(QColor(theme.STEEL), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 6, 6)
            # small play glyph, bottom-right
            cx, cy = r.right() - 14, r.bottom() - 14
            tri = QPolygonF([QPointF(cx - 5, cy - 7), QPointF(cx - 5, cy + 7),
                             QPointF(cx + 6, cy)])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(0, 0, 0, 140)))
            p.drawEllipse(QPointF(cx, cy), 11, 11)
            p.setBrush(QBrush(QColor(255, 255, 255, 230)))
            p.drawPolygon(tri)
            p.end()
            return
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#1b2029"))
        g.setColorAt(1, QColor("#0a0c10"))
        p.setPen(QPen(QColor(theme.STEEL), 1))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 6, 6)
        # scan lines
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        for y in range(6, self.height() - 4, 6):
            p.drawLine(4, y, self.width() - 4, y)
        # play triangle
        cx, cy = self.width() / 2, self.height() / 2
        tri = QPolygonF([QPointF(cx - 7, cy - 10), QPointF(cx - 7, cy + 10),
                         QPointF(cx + 9, cy)])
        glow = QColor(self._accent)
        glow.setAlpha(50)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), 16, 16)
        p.setBrush(QBrush(self._accent))
        p.drawPolygon(tri)
        p.end()


# --------------------------------------------------------------------------
class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(16, 14, 16, 14)
        self._lay.setSpacing(8)

    def add(self, w):
        from PyQt6.QtWidgets import QLayout
        if isinstance(w, QLayout):
            self._lay.addLayout(w)
        else:
            self._lay.addWidget(w)
        return w

    def layout_(self):
        return self._lay


class StatTile(Card):
    """Dashboard stat tile: title + pack icon, big value, delta, mini bar chart."""

    ICONS = {"green": "check", "amber": "zap", "blue": "cpu", "red": "play"}

    def __init__(self, title, accent="green", bar_color=None, parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setProperty("accent", accent)
        self.layout_().setContentsMargins(8, 8, 8, 8)
        self.layout_().setSpacing(4)
        self._accent = accent
        self._bar_color = bar_color or {"green": theme.GREEN, "amber": theme.AMBER,
                                       "blue": theme.BLUE, "red": theme.RED}[accent]
        lay = self.layout_()
        top = QHBoxLayout()
        t = _lbl(title, "StatTitle")
        top.addWidget(t)
        top.addStretch()
        self._icon = svg_label(self.ICONS.get(accent, "check"), 20, self._bar_color)
        top.addWidget(self._icon)
        lay.addLayout(top)
        self._value = _lbl("0", "Big")
        self._value.setStyleSheet("font-size: 21px; font-weight: 800; background: transparent;")
        lay.addWidget(self._value)
        self._delta = QLabel("")
        self._delta.setObjectName("StatUp")
        lay.addWidget(self._delta)
        brow = QHBoxLayout()
        brow.addStretch()
        self._bars = SparkBars(self._bar_color)
        self._bars.setFixedWidth(72)
        brow.addWidget(self._bars)
        lay.addLayout(brow)
        self.style().unpolish(self)

    def set(self, value, delta=""):
        self._value.setText(str(value))
        self._delta.setText(delta)
        self._bars.setValues(_seeded_bars(f"{self._accent}:{value}"))


class PipelineCard(QFrame):
    """Live Fetch/Render/Upload stage card driven by worker threads.
    icon is a pack SVG name (cloud / render / upload)."""

    def __init__(self, title, color, icon="cpu", parent=None):
        super().__init__(parent)
        self.setObjectName("StageCard")
        self.setProperty("accent", color)
        self._color = color
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        top = QHBoxLayout()
        self._icon = svg_label(icon, 26, self._css())
        top.addWidget(self._icon)
        t = QLabel(title)
        t.setObjectName("StageTitle")
        top.addWidget(t)
        top.addStretch()
        self.badge = pill("Idle", "gray")
        top.addWidget(self.badge)
        lay.addLayout(top)
        prow = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setObjectName("PipeBar")
        self.bar.setProperty("color", color)
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.pct = QLabel("0%")
        self.pct.setObjectName("PctBig")
        prow.addWidget(self.bar, 1)
        prow.addWidget(self.pct)
        lay.addLayout(prow)
        self.detail = QLabel("—")
        self.detail.setObjectName("StageDetail")
        self.detail.setWordWrap(True)
        lay.addWidget(self.detail)
        brow = QHBoxLayout()
        brow.addStretch()
        self.retries = pill("0 retries", "gray")
        brow.addWidget(self.retries)
        lay.addLayout(brow)
        self.style().unpolish(self)

    def _css(self):
        return {"green": theme.GREEN, "amber": theme.AMBER, "blue": theme.BLUE,
                "violet": theme.VIOLET, "cyan": theme.CYAN,
                "gray": theme.MUTED}.get(self._color, theme.MUTED)

    def update(self, label, progress, detail, retries):
        color_map = {"Running": "green", "Processing": "amber", "Uploading": "blue",
                     "Downloading": "violet", "Cleaning": "gray", "Armed": "gray",
                     "Done": "green", "Posted": "green", "Idle": "gray", "Paused": "amber",
                     "Retrying": "red", "Failed": "red"}
        bc = color_map.get(label, "gray")
        self.badge.setText(label)
        self.badge.setProperty("color", bc)
        self.bar.setValue(int(progress))
        self.pct.setText(f"{int(progress)}%")
        self.detail.setText(detail)
        self.retries.setText(f"{retries} retr{'y' if retries == 1 else 'ies'}")
        self.retries.setProperty("color", "red" if retries else "gray")
        for w in (self.badge, self.retries, self.bar):
            w.style().unpolish(w)
            w.style().polish(w)


class TimelineCard(QFrame):
    """One item on the scheduler timeline strip."""

    STATE_TXT = {"posted": "✓ Posted", "now": "● Now", "queued": "○ Queued",
                 "failed": "✕ Failed"}
    STATE_ACCENT = {"posted": theme.GREEN, "now": theme.BLUE,
                    "queued": theme.MUTED, "failed": theme.RED}

    def __init__(self, time_str, state, title, subtitle, parent=None, thumb=None):
        super().__init__(parent)
        self.setObjectName("TlCard")
        self.setProperty("state", state)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)
        lay.addWidget(ThumbLabel(self.STATE_ACCENT.get(state, theme.BLUE),
                                 image_path=thumb))
        col = QVBoxLayout()
        col.setSpacing(2)
        tm = QLabel(time_str)
        tm.setStyleSheet("font-weight:800; font-size:13px; background: transparent;")
        col.addWidget(tm)
        st = QLabel(self.STATE_TXT.get(state, state))
        st.setObjectName("TlState")
        st.setProperty("state", state)
        col.addWidget(st)
        ti = QLabel(title)
        ti.setStyleSheet("font-weight:700; font-size:12px; background: transparent;")
        ti.setWordWrap(True)
        col.addWidget(ti)
        sub = QLabel(subtitle)
        sub.setObjectName("Muted")
        col.addWidget(sub)
        lay.addLayout(col, 1)
        self.style().unpolish(self)


class HealthRow(QWidget):
    ICON_COLORS = {"check": theme.GREEN, "warning": theme.AMBER,
                   "error": theme.RED, "info": theme.BLUE,
                   "shield": theme.GREEN, "lock": theme.GREEN,
                   "globe": theme.BLUE, "refresh": theme.CYAN}

    def __init__(self, text, ok=True, parent=None, icon=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(10)
        name = icon or ("check" if ok else "error")
        dot = svg_label(name, 16, self.ICON_COLORS.get(name,
                        theme.GREEN if ok else theme.RED))
        lay.addWidget(dot)
        t = QLabel(text)
        t.setStyleSheet("font-size: 12px; background: transparent;")
        lay.addWidget(t, 1)


class CircleAvatar(QLabel):
    """Circular operator avatar with a green status ring."""

    def __init__(self, pixmap=None, size=46, parent=None):
        super().__init__(parent)
        self._pm = pixmap
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        R = min(cx, cy) - 1
        if self._pm and not self._pm.isNull():
            # circular clip
            path = QPainterPath()
            path.addEllipse(QPointF(cx, cy), R - 2, R - 2)
            p.setClipPath(path)
            scaled = self._pm.scaled(int(R * 2), int(R * 2),
                                     Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                     Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(int(cx - R), int(cy - R), scaled)
            p.setClipping(False)
        else:
            p.setBrush(QBrush(QColor(theme.PANEL3)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), R - 2, R - 2)
        p.setPen(QPen(QColor(theme.GREEN), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R - 1, R - 1)
        p.end()


class NotifBell(QWidget):
    """Bell icon button with a red notification dot (decorative)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Notifications")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        g = QRadialGradient(cx - 6, cy - 6, 24)
        g.setColorAt(0, QColor(theme.PANEL3))
        g.setColorAt(1, QColor(theme.PANEL))
        p.setPen(QPen(QColor(theme.STEEL), 1))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), 15, 15)
        # pack bell icon (no emoji)
        pm = svg_pixmap("bell", 18, theme.TEXT)
        if not pm.isNull():
            p.drawPixmap(int(cx - 9), int(cy - 9), 18, 18, pm)
        # red dot
        dot = QRadialGradient(cx + 9, cy - 9, 6)
        dot.setColorAt(0, QColor("#ff7a84"))
        dot.setColorAt(1, QColor(theme.RED))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(dot))
        p.drawEllipse(QPointF(cx + 9, cy - 9), 5, 5)
        p.end()


class NavItem(QWidget):
    """Sidebar navigation item: pack icon + two-line title/sub, clickable,
    red active glow."""

    def __init__(self, key, icon, title, sub, on_click, parent=None):
        super().__init__(parent)
        self.key = key
        self._icon_name = icon
        self._on_click = on_click
        self.setObjectName("NavItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(0)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.icon_lbl = svg_label(icon, 20, theme.MUTED)
        row.addWidget(self.icon_lbl)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("NavTitle")
        row.addWidget(self.title_lbl, 1)
        lay.addLayout(row)
        self.sub_lbl = QLabel(sub)
        self.sub_lbl.setObjectName("NavSub")
        lay.addWidget(self.sub_lbl)

    def mousePressEvent(self, e):
        self._on_click(self.key)
        super().mousePressEvent(e)

    def set_active(self, active):
        col = theme.RED if active else theme.MUTED
        pm = svg_pixmap(self._icon_name, 20, col)
        if not pm.isNull():
            self.icon_lbl.setPixmap(pm)
        for w in (self, self.title_lbl):
            w.setProperty("active", "true" if active else "false")
            w.style().unpolish(w)
            w.style().polish(w)
