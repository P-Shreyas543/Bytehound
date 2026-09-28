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

MAIN_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
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
    font-weight: 500;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {BG_CARD_HOVER};
    border-color: {COLOR_ACCENT};
}}
QPushButton:pressed {{
    background-color: #171b26;
}}
QPushButton:disabled {{
    background-color: #161a24;
    color: {TEXT_MUTED};
    border-color: #222836;
}}

QPushButton#btn_start {{
    background-color: #15803d;
    color: #ffffff;
    font-weight: 700;
    border: none;
}}
QPushButton#btn_start:hover {{
    background-color: #16a34a;
}}

QPushButton#btn_pause {{
    background-color: #b45309;
    color: #ffffff;
    font-weight: 600;
    border: none;
}}
QPushButton#btn_pause:hover {{
    background-color: #d97706;
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
