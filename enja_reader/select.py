"""Sentence selection strategies.

Each sentence occurrence gets a threshold h in [0,1); the viewer shows
it in Japanese when h < ratio. Raising the knob only adds Japanese
sentences (monotone) under both strategies.

- "hash": stable pseudo-random spread over the document.
- "difficulty": hardest sentences flip to Japanese first, so at a given
  ratio the reader faces only the easier English sentences.
"""

from __future__ import annotations

import hashlib
import re

_WORD_RE = re.compile(r"[A-Za-z']+")


def sentence_hash(sentence: str) -> float:
    digest = hashlib.sha1(sentence.encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


def difficulty_score(sentence: str) -> float:
    """Crude difficulty heuristic: longer words and longer sentences are harder."""
    words = _WORD_RE.findall(sentence)
    if not words:
        return 0.0
    avg_len = sum(len(w) for w in words) / len(words)
    long_ratio = sum(1 for w in words if len(w) >= 8) / len(words)
    return avg_len + 4.0 * long_ratio + 0.05 * len(words)


def assign_thresholds(sentences: list[str], strategy: str) -> list[float]:
    if strategy == "hash":
        return [sentence_hash(s) for s in sentences]
    if strategy == "difficulty":
        n = len(sentences)
        order = sorted(range(n), key=lambda i: difficulty_score(sentences[i]), reverse=True)
        h = [0.0] * n
        for rank, i in enumerate(order):
            h[i] = (rank + 0.5) / n
        return h
    raise ValueError(f"unknown strategy: {strategy}")
