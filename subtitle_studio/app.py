"""Application bootstrap."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from subtitle_studio import APP_NAME
from subtitle_studio.ui.main_window import MainWindow


def main() -> int:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("SubtitleStudio")
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
