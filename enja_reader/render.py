"""Emit a self-contained HTML viewer with a JA-ratio knob.

All sentence pairs are embedded as JSON; the knob only changes which
language each sentence displays, so no LLM call happens at view time.
The viewer CSS/JS live in assets/ and are inlined here, so the same
sources can be reused unchanged by the Chrome extension later.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

_ASSETS = Path(__file__).parent / "assets"

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
__CSS__
</style>
</head>
<body>
<div id="bar">
  <label>日本語比率</label>
  <input id="ratio" type="range" min="0" max="100" value="__RATIO__">
  <span id="pct"></span>
  <button id="reset" title="クリックで個別切替した文を元に戻す">個別切替をリセット</button>
  <span style="color:var(--muted)">文クリック=言語切替 / ホバー=対訳表示</span>
</div>
<main id="doc"></main>
<div id="tip"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
__JS__
</script>
</body>
</html>
"""


def render_html(blocks: list[dict], title: str, initial_ratio: int = 30) -> str:
    data = json.dumps(blocks, ensure_ascii=False)
    # keep embedded JSON safe inside <script>
    data = data.replace("</", "<\\/")
    return (
        _TEMPLATE.replace("__TITLE__", html.escape(title))
        .replace("__RATIO__", str(initial_ratio))
        .replace("__CSS__", (_ASSETS / "viewer.css").read_text(encoding="utf-8"))
        .replace("__JS__", (_ASSETS / "viewer.js").read_text(encoding="utf-8"))
        .replace("__DATA__", data)
    )
