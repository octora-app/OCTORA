"""OCTORA theme — EXACT tokens from the official asset pack (tokens.css).

Visual rules (asset pack README):
- base near-black blue/graphite; primary action cyan/green
- warning/processing amber; critical/error red
- red ONLY for alerts, active critical controls, reactor cores
- text near-white; muted text stays >= #91A2A9
"""
BG = "#070B0E"
PANEL = "#0D1418"
PANEL2 = "#121B20"
PANEL3 = "#162127"
STEEL = "#2B3A41"
STEEL_HI = "#3D4F57"
TEXT = "#F2F7F8"
MUTED = "#91A2A9"
DIM = "#5F6E75"
RED = "#FF3B30"
RED_DEEP = "#B0251C"
RED_DIM = "#5C1A15"
GREEN = "#00E6A8"
AMBER = "#FFBE4A"
BLUE = "#55A8FF"
CYAN = "#42E8FF"
VIOLET = "#a78bfa"  # legacy alias (not a pack token; avoid in new UI)

ACCENTS = {"red": RED, "cyan": CYAN, "green": GREEN, "amber": AMBER, "blue": BLUE}

# glass-over-artwork: panels float above the full-bleed background painting
GLASS = "rgba(10,12,16,0.84)"
GLASS_BAR = "rgba(8,10,14,0.90)"

# backward-compat aliases for screens not yet restyled
BORDER = STEEL
RED_DARK = RED_DEEP

# color helpers for QPainter work
from PyQt6.QtGui import QColor  # noqa: E402


def qc(hexstr: str) -> "QColor":
    return QColor(hexstr)


