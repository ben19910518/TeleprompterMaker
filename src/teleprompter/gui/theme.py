"""Dark Fusion theme."""
import os

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#4c8dff"
ACCENT_HOVER = "#6aa1ff"
ACCENT_DOWN = "#3a78e6"
BG = "#15171c"          # window
SURFACE = "#1d2027"     # cards
RAISED = "#272b34"      # buttons
RAISED_HOVER = "#30353f"
INPUT = "#121419"
BORDER = "#2c313b"
BORDER_STRONG = "#3a404c"
TEXT = "#e7e9ee"
MUTED = "#8b93a3"
DISABLED = "#5d6370"
OK = "#5fd39a"

STYLESHEET = f"""
QWidget {{ font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif; font-size: 9.5pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: #2b303a; color: {TEXT}; border: 1px solid {BORDER_STRONG}; padding: 4px 6px; }}

/* ---------- header & wizard steps */
QFrame#header {{ background: #191c22; border-bottom: 1px solid {BORDER}; }}
QLabel#appTitle {{ font-size: 12pt; font-weight: bold; }}
QLabel#stepArrow {{ color: {DISABLED}; font-size: 14pt; padding: 0 2px; }}
QPushButton#step {{
    background: transparent; border: 1px solid transparent; border-radius: 15px;
    padding: 5px 16px; color: {MUTED}; font-weight: bold;
}}
QPushButton#step:hover {{ background: {RAISED}; color: {TEXT}; }}
QPushButton#step:checked {{ background: rgba(76, 141, 255, 0.16); border-color: {ACCENT}; color: #cfe0ff; }}
QPushButton#step[done="true"] {{ color: {OK}; }}
QPushButton#step[done="true"]:checked {{ color: #cfe0ff; }}
QPushButton#segLeft, QPushButton#segRight {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; padding: 4px 14px; color: {MUTED};
}}
QPushButton#segLeft {{ border-top-left-radius: 5px; border-bottom-left-radius: 5px; border-right: none; }}
QPushButton#segRight {{ border-top-right-radius: 5px; border-bottom-right-radius: 5px; }}
QPushButton#segLeft:checked, QPushButton#segRight:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton#flat {{ background: transparent; border: 1px solid transparent; padding: 4px 10px; color: {MUTED}; }}
QPushButton#flat:hover {{ background: {RAISED}; color: {TEXT}; }}
QPushButton#flat::menu-indicator {{ image: none; width: 0; }}

/* ---------- cards */
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLabel#cardTitle {{ color: #aac4f0; font-weight: bold; font-size: 10pt; }}
QLabel#projLine {{ color: {TEXT}; padding: 1px 0; }}
QGroupBox {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
    margin-top: 0px; padding: 34px 10px 10px 10px; color: #aac4f0; font-weight: bold; font-size: 10pt;
}}
QGroupBox::title {{
    subcontrol-origin: padding; subcontrol-position: top left; left: 14px; top: 10px;
    color: #aac4f0; font-weight: bold; font-size: 10pt;
}}
QWidget#settingsPanel {{ background: transparent; }}

/* ---------- buttons */
QPushButton {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 5px; padding: 5px 12px; color: {TEXT};
}}
QPushButton:hover {{ background: {RAISED_HOVER}; border-color: #4a5160; }}
QPushButton:pressed {{ background: #22262e; }}
QPushButton:disabled {{ color: {DISABLED}; background: #1f2229; border-color: {BORDER}; }}
QPushButton:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton:focus {{ outline: none; border-color: #55607a; }}
QPushButton#primary {{
    background: {ACCENT}; border: 1px solid {ACCENT}; color: white; font-size: 10.5pt; font-weight: bold;
    padding: 8px 18px; border-radius: 6px;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#primary:pressed {{ background: {ACCENT_DOWN}; }}
QPushButton#primary:disabled {{ background: #2a3a58; border-color: #2a3a58; color: #8495b3; }}
QPushButton#accent {{ background: rgba(76, 141, 255, 0.18); border-color: #3f6fc4; color: #dce8ff; font-weight: bold; }}
QPushButton#accent:hover {{ background: rgba(76, 141, 255, 0.30); }}
QPushButton#accent:disabled {{ color: {DISABLED}; background: #1f2229; border-color: {BORDER}; }}
QPushButton#small {{ padding: 3px 10px; font-size: 9pt; }}
QPushButton#nudge {{ padding: 3px 4px; min-width: 46px; font-family: "Consolas", "Microsoft YaHei UI"; font-size: 9pt; }}
QPushButton#warn {{ background: #5a3b1d; border-color: #a86a2a; color: #ffd9a8; }}

/* ---------- inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox, QPlainTextEdit {{
    background: {INPUT}; border: 1px solid {BORDER_STRONG}; border-radius: 5px; padding: 4px 6px; color: {TEXT};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QFontComboBox:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QLineEdit:read-only {{ color: #b9bfcb; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {DISABLED}; background: #17191e;
}}
QComboBox QAbstractItemView {{
    background: #1b1e24; border: 1px solid {BORDER_STRONG}; selection-background-color: {ACCENT}; outline: none;
}}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER_STRONG}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #f0f2f5; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: white; }}
QProgressBar {{ border: none; border-radius: 3px; background: {INPUT}; text-align: center; color: {TEXT}; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

/* ---------- tables */
QTableWidget {{
    background: {INPUT}; alternate-background-color: #171a20; border: 1px solid {BORDER}; border-radius: 5px;
    gridline-color: transparent; selection-background-color: rgba(76, 141, 255, 0.35); selection-color: white;
}}
QTableWidget::item {{ padding: 2px 6px; }}
QHeaderView::section {{
    background: #1b1e24; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER}; padding: 5px 6px; font-weight: bold;
}}
QTableCornerButton::section {{ background: #1b1e24; border: none; }}

/* ---------- scroll & split */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: #363c48; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: #4a5262; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 8px; }}
QSplitter::handle:vertical {{ height: 8px; }}
QSplitter::handle:hover {{ background: rgba(76, 141, 255, 0.25); border-radius: 3px; }}

/* ---------- menus & status */
QMenu {{ background: #1f2229; border: 1px solid {BORDER_STRONG}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QStatusBar {{ background: #191c22; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar QLabel {{ color: {MUTED}; }}

/* ---------- labels */
QLabel#hint {{ color: {MUTED}; }}
QLabel#timecode {{ font-family: "Consolas", "Cascadia Mono", monospace; font-size: 10.5pt; color: #cfd6e4; }}
QLabel#warnbox {{ background: #3b2a14; color: #ffd38a; border: 1px solid #7a5622; border-radius: 6px; padding: 7px 9px; }}
QLabel#okbox {{ background: #15332a; color: #9be7c0; border: 1px solid #285e47; border-radius: 6px; padding: 7px 9px; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(BG))
    p.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Base, QColor(INPUT))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#171a20"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2b303a"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Button, QColor(RAISED))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#666d7a"))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(DISABLED))
    app.setPalette(p)
    from ..paths import resource_dir

    def icon(name):
        return os.path.join(resource_dir(), name).replace("\\", "/")
    check = icon("check.svg")
    extra = f"""
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: top right; width: 24px;
    border: none; border-left: 1px solid {BORDER}; border-top-right-radius: 5px; border-bottom-right-radius: 5px;
}}
QComboBox::drop-down:hover {{ background: {RAISED_HOVER}; }}
QComboBox::down-arrow {{ image: url("{icon('arrow-down.svg')}"); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: url("{icon('arrow-down-disabled.svg')}"); }}
QComboBox::down-arrow:on {{ top: 1px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; border: none; border-left: 1px solid {BORDER}; background: {RAISED};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-position: top right; border-top-right-radius: 5px; border-bottom: 1px solid {BORDER};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 5px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: #3a404c; }}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{ background: {ACCENT}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{icon('arrow-up.svg')}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{icon('arrow-down.svg')}"); width: 10px; height: 10px; }}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QSpinBox::up-arrow:off, QDoubleSpinBox::up-arrow:off {{ image: url("{icon('arrow-up-disabled.svg')}"); }}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled,
QSpinBox::down-arrow:off, QDoubleSpinBox::down-arrow:off {{ image: url("{icon('arrow-down-disabled.svg')}"); }}
QCheckBox {{ spacing: 7px; background: transparent; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #6c7383; border-radius: 4px; background: {INPUT}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url("{check}"); }}
QCheckBox::indicator:disabled {{ border-color: #444a56; background: #1f2229; }}
"""
    app.setStyleSheet(STYLESHEET + extra)
    app.setFont(QFont("Microsoft YaHei UI", 9))
