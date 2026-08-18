"""Sentence translation through a local Ollama server, with SQLite cache."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"

SYSTEM_PROMPT = (
    "You are a professional English-to-Japanese translator. "
    "Translate the target sentence into natural, fluent Japanese. "
    "Use the surrounding context only to resolve pronouns and terminology. "
    "Strictly write in plain form (だ・である調). Never use です・ます form. "
    "Output ONLY the Japanese translation — no explanations, no romaji, "
    "no quotation marks around the output.\n\n"
    "Examples of the required style:\n"
    "The system is fast. → このシステムは速い。\n"
    "This is how training wheels work. → これが補助輪の仕組みである。\n"
    "It must be a knob, not a constant. → それは定数ではなくノブでなければならない。\n"
    "You can adjust the ratio at any time. → 比率はいつでも調整できる。"
)

HEADING_HINT = (
    "The target is a section heading: translate it as a concise noun phrase "
    "(体言止め), with no trailing particle and no final period."
)


class TranslationCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS translations ("
            " key TEXT PRIMARY KEY, model TEXT, en TEXT, ja TEXT)"
        )

    @staticmethod
    def key(model: str, sentence: str, before: str, after: str) -> str:
        return hashlib.sha256(
            f"{model}\x00{SYSTEM_PROMPT}\x00{before}\x00{after}\x00{sentence}".encode()
        ).hexdigest()

    def get(self, model: str, sentence: str, before: str, after: str) -> str | None:
        row = self.conn.execute(
            "SELECT ja FROM translations WHERE key=?",
            (self.key(model, sentence, before, after),),
        ).fetchone()
        return row[0] if row else None

    def put(self, model: str, sentence: str, before: str, after: str, ja: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO translations VALUES (?,?,?,?)",
            (self.key(model, sentence, before, after), model, sentence, ja),
        )
        self.conn.commit()


def _chat(model: str, prompt: str, timeout: float = 120.0) -> str:
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"].strip()


def translate_sentence(
    model: str,
    sentence: str,
    context_before: str = "",
    context_after: str = "",
    cache: TranslationCache | None = None,
    kind: str = "",
) -> str:
    # the hint changes the expected output, so it participates in the cache key
    hint = HEADING_HINT if kind == "heading" else ""
    if cache:
        hit = cache.get(model, sentence, context_before, context_after + hint)
        if hit is not None:
            return hit

    parts = []
    if hint:
        parts.append(hint)
    if context_before:
        parts.append(f"Context (before): {context_before}")
    if context_after:
        parts.append(f"Context (after): {context_after}")
    parts.append(f"Target sentence: {sentence}")
    ja = _strip_wrapping_quotes(_chat(model, "\n".join(parts)))

    if cache:
        cache.put(model, sentence, context_before, context_after + hint, ja)
    return ja


_QUOTE_PAIRS = [('"', '"'), ("「", "」"), ("『", "』"), ("“", "”")]


def _strip_wrapping_quotes(text: str) -> str:
    """Remove quotes only when they wrap the whole output as a matched pair."""
    text = text.strip()
    changed = True
    while changed and len(text) >= 2:
        changed = False
        for opening, closing in _QUOTE_PAIRS:
            if text.startswith(opening) and text.endswith(closing):
                inner = text[len(opening):-len(closing)]
                # keep quotes that belong to the sentence itself,
                # e.g. 「こんにちは」と彼は言った。
                if closing in inner:
                    continue
                text = inner.strip()
                changed = True
                break
    return text


def check_server(model: str) -> str | None:
    """Return an error message if Ollama or the model is unavailable, else None."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            tags = json.loads(r.read())
    except (urllib.error.URLError, OSError):
        return "Ollama server is not reachable at localhost:11434. Start it with `ollama serve`."
    names = {m["name"] for m in tags.get("models", [])}
    if model not in names and f"{model}:latest" not in names:
        return f"Model '{model}' not found in Ollama. Available: {', '.join(sorted(names))}"
    return None
