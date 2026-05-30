"""Subtitle document model: build, edit, style, import and export.

Wraps ``pysubs2`` so we can round-trip SRT / VTT / ASS and apply rich styling
(used for hard burn-in via ASS).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pysubs2

from subtitle_studio.config import SubtitleStyle
from subtitle_studio.core.transcribe import Cue, TranscriptionResult


@dataclass
class SubtitleLine:
    """An editable subtitle entry. Times are in seconds."""
    start: float
    end: float
    text: str

    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class SubtitleDocument:
    lines: List[SubtitleLine] = field(default_factory=list)
    language: str = "unknown"

    # ---- construction -------------------------------------------------
    @classmethod
    def from_result(cls, result: TranscriptionResult) -> "SubtitleDocument":
        lines = [SubtitleLine(c.start, c.end, c.text) for c in result.cues]
        return cls(lines=lines, language=result.language)

    @classmethod
    def load(cls, path: str | Path) -> "SubtitleDocument":
        subs = pysubs2.load(str(path))
        lines = [
            SubtitleLine(ev.start / 1000.0, ev.end / 1000.0, ev.plaintext)
            for ev in subs
            if not ev.is_comment
        ]
        return cls(lines=lines)

    # ---- editing ------------------------------------------------------
    def texts(self) -> List[str]:
        return [ln.text for ln in self.lines]

    def set_texts(self, texts: List[str]) -> None:
        for ln, t in zip(self.lines, texts):
            ln.text = t

    # ---- export -------------------------------------------------------
    def to_ssafile(self, style: SubtitleStyle | None = None) -> pysubs2.SSAFile:
        subs = pysubs2.SSAFile()
        if style is not None:
            subs.styles["Default"] = _to_ssastyle(style)
        for ln in self.lines:
            subs.append(
                pysubs2.SSAEvent(
                    start=int(round(ln.start * 1000)),
                    end=int(round(ln.end * 1000)),
                    text=ln.text.replace("\n", r"\N"),
                )
            )
        return subs

    def save(self, path: str | Path, style: SubtitleStyle | None = None) -> Path:
        path = Path(path)
        subs = self.to_ssafile(style)
        # pysubs2 picks the format from the extension (.srt/.ass/.vtt).
        subs.save(str(path))
        return path

    def save_styled_ass(self, path: str | Path, style: SubtitleStyle) -> Path:
        """Save an .ass with full styling - used as the burn-in source."""
        path = Path(path)
        subs = self.to_ssafile(style)
        subs.save(str(path), format_="ass")
        return path


def _hex_to_ass_color(hex_color: str, alpha: int = 0) -> pysubs2.Color:
    """Convert ``#RRGGBB`` to a pysubs2 Color (alpha 0 = opaque)."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    else:
        r = g = b = 255
    return pysubs2.Color(r, g, b, alpha)


def _to_ssastyle(style: SubtitleStyle) -> pysubs2.SSAStyle:
    s = pysubs2.SSAStyle()
    s.fontname = style.font_name
    s.fontsize = style.font_size
    s.primarycolor = _hex_to_ass_color(style.primary_color)
    s.outlinecolor = _hex_to_ass_color(style.outline_color)
    s.backcolor = _hex_to_ass_color(style.back_color)
    s.bold = style.bold
    s.italic = style.italic
    s.outline = style.outline
    s.shadow = style.shadow
    s.alignment = pysubs2.Alignment(style.alignment)
    s.marginv = style.margin_v
    s.marginl = style.margin_l
    s.marginr = style.margin_r
    return s
