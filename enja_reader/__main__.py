"""CLI: build a blended EN/JA HTML from a local document.

Usage:
    python -m enja_reader build INPUT [-o OUT.html] [--model gemma2] [--ratio 30]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .parse import parse_document
from .render import render_html, sentence_hash
from .segment import split_sentences
from .translate import TranslationCache, check_server, translate_sentence

TRANSLATABLE = {"heading", "paragraph", "list_item", "quote"}


def cmd_build(args: argparse.Namespace) -> int:
    src = Path(args.input)
    text = src.read_text(encoding="utf-8")
    blocks = parse_document(text)

    err = check_server(args.model)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    cache = TranslationCache(Path(args.cache))

    # segment
    for b in blocks:
        if b.kind in TRANSLATABLE:
            b.sentences = split_sentences(b.text)

    todo = [(b, i) for b in blocks if b.kind in TRANSLATABLE for i in range(len(b.sentences))]
    print(f"{src.name}: {len(blocks)} blocks, {len(todo)} sentences")

    out_blocks: list[dict] = []
    done = 0
    t0 = time.time()
    for b in blocks:
        if b.kind not in TRANSLATABLE:
            out_blocks.append({"kind": b.kind, "text": b.text})
            continue
        pairs = []
        for i, sent in enumerate(b.sentences):
            before = b.sentences[i - 1] if i > 0 else ""
            after = b.sentences[i + 1] if i + 1 < len(b.sentences) else ""
            ja = translate_sentence(args.model, sent, before, after, cache)
            pairs.append({"en": sent, "ja": ja, "h": round(sentence_hash(sent), 6)})
            done += 1
            if done % 10 == 0 or done == len(todo):
                rate = done / max(time.time() - t0, 1e-9)
                print(f"  translated {done}/{len(todo)} ({rate:.1f} sent/s)", flush=True)
        out_blocks.append(
            {"kind": b.kind, "level": b.level, "sentences": pairs}
        )

    out = Path(args.output) if args.output else src.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_html(out_blocks, title=src.stem, initial_ratio=args.ratio),
        encoding="utf-8",
    )
    print(f"wrote {out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="enja_reader")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build blended HTML from a document")
    b.add_argument("input", help="input .md / .txt file")
    b.add_argument("-o", "--output", help="output HTML path")
    b.add_argument("--model", default="gemma2", help="Ollama model name")
    b.add_argument("--ratio", type=int, default=30, help="initial JA ratio (0-100)")
    b.add_argument("--cache", default=".cache/translations.sqlite")
    b.set_defaults(func=cmd_build)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