def stylesheet(accent: str = "red") -> str:
    ac = ACCENTS.get(accent, RED)
    return f"""
* {{ font-family: 'Segoe UI', 'Inter', 'Noto Sans', sans-serif; }}
QMainWindow {{ background: transparent; color: {TEXT}; }}
QWidget#Root {{ background: transparent; color: {TEXT}; }}
QWidget {{ background: transparent; color: {TEXT}; }}
QWidget#qt_scrollarea_viewport {{ background: transparent; }}
QMenu {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {STEEL}; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {STEEL}; }}
QAbstractScrollArea {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}

/* ---------- top bar ---------- */
QWidget#TopBar {{ background: {GLASS_BAR}; border-bottom: 1px solid {STEEL}; }}
QLabel#LogoText {{ font-size: 30px; font-weight: 900; letter-spacing: 4px; color: {TEXT}; }}
QLabel#LogoSub {{ font-size: 10px; letter-spacing: 5px; color: {MUTED}; }}
QLabel#Powered {{ font-size: 12px; color: {TEXT}; font-weight: 600; }}
QLabel#Powered b {{ color: {TEXT}; }}
QLabel#Clock {{ font-size: 19px; font-weight: 800; color: {TEXT}; }}
QLabel#ClockSub {{ font-size: 11px; color: {MUTED}; }}
QLabel#LiveDot {{ font-size: 13px; font-weight: 800; color: {GREEN}; }}
QLabel#LiveSub {{ font-size: 11px; color: {GREEN}; }}
QWidget#Chip {{
    background: {PANEL2}; border: 1px solid {STEEL}; border-radius: 12px;
}}
QLabel#OpName {{ font-size: 14px; font-weight: 700; color: {TEXT}; }}
QLabel#OpRole {{ font-size: 11px; color: {MUTED}; }}
QPushButton#IconBtn {{
    background: {PANEL3}; border: 1px solid {STEEL}; border-radius: 16px;
    padding: 0px; min-width: 32px; min-height: 32px;
    max-width: 32px; max-height: 32px;
}}
QPushButton#IconBtn:hover {{ border-color: {ac}; }}
QLabel#TopQuote {{ font-size: 10px; letter-spacing: 2px; color: {MUTED}; }}
QLabel#TopQuoteScript {{ font-size: 15px; font-style: italic; color: {TEXT}; }}

/* ---------- sidebar ---------- */
QWidget#SideBar {{ background: {GLASS_BAR}; border-right: 1px solid {STEEL}; }}
QLabel#NavTitle {{ font-size: 14px; font-weight: 700; color: {MUTED}; }}
QLabel#NavSub {{ font-size: 10px; color: {DIM}; padding-left: 32px; }}
QWidget#NavItem {{ border-left: 3px solid transparent; }}
QWidget#NavItem:hover {{ background: {PANEL2}; }}
QWidget#NavItem:hover QLabel#NavTitle {{ color: {TEXT}; }}
QWidget#NavItem[active="true"] {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(255,59,48,0.28), stop:1 rgba(255,59,48,0.04));
    border-left: 3px solid {RED};
}}
QWidget#NavItem[active="true"] QLabel#NavTitle {{ color: {RED}; font-weight: 800; }}
QLabel#SideFoot1 {{ font-size: 11px; color: {MUTED}; }}
QLabel#SideFoot2 {{ font-size: 15px; font-weight: 800; color: {TEXT}; letter-spacing: 1px; }}
QLabel#SideFoot3 {{ font-size: 8px; letter-spacing: 2px; color: {DIM}; }}
QLabel#SideScript {{ font-size: 13px; font-style: italic; color: {RED}; }}

/* ---------- cards ---------- */
QWidget#Card, QFrame#Card {{
    background: {GLASS}; border: 1px solid {STEEL}; border-radius: 10px;
}}
QLabel#H1 {{ font-size: 34px; font-weight: 800; color: {TEXT}; }}
QLabel#H2 {{ font-size: 24px; font-weight: 750; color: {TEXT}; }}
QLabel#Muted {{ color: {MUTED}; font-size: 12px; font-weight: 600; }}
QLabel#Big {{ font-size: 34px; font-weight: 800; color: {TEXT}; }}
QLabel#StatUp {{ color: {GREEN}; font-size: 11px; font-weight: 600; }}
QLabel#StatTitle {{ color: {MUTED}; font-size: 10px; font-weight: 600; }}
QLabel#Quote {{ color: {MUTED}; font-style: italic; font-size: 11px; }}
QLabel#QuoteBox {{
    color: {TEXT}; font-size: 10px; letter-spacing: 1px;
    background: rgba(255,59,48,0.08); border: 1px solid {RED_DIM}; border-radius: 8px;
    padding: 10px;
}}
QLabel#PanelTag {{
    color: {BLUE}; font-size: 10px; letter-spacing: 3px; font-weight: 700;
}}
QLabel#TimeChip {{
    background: {PANEL2}; border: 1px solid {STEEL}; border-radius: 8px;
    padding: 5px 12px; font-size: 12px; color: {TEXT};
}}
QLabel#PctBig {{ font-size: 20px; font-weight: 800; color: {TEXT}; }}

/* stat cards get their accent via dynamic property */
QFrame#StatCard {{ border-radius: 10px; border: 1px solid {STEEL};
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(22,33,39,0.92), stop:1 rgba(10,12,16,0.92)); }}
QFrame#StatCard[accent="green"] {{ border: 1px solid #0F5C44;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(8,64,48,0.88), stop:1 rgba(8,14,12,0.92)); }}
QFrame#StatCard[accent="amber"] {{ border: 1px solid #6B4A15;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(74,52,18,0.88), stop:1 rgba(14,12,8,0.92)); }}
QFrame#StatCard[accent="blue"] {{ border: 1px solid #1E4A66;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(18,58,84,0.88), stop:1 rgba(8,12,16,0.92)); }}
QFrame#StatCard[accent="red"] {{ border: 1px solid {RED_DIM};
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(84,24,20,0.88), stop:1 rgba(16,8,10,0.92)); }}

/* pipeline stage cards */
QFrame#StageCard {{ background: {GLASS}; border-radius: 12px; border: 2px solid {STEEL}; }}
QFrame#StageCard[accent="green"] {{ border: 2px solid #0F8A5E; }}
QFrame#StageCard[accent="amber"] {{ border: 2px solid #8A5F1C; }}
QFrame#StageCard[accent="blue"] {{ border: 2px solid #22708C; }}
QLabel#StageTitle {{ font-size: 21px; font-weight: 800; color: {TEXT}; }}
QLabel#StageDetail {{ font-size: 11px; color: {MUTED}; }}

/* pills / badges — 11-12px / 700 per pack hierarchy */
QLabel#Pill {{
    font-size: 11px; font-weight: 700; padding: 4px 12px; border-radius: 9px;
}}
QLabel#Pill[color="green"] {{ background: rgba(0,230,168,0.12); color: {GREEN}; border: 1px solid #0F8A5E; }}
QLabel#Pill[color="amber"] {{ background: rgba(255,190,74,0.12); color: {AMBER}; border: 1px solid #8A5F1C; }}
QLabel#Pill[color="blue"] {{ background: rgba(85,168,255,0.12); color: {BLUE}; border: 1px solid #22708C; }}
QLabel#Pill[color="red"] {{ background: rgba(255,59,48,0.14); color: {RED}; border: 1px solid {RED_DIM}; }}
QLabel#Pill[color="gray"] {{ background: {PANEL3}; color: {MUTED}; border: 1px solid {STEEL}; }}
QLabel#Pill[color="live"] {{ background: rgba(0,230,168,0.10); color: {GREEN}; border: 1px solid #0F8A5E; }}
QLabel#Badge {{ font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 8px; }}
QLabel#Badge[color="green"] {{ background: #0A2B1E; color: {GREEN}; border: 1px solid {GREEN}; }}
QLabel#Badge[color="amber"] {{ background: #2E2008; color: {AMBER}; border: 1px solid {AMBER}; }}
QLabel#Badge[color="blue"] {{ background: #0A2733; color: {CYAN}; border: 1px solid {CYAN}; }}
QLabel#Badge[color="violet"] {{ background: #1D1533; color: {VIOLET}; border: 1px solid {VIOLET}; }}
QLabel#Badge[color="cyan"] {{ background: #0A2733; color: {CYAN}; border: 1px solid {CYAN}; }}
QLabel#Badge[color="red"] {{ background: #2B0D0B; color: {RED}; border: 1px solid {RED}; }}
QLabel#Badge[color="gray"] {{ background: {PANEL2}; color: {MUTED}; border: 1px solid {STEEL}; }}

/* progress bars */
QProgressBar#PipeBar {{
    background: {PANEL3}; border: 1px solid {STEEL}; border-radius: 7px;
    height: 14px; text-align: center;
}}
QProgressBar#PipeBar::chunk {{ border-radius: 6px; }}
QProgressBar#PipeBar[color="green"]::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #00A87E, stop:1 #4DFFC4);
}}
QProgressBar#PipeBar[color="amber"]::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #D18A1D, stop:1 #FFD47A);
}}
QProgressBar#PipeBar[color="blue"]::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1D7FA8, stop:1 #8FD4FF);
}}
QProgressBar#PipeBar[color="violet"]::chunk {{ background: {VIOLET}; }}
QProgressBar#PipeBar[color="cyan"]::chunk {{ background: {CYAN}; }}
QProgressBar#PipeBar[color="gray"]::chunk {{ background: {DIM}; }}
QProgressBar {{ background: {PANEL3}; border: 1px solid {STEEL}; border-radius: 6px; height: 12px; }}
QProgressBar::chunk {{ border-radius: 5px; background: {ac}; }}

/* ---------- buttons / inputs ---------- */
QPushButton {{
    background: {PANEL2}; color: {TEXT}; border: 1px solid {STEEL};
    border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {ac}; }}
QPushButton#RedButton {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #C22430, stop:1 #6D0B13);
    border: 2px solid {RED}; color: #ffffff; font-size: 14px; font-weight: 800;
    letter-spacing: 1px; padding: 12px 22px; border-radius: 10px;
}}
QPushButton#RedButton:hover {{ background: #D92F3D; }}
QPushButton#GhostBtn {{
    background: transparent; border: 1px solid {STEEL}; border-radius: 8px;
    color: {TEXT}; font-size: 12px; font-weight: 600; padding: 7px 14px;
}}
QPushButton#GhostBtn:hover {{ border-color: {BLUE}; color: {BLUE}; }}
QPushButton#Danger {{ border-color: {RED}; color: {RED}; }}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateTimeEdit, QTimeEdit {{
    background: {PANEL2}; color: {TEXT}; border: 1px solid {STEEL};
    border-radius: 8px; padding: 7px 10px; font-size: 13px; selection-background-color: {ac};
}}
QLineEdit:focus, QTextEdit:focus {{ border: 1px solid {ac}; }}
QComboBox QAbstractItemView {{ background: {PANEL2}; color: {TEXT}; selection-background-color: {ac}; }}

/* ---------- tables ---------- */
QTableWidget {{ background: {PANEL}; alternate-background-color: {PANEL2};
    gridline-color: {STEEL}; border: 1px solid {STEEL}; border-radius: 8px; font-size: 12px; }}
QTableWidget::item {{ padding: 4px; }}
QHeaderView::section {{ background: {PANEL2}; color: {MUTED}; border: none; padding: 8px; font-weight: 700; }}

/* ---------- timeline ---------- */
QFrame#TlCard {{ background: rgba(18,22,30,0.88); border: 1px solid {STEEL}; border-radius: 10px; }}
QFrame#TlCard[state="now"] {{ border: 2px solid {BLUE}; }}
QFrame#TlCard[state="posted"] {{ border: 1px solid #0F8A5E; }}
QFrame#TlCard[state="queued"] {{ border: 1px dashed {STEEL_HI}; }}
QFrame#TlCard[state="failed"] {{ border: 1px solid {RED_DIM}; }}
QLabel#TlState {{ font-size: 11px; font-weight: 700; }}
QLabel#TlState[state="posted"] {{ color: {GREEN}; }}
QLabel#TlState[state="now"] {{ color: {BLUE}; }}
QLabel#TlState[state="queued"] {{ color: {MUTED}; }}
QLabel#TlState[state="failed"] {{ color: {RED}; }}

/* ---------- status bar ---------- */
QWidget#StatusBar {{ background: {GLASS_BAR}; border-top: 1px solid {STEEL}; }}
QLabel#ErrZero {{ color: {GREEN}; font-size: 17px; font-weight: 800; }}
QLabel#ErrSome {{ color: {RED}; font-size: 17px; font-weight: 800; }}
QLabel#FootStrip {{ color: {DIM}; font-size: 10px; letter-spacing: 3px; }}
QLabel#VerTag {{ color: {DIM}; font-size: 10px; }}

/* scrollbars */
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {STEEL}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {STEEL}; border-radius: 5px; min-width: 30px; }}
QTabWidget::pane {{ border: 1px solid {STEEL}; border-radius: 8px; background: {PANEL}; }}
QTabBar::tab {{ background: {PANEL2}; color: {MUTED}; padding: 8px 18px; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
QTabBar::tab:selected {{ background: {PANEL}; color: {ac}; font-weight: 700; }}
QCheckBox {{ color: {TEXT}; font-size: 13px; }}
"""
