"""ffmpeg-backed media operations: probe, audio extraction, subtitle burn-in.

Uses the ffmpeg binary bundled by ``imageio-ffmpeg`` so the packaged .exe needs
no external dependencies.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

import imageio_ffmpeg

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v",
    ".mpg", ".mpeg", ".ts", ".m2ts", ".3gp", ".ogv",
}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def is_media_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in MEDIA_EXTENSIONS


def is_video_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def ffmpeg_exe() -> str:
    """Absolute path to the bundled ffmpeg executable."""
    return imageio_ffmpeg.get_ffmpeg_exe()


def _no_window_kwargs() -> dict:
    """Prevent console windows from flashing when frozen on Windows."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def probe_duration(media_path: str | Path) -> float:
    """Return media duration in seconds (0.0 if it cannot be determined)."""
    cmd = [ffmpeg_exe(), "-i", str(media_path), "-hide_banner"]
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, **_no_window_kwargs(),
    )
    # ffmpeg prints duration to stderr: "Duration: 00:01:23.45,"
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if m:
        h, mnt, s = m.groups()
        return int(h) * 3600 + int(mnt) * 60 + float(s)
    return 0.0


def extract_audio(
    media_path: str | Path,
    out_wav: str | Path,
    progress: Optional[Callable[[float], None]] = None,
    duration: Optional[float] = None,
) -> Path:
    """Extract a 16 kHz mono PCM WAV (what Whisper expects).

    ``progress`` is called with a 0..1 fraction when ``duration`` is known.
    """
    out_wav = Path(out_wav)
    cmd = [
        ffmpeg_exe(), "-y",
        "-i", str(media_path),
        "-vn",                    # drop video
        "-ac", "1",               # mono
        "-ar", "16000",           # 16 kHz
        "-c:a", "pcm_s16le",
        "-f", "wav",
        str(out_wav),
    ]
    _run_with_progress(cmd, duration, progress)
    if not out_wav.exists() or out_wav.stat().st_size == 0:
        raise RuntimeError("Audio extraction failed (no output produced).")
    return out_wav


def burn_subtitles(
    video_path: str | Path,
    subtitle_path: str | Path,
    out_path: str | Path,
    progress: Optional[Callable[[float], None]] = None,
    duration: Optional[float] = None,
) -> Path:
    """Hard-burn an .ass/.srt subtitle file into a video, re-encoding video only.

    Styling is taken from the subtitle file itself (we write styled ASS).
    """
    video_path = Path(video_path)
    subtitle_path = Path(subtitle_path)
    out_path = Path(out_path)

    # The subtitles filter needs a path with escaped special chars (esp. on Windows
    # where the drive colon must be escaped for the filtergraph parser).
    sub_arg = _escape_filter_path(subtitle_path)

    cmd = [
        ffmpeg_exe(), "-y",
        "-i", str(video_path),
        "-vf", f"subtitles={sub_arg}",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        str(out_path),
    ]
    _run_with_progress(cmd, duration, progress)
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("Subtitle burn-in failed (no output produced).")
    return out_path


def _escape_filter_path(path: Path) -> str:
    r"""Escape a filesystem path for use inside an ffmpeg filtergraph value.

    On Windows ``C:\dir\file.ass`` must become ``C\:/dir/file.ass`` and be quoted.
    """
    p = str(path).replace("\\", "/")
    p = p.replace(":", r"\:")
    return f"'{p}'"


def _run_with_progress(
    cmd: list[str],
    duration: Optional[float],
    progress: Optional[Callable[[float], None]],
) -> None:
    """Run ffmpeg, parsing ``-progress`` style time output for a 0..1 fraction."""
    # Insert machine-readable progress reporting to stdout.
    full = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    proc = subprocess.Popen(
        full, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, **_no_window_kwargs(),
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if progress and duration and line.startswith("out_time_ms="):
            try:
                us = int(line.split("=", 1)[1])
                frac = max(0.0, min(1.0, (us / 1_000_000) / duration))
                progress(frac)
            except (ValueError, ZeroDivisionError):
                pass
    proc.wait()
    if proc.returncode != 0:
        err = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"ffmpeg failed (code {proc.returncode}):\n{err[-2000:]}")
    if progress:
        progress(1.0)
