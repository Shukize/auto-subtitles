# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Subtitle Studio (onedir, windowed).

Bundles ffmpeg, the faster-whisper VAD assets, and the CUDA DLLs (preserving the
``nvidia/<pkg>/bin`` layout that subtitle_studio.core.cuda_setup expects).

Build:  pyinstaller SubtitleStudio.spec --noconfirm
Output: dist/SubtitleStudio/SubtitleStudio.exe
"""
import glob
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

block_cipher = None

binaries = []
datas = []
hiddenimports = []

# --- packages that ship their own DLLs / data --------------------------------
for pkg in ("ctranslate2", "av", "onnxruntime"):
    b, d, h = collect_all(pkg)
    binaries += b
    datas += d
    hiddenimports += h

# faster-whisper bundles the Silero VAD model under faster_whisper/assets
datas += collect_data_files("faster_whisper")
hiddenimports += ["faster_whisper"]

# imageio-ffmpeg bundles the ffmpeg executable under its binaries/ dir
datas += collect_data_files("imageio_ffmpeg")

# deep-translator / pysubs2 are pure python but include them explicitly
hiddenimports += ["deep_translator", "pysubs2"]

# --- NVIDIA CUDA DLLs: replicate site-packages/nvidia/<pkg>/bin --------------
# Located by walking sys.path so this works from any venv.
import site
import sys

def _find_nvidia_root():
    roots = []
    for p in sys.path + (site.getsitepackages() if hasattr(site, "getsitepackages") else []):
        cand = os.path.join(p, "nvidia")
        if os.path.isdir(cand):
            roots.append(cand)
    return roots

for nvidia_root in _find_nvidia_root():
    for dll in glob.glob(os.path.join(nvidia_root, "**", "*.dll"), recursive=True):
        rel = os.path.relpath(os.path.dirname(dll), os.path.dirname(nvidia_root))
        binaries.append((dll, rel))   # e.g. dest "nvidia/cublas/bin"

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SubtitleStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                 # windowed GUI app
    disable_windowed_traceback=False,
    icon="assets/app.ico" if os.path.exists("assets/app.ico") else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SubtitleStudio",
)
