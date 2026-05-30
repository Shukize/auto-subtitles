"""Small UI helpers."""
from __future__ import annotations


def format_timestamp(seconds: float) -> str:
    """seconds -> 'HH:MM:SS.mmm'."""
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_timestamp(text: str) -> float:
    """'HH:MM:SS.mmm' (or 'MM:SS.mmm' / 'SS.mmm') -> seconds. Raises ValueError."""
    text = text.strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    elif len(parts) == 1:
        h, m, s = "0", "0", parts[0]
    else:
        raise ValueError(f"Bad timestamp: {text!r}")
    return int(h) * 3600 + int(m) * 60 + float(s)
