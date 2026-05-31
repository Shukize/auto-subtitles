"""Background worker thread so the UI stays responsive during long jobs."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    """Runs ``job(progress, is_cancelled)`` off the UI thread.

    ``job`` receives:
      * ``progress(fraction: float, message: str)`` - report 0..1 progress.
      * ``is_cancelled() -> bool`` - poll for cooperative cancellation.

    Whatever ``job`` returns is delivered via the ``done`` signal.
    """

    progress = Signal(float, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, job: Callable[[Callable[[float, str], None], Callable[[], bool]], Any]):
        super().__init__()
        self._job = job
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def _is_cancelled(self) -> bool:
        return self._cancel

    def _emit_progress(self, fraction: float, message: str = "") -> None:
        self.progress.emit(float(fraction), message)

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            result = self._job(self._emit_progress, self._is_cancelled)
            if not self._cancel:
                self.done.emit(result)
        except BaseException as exc:  # BaseException catches MemoryError and native errors
            if not self._cancel:
                self.failed.emit(str(exc) or type(exc).__name__)
