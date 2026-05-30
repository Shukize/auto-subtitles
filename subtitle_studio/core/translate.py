"""Subtitle translation to any language (pluggable backend).

Default backend is Google Translate via ``deep-translator`` (free, online, broad
language coverage). The translator batches lines and preserves cue timing.
"""
from __future__ import annotations

from typing import Callable, List, Optional

# Common targets surfaced in the UI. "auto" source is always allowed.
# deep-translator accepts ISO codes or language names; we keep human labels here.
LANGUAGES = {
    "Arabic": "ar", "Bengali": "bn", "Bulgarian": "bg", "Chinese (Simplified)": "zh-CN",
    "Chinese (Traditional)": "zh-TW", "Croatian": "hr", "Czech": "cs", "Danish": "da",
    "Dutch": "nl", "English": "en", "Estonian": "et", "Filipino": "tl", "Finnish": "fi",
    "French": "fr", "German": "de", "Greek": "el", "Gujarati": "gu", "Hebrew": "iw",
    "Hindi": "hi", "Hungarian": "hu", "Indonesian": "id", "Italian": "it",
    "Japanese": "ja", "Kannada": "kn", "Korean": "ko", "Latvian": "lv",
    "Lithuanian": "lt", "Malay": "ms", "Malayalam": "ml", "Marathi": "mr",
    "Norwegian": "no", "Persian": "fa", "Polish": "pl", "Portuguese": "pt",
    "Punjabi": "pa", "Romanian": "ro", "Russian": "ru", "Serbian": "sr",
    "Slovak": "sk", "Slovenian": "sl", "Spanish": "es", "Swahili": "sw",
    "Swedish": "sv", "Tamil": "ta", "Telugu": "te", "Thai": "th", "Turkish": "tr",
    "Ukrainian": "uk", "Urdu": "ur", "Vietnamese": "vi",
}


def language_code(name_or_code: str) -> str:
    """Accept either a display name ('Spanish') or a code ('es')."""
    if name_or_code in LANGUAGES:
        return LANGUAGES[name_or_code]
    return name_or_code


def translate_lines(
    lines: List[str],
    target: str,
    source: str = "auto",
    progress: Optional[Callable[[float], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """Translate a list of subtitle texts, preserving order and count.

    Lines are sent in batches to limit network round-trips. Empty lines pass
    through untouched. On a per-batch failure the original text is kept so the
    job never aborts mid-way.
    """
    from deep_translator import GoogleTranslator

    target = language_code(target)
    src = "auto" if source in ("auto", "", None) else language_code(source)
    translator = GoogleTranslator(source=src, target=target)

    out: List[str] = [""] * len(lines)
    # Indices of non-empty lines we actually need to translate.
    todo = [i for i, t in enumerate(lines) if t and t.strip()]

    # deep-translator's batch endpoint handles lists; chunk to stay within limits.
    BATCH = 25
    done = 0
    for start in range(0, len(todo), BATCH):
        if cancelled and cancelled():
            raise RuntimeError("Cancelled")
        idx_chunk = todo[start:start + BATCH]
        texts = [lines[i] for i in idx_chunk]
        try:
            results = translator.translate_batch(texts)
        except Exception:
            # Fall back to per-line; keep original on failure.
            results = []
            for t in texts:
                try:
                    results.append(translator.translate(t))
                except Exception:
                    results.append(t)
        for i, res in zip(idx_chunk, results):
            out[i] = res if res else lines[i]
        done += len(idx_chunk)
        if progress and todo:
            progress(min(1.0, done / len(todo)))

    if progress:
        progress(1.0)
    return out
