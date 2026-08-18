"""Model/prompt comparison harness for translation quality.

Translates the sample document's sentences with each (model, prompt)
config, computes automatic metrics, and writes:
  eval/results.json  - raw translations + metrics
  eval/report.html   - side-by-side table with flagged issues

Usage:
    python eval/compare.py [--configs gemma2:base gemma2:fewshot qwen2.5:7b:base ...]

Metrics (per config):
  polite_rate  : fraction of sentences ending in です・ます forms
                 (target style is plain だ・である, so lower is better)
  leftover_en  : fraction with a run of 3+ latin words (untranslated text)
  meta_text    : fraction containing translator meta commentary
  len_outliers : fraction with ja/en char ratio < 0.3 or > 3.0
  sent_per_s   : throughput
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from enja_reader.parse import parse_document  # noqa: E402
from enja_reader.segment import split_sentences  # noqa: E402
from enja_reader.translate import SYSTEM_PROMPT, _chat, _strip_wrapping_quotes  # noqa: E402

BASE_PROMPT = (
    "You are a professional English-to-Japanese translator. "
    "Translate the sentence given by the user into natural, fluent Japanese. "
    "Use the surrounding context only to resolve pronouns and terminology. "
    "Write in plain form (だ・である調), consistently across sentences. "
    "Output ONLY the Japanese translation of the target sentence — "
    "no explanations, no romaji, no quotation marks around the output."
)

FEWSHOT_PROMPT = (
    "You are a professional English-to-Japanese translator. "
    "Translate the target sentence into natural, fluent Japanese. "
    "Use the surrounding context only to resolve pronouns and terminology. "
    "Strictly write in plain form (だ・である調). Never use です・ます form. "
    "Output ONLY the Japanese translation — no explanations, no romaji, "
    "no quotation marks around the output.\n\n"
    "Examples of the required style:\n"
    "The system is fast. → このシステムは速い。\n"
    "This is how training wheels work. → これが補助輪の仕組みである。\n"
    "You can adjust the ratio at any time. → 比率はいつでも調整できる。"
)

# fewshot2 == the shipping prompt in translate.py (adds the "X, not Y" example)
PROMPTS = {"base": BASE_PROMPT, "fewshot": FEWSHOT_PROMPT, "fewshot2": SYSTEM_PROMPT}

_POLITE_RE = re.compile(
    r"(です|ます|ました|ません|でした|でしょう|ましょう|ますか|ですか)(?:[。!?！？」』\s]*)$"
)
_LATIN_RUN_RE = re.compile(r"[A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){2,}")
_META_RE = re.compile(r"(翻訳[:：]|訳[:：]|Translation|以下の|という意味)")
# scripts that should never appear in an EN->JA translation
_FOREIGN_RE = re.compile(r"[Ѐ-ӿ가-힯؀-ۿ฀-๿ऀ-ॿ]")


def is_polite(ja: str) -> bool:
    return bool(_POLITE_RE.search(ja.strip()))


def collect_sentences(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    fmt = "html" if path.suffix.lower() in {".html", ".htm"} else "markdown"
    blocks = parse_document(text, fmt=fmt)
    out: list[str] = []
    for b in blocks:
        if b.kind in {"heading", "paragraph", "list_item", "quote"}:
            out.extend(split_sentences(b.text))
    return out


def run_config(model: str, prompt_name: str, sentences: list[str],
               cache_dir: Path) -> dict:
    cache_file = cache_dir / f"{model.replace(':', '_')}__{prompt_name}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("sentences") == sentences:
            return cached

    system = PROMPTS[prompt_name]
    translations: list[str] = []
    t0 = time.time()
    for i, sent in enumerate(sentences):
        before = sentences[i - 1] if i > 0 else ""
        after = sentences[i + 1] if i + 1 < len(sentences) else ""
        parts = []
        if before:
            parts.append(f"Context (before): {before}")
        if after:
            parts.append(f"Context (after): {after}")
        parts.append(f"Target sentence: {sent}")
        ja = _strip_wrapping_quotes(
            _chat_with_system(model, system, "\n".join(parts))
        )
        translations.append(ja)
        print(f"  [{model}/{prompt_name}] {i + 1}/{len(sentences)}", flush=True)
    elapsed = time.time() - t0

    result = {
        "model": model,
        "prompt": prompt_name,
        "sentences": sentences,
        "translations": translations,
        "elapsed_s": round(elapsed, 1),
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    return result


def _chat_with_system(model: str, system: str, prompt: str) -> str:
    import enja_reader.translate as tr

    original = tr.SYSTEM_PROMPT
    tr.SYSTEM_PROMPT = system
    try:
        return _chat(model, prompt)
    finally:
        tr.SYSTEM_PROMPT = original


def metrics(result: dict) -> dict:
    sents = result["sentences"]
    jas = result["translations"]
    n = len(sents)
    polite = [is_polite(j) for j in jas]
    leftover = [bool(_LATIN_RUN_RE.search(j)) for j in jas]
    meta = [bool(_META_RE.search(j)) for j in jas]
    foreign = [bool(_FOREIGN_RE.search(j)) for j in jas]
    ratios = [len(j) / max(len(s), 1) for s, j in zip(sents, jas)]
    outlier = [r < 0.3 or r > 3.0 for r in ratios]
    return {
        "polite_rate": round(sum(polite) / n, 3),
        "leftover_en": round(sum(leftover) / n, 3),
        "meta_text": round(sum(meta) / n, 3),
        "foreign_script": round(sum(foreign) / n, 3),
        "len_outliers": round(sum(outlier) / n, 3),
        "sent_per_s": round(n / result["elapsed_s"], 2) if result["elapsed_s"] else None,
        "flags": [
            {"i": i, "polite": p, "leftover": lo, "meta": m, "foreign": f, "outlier": o}
            for i, (p, lo, m, f, o) in enumerate(zip(polite, leftover, meta, foreign, outlier))
            if p or lo or m or f or o
        ],
    }


def write_report(results: list[dict], all_metrics: list[dict], out: Path) -> None:
    head = "".join(
        f"<th>{html.escape(r['model'])}<br>{r['prompt']}</th>" for r in results
    )
    metric_rows = ""
    for key in ["polite_rate", "leftover_en", "meta_text", "foreign_script",
                "len_outliers", "sent_per_s"]:
        cells = "".join(f"<td>{m[key]}</td>" for m in all_metrics)
        metric_rows += f"<tr><th>{key}</th>{cells}</tr>"

    flagged = {(r["model"], r["prompt"]): {f["i"]: f for f in m["flags"]}
               for r, m in zip(results, all_metrics)}
    body_rows = ""
    for i, en in enumerate(results[0]["sentences"]):
        cells = ""
        for r in results:
            f = flagged[(r["model"], r["prompt"])].get(i)
            cls = ""
            note = ""
            if f:
                issues = [k for k in ("polite", "leftover", "meta", "foreign", "outlier") if f[k]]
                cls = ' class="flag"'
                note = f'<div class="issues">{", ".join(issues)}</div>'
            cells += f"<td{cls}>{html.escape(r['translations'][i])}{note}</td>"
        body_rows += f"<tr><td class='en'>{html.escape(en)}</td>{cells}</tr>"

    out.write_text(f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><title>enja-reader model eval</title>
<style>
body {{ font-family: "Segoe UI", "Yu Gothic UI", sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: .85rem; }}
th, td {{ border: 1px solid #ccc; padding: .4rem .6rem; vertical-align: top; }}
td.en {{ color: #555; width: 22%; }}
td.flag {{ background: #fff3e0; }}
.issues {{ color: #b45309; font-size: .75rem; margin-top: .2rem; }}
</style></head><body>
<h1>Model / prompt comparison</h1>
<table><tr><th>metric</th>{head}</tr>{metric_rows}</table>
<h2>Sentences</h2>
<table><tr><th>EN</th>{head}</tr>{body_rows}</table>
</body></html>""", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=str(ROOT / "samples" / "attention.md"))
    ap.add_argument("--configs", nargs="+",
                    default=["gemma2:base", "gemma2:fewshot",
                             "qwen2.5:7b:base", "qwen2.5:7b:fewshot"])
    args = ap.parse_args()

    sentences = collect_sentences(Path(args.sample))
    print(f"{len(sentences)} sentences from {args.sample}")

    cache_dir = ROOT / "eval" / ".cache"
    results, all_metrics = [], []
    for cfg in args.configs:
        model, _, prompt = cfg.rpartition(":")
        r = run_config(model, prompt, sentences, cache_dir)
        m = metrics(r)
        results.append(r)
        all_metrics.append(m)
        print(f"{model}/{prompt}: polite={m['polite_rate']} leftover={m['leftover_en']} "
              f"meta={m['meta_text']} outliers={m['len_outliers']} speed={m['sent_per_s']}/s")

    (ROOT / "eval" / "results.json").write_text(
        json.dumps([{**r, "metrics": m} for r, m in zip(results, all_metrics)],
                   ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(results, all_metrics, ROOT / "eval" / "report.html")
    print(f"wrote {ROOT / 'eval' / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
