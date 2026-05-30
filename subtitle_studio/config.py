"""Application configuration and persistent settings."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path


def app_data_dir() -> Path:
    """Per-user writable directory for settings, logs and model cache."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / "SubtitleStudio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_cache_dir() -> Path:
    d = app_data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


# Whisper model sizes, smallest/fastest -> largest/most accurate.
WHISPER_MODELS = [
    "tiny",
    "base",
    "small",
    "medium",
    "large-v3",
]

DEFAULT_MODEL = "large-v3"  # most accurate; RTX-class GPU handles it comfortably

SETTINGS_FILE = app_data_dir() / "settings.json"


@dataclass
class SubtitleStyle:
    """Appearance of burned-in subtitles (maps to libass / ASS styling)."""
    font_name: str = "Arial"
    font_size: int = 28
    primary_color: str = "#FFFFFF"   # text fill
    outline_color: str = "#000000"   # border
    back_color: str = "#000000"      # shadow / box
    bold: bool = True
    italic: bool = False
    outline: float = 2.0             # border thickness
    shadow: float = 0.5
    # 1-9 numpad layout (2 = bottom-center, 5 = middle, 8 = top-center)
    alignment: int = 2
    margin_v: int = 30               # vertical margin from edge (px)
    margin_l: int = 40
    margin_r: int = 40


@dataclass
class Settings:
    model: str = DEFAULT_MODEL
    device: str = "auto"             # auto | cuda | cpu
    compute_type: str = "auto"       # auto | float16 | int8_float16 | int8
    source_language: str = "auto"    # auto-detect by default
    translate_to: str = ""           # empty = no translation
    max_chars_per_line: int = 42
    max_lines: int = 2
    style: SubtitleStyle = field(default_factory=SubtitleStyle)

    @classmethod
    def load(cls) -> "Settings":
        if SETTINGS_FILE.exists():
            try:
                raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                style = SubtitleStyle(**raw.pop("style", {}))
                return cls(style=style, **raw)
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        data = asdict(self)
        try:
            SETTINGS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass
