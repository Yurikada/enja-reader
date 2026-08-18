"""CLI: build a blended EN/JA HTML from a local document.

Usage:
    python -m enja_reader build INPUT [-o OUT.html] [--model gemma2]
                                      [--ratio 30] [--select hash|difficulty]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .parse import parse_document
from .render import render_html
from .segment import split_sentences
from .select import assign_thresholds
from .translate import TranslationCache, check_server, translate_sentence

TRANSLATABLE = {"heading", "paragraph", "list_item", "quote"}


def cmd_build(args: argparse.Namespace) -> int:
    src = Path(args.input)
    fmt = "html" if src.suffix.lower() in {".html", ".htm"} else "markdown"
    text = src.read_text(encoding="utf-8", errors="replace")
    blocks = parse_document(text, fmt=fmt)

    err = check_server(args.model)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    cache = TranslationCache(Path(args.cache))

    for b in blocks:
        if b.kind in TRANSLATABLE:
            b.sentences = split_sentences(b.text)

    all_sentences = [s for b in blocks if b.kind in TRANSLATABLE for s in b.sentences]
    thresholds = assign_thresholds(all_sentences, args.select)
    total = len(all_sentences)
    print(f"{src.name}: {len(blocks)} blocks, {total} sentences ({fmt}, select={args.select})")

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
            pairs.append({"en": sent, "ja": ja, "h": round(thresholds[done], 6)})
            done += 1
            if done % 10 == 0 or done == total:
                rate = done / max(time.time() - t0, 1e-9)
                print(f"  translated {done}/{total} ({rate:.1f} sent/s)", flush=True)
        out_blocks.append(
            {"kind": b.kind, "level": b.level, "ordered": b.ordered, "sentences": pairs}
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
    b.add_argument("input", help="input .md / .txt / .html file")
    b.add_argument("-o", "--output", help="output HTML path")
    b.add_argument("--model", default="gemma2", help="Ollama model name")
    b.add_argument("--ratio", type=int, default=30, help="initial JA ratio (0-100)")
    b.add_argument(
        "--select",
        choices=["hash", "difficulty"],
        default="hash",
        help="which sentences flip to JA first (hash=stable random, difficulty=hardest first)",
    )
    b.add_argument("--cache", default=".cache/translations.sqlite")
    b.set_defaults(func=cmd_build)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
