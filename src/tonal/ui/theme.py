"""
Dark purple/slate colour theme for Tonal.

Apply once with:
    from tonal.ui.theme import apply_theme
    apply_theme(app)
"""

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor

# ---------------------------------------------------------------------------
# Colour palette constants
# ---------------------------------------------------------------------------
BG_DEEP    = "#0f0f1e"   # darkest background (player bar, header)
BG_BASE    = "#1a1a2e"   # main window background
BG_RAISED  = "#16213e"   # sidebar / raised panels
BG_SURFACE = "#1e1e35"   # table alternate row
BG_HOVER   = "#2d2d4e"   # hover state
BG_BORDER  = "#2d2d4e"   # dividers / borders

ACCENT     = "#7c6af7"   # primary accent (play button, selection, seek)
ACCENT_HOV = "#9b8dff"   # accent on hover

TEXT_PRIMARY   = "#e8e8f0"
TEXT_SECONDARY = "#9090b0"
TEXT_MUTED     = "#60607a"

# ---------------------------------------------------------------------------
# Qt Style Sheet
# ---------------------------------------------------------------------------
QSS = f"""
/* ── Global ─────────────────────────────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {BG_BASE};
    color: {TEXT_PRIMARY};
    font-size: 13px;
}}

QDialog {{
    background-color: {BG_BASE};
    color: {TEXT_PRIMARY};
}}

/* ── Splitter ─────────────────────────────────────────────────────────*/
QSplitter::handle {{
    background-color: {BG_BORDER};
    width: 1px;
    height: 1px;
}}

/* ── Left sidebar / library panel ────────────────────────────────────*/
QListWidget {{
    background-color: rgba(22, 33, 62, 205);
    border: none;
    outline: none;
    padding: 4px 0;
}}
QListWidget::item {{
    padding: 9px 16px;
    border-radius: 6px;
    color: {TEXT_SECONDARY};
    margin: 1px 6px;
}}
QListWidget::item:hover {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
QListWidget::item:selected {{
    background-color: {ACCENT};
    color: #ffffff;
}}

/* ── Track table ─────────────────────────────────────────────────────*/
QTableWidget {{
    background-color: rgba(18, 18, 38, 185);
    alternate-background-color: rgba(26, 26, 50, 175);
    border: none;
    outline: none;
    gridline-color: transparent;
    selection-background-color: {BG_HOVER};
    selection-color: {TEXT_PRIMARY};
}}
QTableWidget::item {{
    padding: 5px 8px;
    border: none;
    color: {TEXT_SECONDARY};
}}
QTableWidget::item:selected {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
QTableWidget::item:hover {{
    background-color: {BG_SURFACE};
}}

/* Currently-playing row is handled in Python via setForeground/setBackground */

QHeaderView {{
    background-color: rgba(22, 33, 62, 200);
    border: none;
}}
QHeaderView::section {{
    background-color: rgba(22, 33, 62, 200);
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BG_BORDER};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QHeaderView::section:hover {{
    background-color: {BG_HOVER};
    color: {TEXT_SECONDARY};
}}

/* ── Player bar (objectName="playerBar") ─────────────────────────────*/
#playerBar {{
    background-color: rgba(8, 8, 20, 220);
    border-top: 1px solid rgba(60, 60, 100, 180);
}}

/* ── Buttons ─────────────────────────────────────────────────────────*/
QPushButton {{
    background-color: transparent;
    border: none;
    color: {TEXT_SECONDARY};
    padding: 5px 8px;
    border-radius: 4px;
    font-size: 18px;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
QPushButton:pressed {{
    background-color: {BG_BORDER};
}}
QPushButton:checked {{
    color: {ACCENT};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
}}

/* Play / pause big button */
QPushButton#btnPlayPause {{
    background-color: {ACCENT};
    color: #ffffff;
    border-radius: 20px;
    font-size: 20px;
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
    padding: 0;
}}
QPushButton#btnPlayPause:hover {{
    background-color: {ACCENT_HOV};
}}
QPushButton#btnPlayPause:pressed {{
    background-color: {ACCENT};
}}

/* Small icon buttons (prev/next/shuffle/repeat) */
QPushButton#btnSmall {{
    font-size: 18px;
    min-width: 32px;
    min-height: 32px;
    padding: 4px;
}}

/* Sidebar "Add folder" / "Remove" */
QPushButton#btnSidebar {{
    font-size: 11px;
    padding: 4px 10px;
    background-color: {BG_HOVER};
    color: {TEXT_SECONDARY};
    border-radius: 4px;
}}
QPushButton#btnSidebar:hover {{
    background-color: {BG_BORDER};
    color: {TEXT_PRIMARY};
}}

/* ── Sliders ─────────────────────────────────────────────────────────*/
QSlider::groove:horizontal {{
    height: 4px;
    background-color: {BG_HOVER};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background-color: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background-color: #ffffff;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{
    background-color: {ACCENT_HOV};
    width: 14px;
    height: 14px;
    margin: -5px 0;
}}

/* Volume slider (thinner) */
QSlider#volumeSlider::groove:horizontal {{
    height: 3px;
}}
QSlider#volumeSlider::handle:horizontal {{
    width: 10px;
    height: 10px;
    margin: -3.5px 0;
}}

/* ── Search box ──────────────────────────────────────────────────────*/
QLineEdit {{
    background-color: {BG_HOVER};
    border: 1px solid {BG_BORDER};
    border-radius: 14px;
    padding: 5px 12px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{
    border-color: {ACCENT};
    background-color: {BG_SURFACE};
}}
QLineEdit::placeholder {{
    color: {TEXT_MUTED};
}}

/* ── Scroll bars ─────────────────────────────────────────────────────*/
QScrollBar:vertical {{
    background-color: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {BG_HOVER};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {BG_BORDER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    height: 6px;
    background-color: transparent;
}}
QScrollBar::handle:horizontal {{
    background-color: {BG_HOVER};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Labels ──────────────────────────────────────────────────────────*/
QLabel#trackTitle {{
    font-size: 14px;
    font-weight: bold;
    color: {TEXT_PRIMARY};
}}
QLabel#trackArtist {{
    font-size: 12px;
    color: {TEXT_SECONDARY};
}}
QLabel#timeLabel {{
    font-size: 11px;
    color: {TEXT_MUTED};
    font-family: "SF Mono", "Menlo", "Courier New", monospace;
    min-width: 38px;
}}
QLabel#sectionHeader {{
    font-size: 10px;
    font-weight: 700;
    color: {TEXT_MUTED};
    letter-spacing: 1px;
    padding: 6px 16px 2px 16px;
    text-transform: uppercase;
}}
QLabel#statusLabel {{
    font-size: 11px;
    color: {TEXT_MUTED};
    padding: 2px 6px;
}}

/* ── Tab widget ──────────────────────────────────────────────────────*/
QTabWidget#mainTabs {{
    background-color: transparent;
}}
QTabWidget#mainTabs::pane {{
    background-color: transparent;
    border: none;
}}
QTabWidget#mainTabs > QTabBar {{
    background-color: {BG_DEEP};
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_MUTED};
    padding: 9px 20px;
    font-size: 13px;
    font-weight: 500;
    border: none;
    border-bottom: 2px solid transparent;
    min-width: 120px;
}}
QTabBar::tab:hover {{
    color: {TEXT_SECONDARY};
    background-color: rgba(45, 45, 78, 120);
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
    background-color: rgba(124, 106, 247, 15);
}}
QTabBar::tab:!selected {{
    margin-top: 2px;
}}
/* Inner selector tabs (song picker in alarm dialog) */
QTabWidget#selectorTabs::pane {{
    background-color: rgba(22, 33, 62, 200);
    border: 1px solid {BG_BORDER};
    border-radius: 6px;
}}
QTabWidget#selectorTabs > QTabBar::tab {{
    padding: 6px 14px;
    font-size: 12px;
    min-width: 80px;
}}

/* ── Status bar ──────────────────────────────────────────────────────*/
QStatusBar {{
    background-color: {BG_DEEP};
    color: {TEXT_MUTED};
    font-size: 11px;
    border-top: 1px solid {BG_BORDER};
}}

/* ── Spin / date-time editors ────────────────────────────────────────*/
QTimeEdit, QDateTimeEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {BG_HOVER};
    border: 1px solid {BG_BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
}}
QTimeEdit:focus, QDateTimeEdit:focus {{
    border-color: {ACCENT};
}}
QTimeEdit::up-button, QTimeEdit::down-button {{
    width: 0;
    height: 0;
}}

/* ── Checkbox ────────────────────────────────────────────────────────*/
QCheckBox {{
    color: {TEXT_SECONDARY};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BG_BORDER};
    border-radius: 3px;
    background-color: {BG_HOVER};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Progress bar ────────────────────────────────────────────────────*/
QProgressBar {{
    background-color: {BG_HOVER};
    border-radius: 2px;
    border: none;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 2px;
}}

/* ── Tooltip ─────────────────────────────────────────────────────────*/
QToolTip {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
    border: 1px solid {BG_BORDER};
    padding: 4px 8px;
    border-radius: 4px;
}}

/* ── Menu / context menu ─────────────────────────────────────────────*/
QMenu {{
    background-color: {BG_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BG_BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 20px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: #ffffff;
}}
QMenu::separator {{
    height: 1px;
    background-color: {BG_BORDER};
    margin: 3px 8px;
}}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the Tonal dark theme to the given QApplication."""
    app.setStyleSheet(QSS)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(BG_BASE))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base,            QColor(BG_RAISED))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_SURFACE))
    palette.setColor(QPalette.ColorRole.Text,            QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button,          QColor(BG_HOVER))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_MUTED))
    app.setPalette(palette)
