"""
Entry point for Tonal music player.

Usage:
    python -m tonal
    # or, after install:
    tonal
"""

import sys

# Suppress the Qt multimedia backend warning on macOS in dev mode
import os
os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")


def main() -> None:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon

    # High-DPI support (Qt 6 enables this automatically, but be explicit)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Tonal")
    app.setOrganizationName("Tonal")
    app.setApplicationVersion("1.0.0")

    # Set app icon if bundled asset exists
    _set_app_icon(app)

    # Apply dark theme
    from tonal.ui.theme import apply_theme
    apply_theme(app)

    from tonal.ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


def _set_app_icon(app) -> None:
    """Attempt to load a bundled icon; silently skip if missing."""
    from PySide6.QtGui import QIcon
    import importlib.resources

    # Try several candidate paths (works both in dev and PyInstaller bundle)
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons", "tonal.png"),
        os.path.join(sys._MEIPASS, "assets", "icons", "tonal.png") if hasattr(sys, "_MEIPASS") else "",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            app.setWindowIcon(QIcon(path))
            return


if __name__ == "__main__":
    main()
