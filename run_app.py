"""Launcher entry point (used for dev runs and as the PyInstaller target)."""
import multiprocessing

from subtitle_studio.app import main

if __name__ == "__main__":
    # Required so PyInstaller-frozen child processes don't re-launch the GUI.
    multiprocessing.freeze_support()
    raise SystemExit(main())
