"""Make the pip-installed NVIDIA CUDA DLLs discoverable at runtime.

The ``nvidia-cublas-cu12`` / ``nvidia-cudnn-cu12`` wheels drop their DLLs under
``site-packages/nvidia/<pkg>/bin`` which is *not* on the default DLL search path,
so CTranslate2 fails to load ``cublas64_12.dll`` / ``cudnn64_9.dll`` unless we
register those directories first. Must run before any CUDA inference happens.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_done = False


def register_cuda_dlls() -> bool:
    """Add bundled NVIDIA DLL directories to the search path. Idempotent.

    Returns True if at least one CUDA bin directory was found and registered.
    """
    global _done
    if _done:
        return True
    found = False

    candidate_roots = []
    # 1) site-packages/nvidia (dev / normal install)
    for entry in sys.path:
        if entry and os.path.isdir(os.path.join(entry, "nvidia")):
            candidate_roots.append(Path(entry) / "nvidia")
    # 2) PyInstaller bundle: DLLs collected next to the executable.
    if getattr(sys, "frozen", False):
        candidate_roots.append(Path(sys._MEIPASS) / "nvidia")  # type: ignore[attr-defined]

    for root in candidate_roots:
        if not root.is_dir():
            continue
        for bindir in root.glob("*/bin"):
            try:
                os.add_dll_directory(str(bindir))
                # Also prepend to PATH for libraries that resolve via PATH.
                os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")
                found = True
            except OSError:
                pass

    _done = found
    return found
