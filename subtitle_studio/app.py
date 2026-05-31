"""Application bootstrap."""
from __future__ import annotations

import sys


def _preinit_native_libs() -> None:
    """Load CTranslate2's CUDA stack *before* Qt is imported.

    On Windows, Qt's bundled DLLs shadow native libraries that CTranslate2's
    CUDA backend depends on. If Qt loads first, later constructing a CUDA
    Whisper model hard-crashes the whole process with an access violation
    (observed as a crash at ~10%, right after "Loading model…") — and because
    it's a native crash, no Python ``try/except`` can catch it.

    Importing ``ctranslate2`` first pins the correct DLLs, after which Qt and
    GPU inference coexist happily. Best-effort and harmless on CPU-only
    machines (the package simply isn't imported for its CUDA side effects).
    """
    try:
        from subtitle_studio.core import cuda_setup
        cuda_setup.register_cuda_dlls()
        import ctranslate2  # noqa: F401 -- imported for its DLL-loading side effects
    except Exception:
        # No GPU stack / import failure -> CPU path still works fine.
        pass


# Must run at import time, before anything pulls in PySide6.
_preinit_native_libs()


def main() -> int:
    # Imported here (not at module top) so _preinit_native_libs() runs first.
    from PySide6.QtWidgets import QApplication

    from subtitle_studio import APP_NAME
    from subtitle_studio.ui.main_window import MainWindow

    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("SubtitleStudio")
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
