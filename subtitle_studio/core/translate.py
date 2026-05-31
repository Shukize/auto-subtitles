"""Subtitle translation to any language (pluggable backend).

Default backend is Google Translate via ``deep-translator`` (free, online, broad
language coverage). The translator batches lines and preserves cue timing.
"""
from __future__ import annotations

import time
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

    # Default to originals so any failure automatically keeps source text.
    out: List[str] = list(lines)
    # Indices of non-empty lines we actually need to translate.
    todo = [i for i, t in enumerate(lines) if t and t.strip()]

    # Reduced batch size to avoid hitting Google's per-request character limit
    # and rate-limiting for long videos (100+ cues / 4-8 requests in a row).
    BATCH = 20
    done = 0
    for start in range(0, len(todo), BATCH):
        if cancelled and cancelled():
            raise RuntimeError("Cancelled")
        idx_chunk = todo[start:start + BATCH]
        texts = [lines[i] for i in idx_chunk]

        # Small delay between batches to avoid rate-limiting (Google blocks
        # rapid consecutive requests, especially for less-common target langs).
        if start > 0:
            time.sleep(0.4)

        try:
            results = translator.translate_batch(texts)
            # translate_batch can return None or a shorter list on partial failure.
            if not isinstance(results, list) or len(results) != len(texts):
                raise ValueError("unexpected batch result shape")
            for i, res in zip(idx_chunk, results):
                if res and str(res).strip():
                    out[i] = str(res)
        except Exception:
            # Batch failed — retry line by line with small inter-request delay.
            for j, (idx, t) in enumerate(zip(idx_chunk, texts)):
                if cancelled and cancelled():
                    raise RuntimeError("Cancelled")
                if j > 0:
                    time.sleep(0.15)
                try:
                    res = translator.translate(t)
                    if res and str(res).strip():
                        out[idx] = str(res)
                except Exception:
                    pass  # keep original (already set above)

        done += len(idx_chunk)
        if progress and todo:
            progress(min(1.0, done / len(todo)))

    if progress:
        progress(1.0)
    return out
