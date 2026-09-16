"""Analytics: matplotlib charts from the DB — uploads/day, success rate, per-platform."""
import matplotlib
matplotlib.use("qtagg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QMessageBox

from .. import theme
from ..widgets import h1, muted, Card, h2


class ChartCard(Card):
    def __init__(self, title):
        super().__init__()
        self.add(h2(title))
        self.fig = Figure(figsize=(5, 3), dpi=100, facecolor=theme.PANEL)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.add(self.canvas)

    def axes(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(theme.PANEL)
        for spine in ax.spines.values():
            spine.set_color(theme.BORDER)
        ax.tick_params(colors=theme.MUTED, labelsize=9)
        ax.title.set_color(theme.TEXT)
        return ax

    def draw(self):
        self.fig.tight_layout()
        self.canvas.draw()


class Analytics(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(h1("Analytics"))
        head.addStretch()
        exp = QPushButton("⬇ Export report CSV")
        exp.clicked.connect(self._export)
        head.addWidget(exp)
        lay.addLayout(head)
        lay.addWidget(muted("Performance Insights — computed live from your local database."))

        row = QHBoxLayout()
        self.c_daily = ChartCard("Uploads per day (14d)")
        self.c_plat = ChartCard("Posted by platform")
        row.addWidget(self.c_daily, 1)
        row.addWidget(self.c_plat, 1)
        lay.addLayout(row, 1)
        row2 = QHBoxLayout()
        self.c_rate = ChartCard("Success vs failed")
        self.c_hours = ChartCard("Best posting hours (IST)")
        row2.addWidget(self.c_rate, 1)
        row2.addWidget(self.c_hours, 1)
        lay.addLayout(row2, 1)
        self.refresh()

    def refresh(self):
        db = self.app.db
        # uploads/day
        rows = db.uploads_per_day(14)
        ax = self.c_daily.axes()
        if rows:
            days = [r["d"][5:] for r in rows]
            ax.bar(days, [r["reels"] + r["shorts"] for r in rows],
                   label="Shorts", color=theme.AMBER, alpha=.85)
            ax.set_xticks(range(len(days)))
            ax.set_xticklabels(days, rotation=45, ha="right", fontsize=8)
            ax.legend(facecolor=theme.PANEL2, edgecolor=theme.BORDER, labelcolor=theme.TEXT)
        else:
            ax.text(0.5, 0.5, "No data yet", ha="center", color=theme.MUTED)
        self.c_daily.draw()
        # platform totals
        totals = db.platform_totals()
        ax = self.c_plat.axes()
        if totals:
            ax.bar(list(totals.keys()), list(totals.values()),
                   color=[theme.GREEN, theme.AMBER][:len(totals)])
            for i, v in enumerate(totals.values()):
                ax.text(i, v, str(v), ha="center", va="bottom", color=theme.TEXT)
        else:
            ax.text(0.5, 0.5, "No data yet", ha="center", color=theme.MUTED)
        self.c_plat.draw()
        # success vs failed
        tot = db.query_one("SELECT COUNT(*) c FROM uploads_log WHERE status IN ('posted','failed')")["c"] or 0
        ok = db.query_one("SELECT COUNT(*) c FROM uploads_log WHERE status='posted'")["c"] or 0
        ax = self.c_rate.axes()
        if tot:
            ax.pie([ok, tot - ok], labels=["Posted", "Failed"],
                   colors=[theme.GREEN, theme.RED], autopct="%1.1f%%",
                   textprops={"color": theme.TEXT})
        else:
            ax.text(0.5, 0.5, "No data yet", ha="center", color=theme.MUTED)
        self.c_rate.draw()
        # posting hours
        hours = db.posted_hours()
        ax = self.c_hours.axes()
        if hours:
            hs = sorted(hours)
            ax.bar(hs, [hours[h] for h in hs], color=theme.CYAN, alpha=.85)
            ax.set_xlabel("Hour (IST)", color=theme.MUTED)
            ax.set_xticks(range(0, 24, 3))
        else:
            ax.text(0.5, 0.5, "No data yet", ha="center", color=theme.MUTED)
        self.c_hours.draw()

    def _export(self):
        from ...core.reports import export_uploads_csv
        path, _ = QFileDialog.getSaveFileName(self, "Export analytics CSV",
                                              "octora-analytics.csv", "CSV (*.csv)")
        if path:
            export_uploads_csv(self.app.db, path)
            QMessageBox.information(self, "Export", f"Saved:\n{path}")
