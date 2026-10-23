"""UI styling, color palette, and stylesheet definitions."""

# Color Palette
BG_DARK = "#12151c"
BG_PANEL = "#1a1f2c"
BG_CARD = "#212738"
BG_CARD_HOVER = "#2a3247"
BORDER_COLOR = "#2e374d"

TEXT_PRIMARY = "#f0f4fc"
TEXT_SECONDARY = "#94a3b8"
TEXT_MUTED = "#64748b"

COLOR_ACCENT = "#38bdf8"       # Cyan
COLOR_CHARGE = "#22c55e"       # Bright Green
COLOR_DISCHARGE = "#f59e0b"    # Amber / Orange
COLOR_REST = "#94a3b8"         # Slate Gray
COLOR_DANGER = "#ef4444"       # Red / Alarm
COLOR_WARNING = "#eab308"      # Yellow

def get_main_stylesheet(font_size_px: int = 13) -> str:
    return f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: {font_size_px}px;
}}

QSplitter::handle:vertical {{
    background-color: {BORDER_COLOR};
    height: 7px;
    margin: 2px 24px;
    border-radius: 3px;
}}
QSplitter::handle:vertical:hover {{
    background-color: {COLOR_ACCENT};
}}
QSplitter::handle:vertical:pressed {{
    background-color: #0284c7;
}}

QToolBar {{
    background-color: {BG_PANEL};
    border-bottom: 1px solid {BORDER_COLOR};
    padding: 6px 12px;
    spacing: 8px;
}}

QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    margin-top: 12px;
    font-weight: 600;
    padding-top: 14px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    color: {COLOR_ACCENT};
}}

QPushButton {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {BG_CARD_HOVER};
    border-color: {COLOR_ACCENT};
    color: #ffffff;
}}
QPushButton:pressed {{
    background-color: #0284c7;
    border: 2px solid {COLOR_ACCENT};
    color: #ffffff;
    padding-top: 8px;
    padding-bottom: 4px;
}}
QPushButton:disabled {{
    background-color: #161a24;
    color: {TEXT_MUTED};
    border-color: #222836;
}}

QPushButton#btn_connect {{
    background-color: #0369a1;
    color: #ffffff;
    font-weight: 700;
    border: 1px solid #0284c7;
}}
QPushButton#btn_connect:hover {{
    background-color: #0284c7;
    border-color: #38bdf8;
}}
QPushButton#btn_connect:pressed {{
    background-color: #38bdf8;
    color: #0f172a;
    border: 2px solid #bae6fd;
    font-weight: 800;
}}

QPushButton#btn_refresh {{
    font-weight: 700;
    font-size: 14px;
}}
QPushButton#btn_refresh:pressed {{
    background-color: #38bdf8;
    color: #0f172a;
}}

QPushButton#btn_start {{
    background-color: #15803d;
    color: #ffffff;
    font-weight: 700;
    border: 1px solid #16a34a;
}}
QPushButton#btn_start:hover {{
    background-color: #16a34a;
    border-color: #4ade80;
}}
QPushButton#btn_start:pressed {{
    background-color: #22c55e;
    color: #052e16;
    border: 2px solid #86efac;
    font-weight: 800;
    padding-top: 8px;
    padding-bottom: 4px;
}}

QPushButton#btn_pause {{
    background-color: #b45309;
    color: #ffffff;
    font-weight: 600;
    border: 1px solid #d97706;
}}
QPushButton#btn_pause:hover {{
    background-color: #d97706;
    border-color: #f59e0b;
}}
QPushButton#btn_pause:pressed {{
    background-color: #f59e0b;
    color: #451a03;
    border: 2px solid #fde047;
    font-weight: 800;
    padding-top: 8px;
    padding-bottom: 4px;
}}

QPushButton#btn_skip {{
    background-color: #1e293b;
    color: #f8fafc;
    font-weight: 600;
    border: 1px solid #334155;
}}
QPushButton#btn_skip:hover {{
    background-color: #334155;
    border-color: #64748b;
}}
QPushButton#btn_skip:pressed {{
    background-color: #475569;
    color: #38bdf8;
    border: 2px solid #38bdf8;
    font-weight: 800;
    padding-top: 8px;
    padding-bottom: 4px;
}}

QPushButton#btn_stop {{
    background-color: #92400e;
    color: #ffffff;
    font-weight: 600;
    border: 1px solid #f59e0b;
}}
QPushButton#btn_stop:hover {{
    background-color: #b45309;
    border-color: #fbbf24;
}}
QPushButton#btn_stop:pressed {{
    background-color: #d97706;
    color: #ffffff;
    border: 2px solid #fca5a5;
    font-weight: 800;
    padding-top: 8px;
    padding-bottom: 4px;
}}

QPushButton#btn_estop {{
    background-color: #dc2626;
    color: #ffffff;
    font-weight: 800;
    font-size: 14px;
    border: 2px solid #ef4444;
    border-radius: 6px;
    padding: 6px 18px;
}}
QPushButton#btn_estop:hover {{
    background-color: #ef4444;
    border-color: #fca5a5;
}}
QPushButton#btn_estop:pressed {{
    background-color: #ff0000;
    color: #ffffff;
    border: 3px solid #ffffff;
    font-weight: 900;
    padding-top: 8px;
    padding-bottom: 4px;
}}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 24px;
}}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border-color: {COLOR_ACCENT};
}}

QTableWidget {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    gridline-color: {BORDER_COLOR};
    color: {TEXT_PRIMARY};
    selection-background-color: #334155;
}}
QHeaderView::section {{
    background-color: {BG_CARD};
    color: {TEXT_SECONDARY};
    padding: 6px;
    border: 1px solid {BORDER_COLOR};
    font-weight: 600;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER_COLOR};
    background-color: {BG_PANEL};
    border-radius: 6px;
}}
QTabBar::tab {{
    background-color: {BG_DARK};
    color: {TEXT_SECONDARY};
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background-color: {BG_PANEL};
    color: {COLOR_ACCENT};
    font-weight: 600;
    border-top: 2px solid {COLOR_ACCENT};
}}

QStatusBar {{
    background-color: {BG_PANEL};
    border-top: 1px solid {BORDER_COLOR};
    color: {TEXT_SECONDARY};
}}
"""

MAIN_STYLESHEET = get_main_stylesheet(13)

