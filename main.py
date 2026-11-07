"""Main entry point for Quickglint application with 1:1 hardware pixel precision."""

import os
import sys

# Force 1:1 physical pixel coordinate mapping for razor-sharp 4K/Retina screenshot capture
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"

# Explicit Windows AppUserModelID so taskbar groups properly with Quickglint branding and icon
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Quickglint.App.2.1.0")
    except Exception:
        pass

from PySide6.QtCore import QTimer


def main() -> None:
    """Initialize and run the Quickglint application."""
    from app.utils.logger import logger

    try:
        from app.application import QuickglintApp

        app = QuickglintApp(sys.argv)

        # Check command line flags
        if "--capture" in sys.argv:
            QTimer.singleShot(100, app.trigger_capture)
        elif "--pdf" in sys.argv or "--pdf-editor" in sys.argv:
            QTimer.singleShot(100, app.open_pdf_editor)
        elif "--vault" in sys.argv:
            QTimer.singleShot(100, app.open_secure_vault)
        elif "--history" in sys.argv or "--share-history" in sys.argv:
            QTimer.singleShot(100, app.open_share_history)
        elif "--measure" in sys.argv or "--measurement" in sys.argv:
            QTimer.singleShot(100, app.open_measurement_studio)
        elif "--favorites" in sys.argv or "--fav" in sys.argv:
            QTimer.singleShot(100, app.open_favorites)
        elif "--window" in sys.argv or "--smart-window" in sys.argv:
            QTimer.singleShot(100, app.trigger_smart_window_capture)

        exit_code = app.run()
        sys.exit(exit_code)
    except Exception as exc:
        logger.critical("Fatal error starting Quickglint: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
