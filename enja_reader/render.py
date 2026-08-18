"""Emit a self-contained HTML viewer with a JA-ratio knob.

All sentence pairs are embedded as JSON; the knob only changes which
language each sentence displays, so no LLM call happens at view time.
Selection is by per-sentence hash threshold: raising the knob only adds
Japanese sentences (monotone, stable).
"""

from __future__ import annotations

import hashlib
import html
import json


def sentence_hash(sentence: str) -> float:
    """Deterministic value in [0,1) controlling when a sentence flips to JA."""
    digest = hashlib.sha1(sentence.encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #ffffff; --fg: #1a1a1a; --muted: #667085;
    --ja-bg: #f0f6ff; --manual-outline: #f4b400;
    --accent: #2563eb; --code-bg: #f6f8fa; --border: #e4e7ec;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #111418; --fg: #e6e6e6; --muted: #98a2b3;
      --ja-bg: #16243a; --accent: #60a5fa;
      --code-bg: #1b1f24; --border: #2a2f36;
    }
  }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: "Segoe UI", "Hiragino Sans", "Yu Gothic UI", "Noto Sans JP", sans-serif;
    line-height: 1.85;
  }
  main { max-width: 46rem; margin: 0 auto; padding: 5.5rem 1.5rem 4rem; }
  #bar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 10;
    display: flex; align-items: center; gap: .8rem; flex-wrap: wrap;
    padding: .6rem 1.2rem; background: var(--bg);
    border-bottom: 1px solid var(--border); font-size: .85rem;
  }
  #bar label { color: var(--muted); white-space: nowrap; }
  #ratio { width: min(16rem, 40vw); accent-color: var(--accent); }
  #pct { min-width: 3.5em; font-variant-numeric: tabular-nums; }
  #reset { border: 1px solid var(--border); background: none; color: var(--muted);
           border-radius: 6px; padding: .15rem .6rem; cursor: pointer; }
  #reset:hover { color: var(--fg); }
  .s { cursor: pointer; border-radius: 3px; padding: 0 1px; }
  .s.ja { background: var(--ja-bg); }
  .s.manual { box-shadow: 0 0 0 1px var(--manual-outline); }
  .s:hover { outline: 2px solid var(--accent); outline-offset: 1px; }
  pre { background: var(--code-bg); border: 1px solid var(--border);
        border-radius: 8px; padding: .9rem 1rem; overflow-x: auto;
        font-size: .85rem; line-height: 1.5; }
  blockquote { border-left: 3px solid var(--border); margin: 0 0 0 .2rem;
               padding-left: 1rem; color: var(--muted); }
  h1,h2,h3,h4,h5,h6 { line-height: 1.4; }
  #tip {
    position: fixed; z-index: 20; max-width: 30rem; display: none;
    background: var(--fg); color: var(--bg); font-size: .82rem; line-height: 1.6;
    padding: .5rem .7rem; border-radius: 8px; pointer-events: none;
  }
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
const blocks = JSON.parse(document.getElementById("data").textContent);
const docEl = document.getElementById("doc");
const slider = document.getElementById("ratio");
const pct = document.getElementById("pct");
const tip = document.getElementById("tip");
const manual = new Map();   // sentence element -> forced lang ("en"|"ja")
let spans = [];

function makeSentence(s) {
  const el = document.createElement("span");
  el.className = "s";
  el.dataset.en = s.en;
  el.dataset.ja = s.ja;
  el.dataset.h = s.h;
  spans.push(el);
  return el;
}

for (const b of blocks) {
  let container;
  if (b.kind === "code") {
    container = document.createElement("pre");
    container.textContent = b.text;
    docEl.appendChild(container);
    continue;
  }
  if (b.kind === "heading") {
    container = document.createElement("h" + Math.min(b.level || 1, 6));
  } else if (b.kind === "list_item") {
    container = document.createElement("li");
    let ul = docEl.lastElementChild;
    if (!ul || ul.tagName !== "UL") { ul = document.createElement("ul"); docEl.appendChild(ul); }
    b._parent = ul;
  } else if (b.kind === "quote") {
    container = document.createElement("blockquote");
  } else {
    container = document.createElement("p");
  }
  b.sentences.forEach((s, i) => {
    if (i > 0) container.appendChild(document.createTextNode(" "));
    container.appendChild(makeSentence(s));
  });
  (b._parent || docEl).appendChild(container);
}

function langFor(el, ratio) {
  if (manual.has(el)) return manual.get(el);
  return parseFloat(el.dataset.h) < ratio ? "ja" : "en";
}

function apply() {
  const ratio = slider.value / 100;
  pct.textContent = slider.value + "%";
  for (const el of spans) {
    const lang = langFor(el, ratio);
    el.textContent = el.dataset[lang];
    el.classList.toggle("ja", lang === "ja");
    el.classList.toggle("manual", manual.has(el));
    el.setAttribute("lang", lang);
  }
}

docEl.addEventListener("click", e => {
  const el = e.target.closest(".s");
  if (!el) return;
  const current = langFor(el, slider.value / 100);
  manual.set(el, current === "ja" ? "en" : "ja");
  apply();
  showTip(el);
});

function showTip(el) {
  const lang = el.getAttribute("lang");
  tip.textContent = el.dataset[lang === "ja" ? "en" : "ja"];
  tip.style.display = "block";
  const r = el.getBoundingClientRect();
  tip.style.left = Math.min(r.left, innerWidth - tip.offsetWidth - 16) + "px";
  tip.style.top = (r.bottom + 8) + "px";
}
docEl.addEventListener("mouseover", e => {
  const el = e.target.closest(".s");
  if (el) showTip(el);
});
docEl.addEventListener("mouseout", () => { tip.style.display = "none"; });

document.getElementById("reset").addEventListener("click", () => { manual.clear(); apply(); });
slider.addEventListener("input", apply);
apply();
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
        .replace("__DATA__", data)
    )
