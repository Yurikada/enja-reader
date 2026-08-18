"""English sentence segmentation via pysbd, with a regex fallback."""

from __future__ import annotations

import re

try:
    import pysbd

    _SEG = pysbd.Segmenter(language="en", clean=False)

    def split_sentences(text: str) -> list[str]:
        return [s.strip() for s in _SEG.segment(text) if s.strip()]

except ImportError:  # pragma: no cover
    _SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")

    def split_sentences(text: str) -> list[str]:
        return [s.strip() for s in _SENT_RE.split(text) if s.strip()]
