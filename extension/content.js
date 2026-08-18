// enja-reader content script: sentence-level bilingual blending on any page.
// Direction is auto-detected (EN page -> mix in JA, JA page -> mix in EN)
// and can be flipped from the in-page bar. Injected on demand; running it
// again while active deactivates.
(async () => {
  if (window.__enjaReader) {
    window.__enjaReader.deactivate();
    return;
  }

  const api = { deactivate: () => { alive = false; } };
  window.__enjaReader = api;
  let alive = true; // the whole session (until deactivate)

  const settings = Object.assign(
    { backend: "auto", select: "hash", ratio: 30, model: "gemma2", direction: "auto" },
    await chrome.storage.sync.get(["backend", "select", "ratio", "model", "direction"]),
  );
  if (!alive) return;

  const initialRatio =
    Number.isFinite(+settings.ratio) ? Math.min(Math.max(+settings.ratio, 0), 100) : 30;

  // ---------- language helpers ----------

  let detector = null;
  if ("LanguageDetector" in self) {
    try {
      detector = await LanguageDetector.create();
    } catch {
      detector = null;
    }
  }
  if (!alive) return;

  function latinRatio(text) {
    const letters = text.match(/\p{L}/gu) || [];
    if (!letters.length) return 0;
    return (text.match(/[A-Za-z]/g) || []).length / letters.length;
  }

  async function detectedLang(text) {
    if (detector) {
      try {
        const [top] = await detector.detect(text);
        if (top && top.confidence > 0.5) return top.detectedLanguage;
      } catch {
        /* fall through */
      }
    }
    const r = latinRatio(text);
    if (r >= 0.5) return "en";
    if (/[぀-ヿ㐀-䶿一-鿿]/.test(text)) return "ja";
    return "und";
  }

  const CANDIDATE_SELECTOR = "p, h1, h2, h3, h4, h5, h6, li, blockquote, dd, figcaption";
  const SKIP_CLOSEST = "nav, footer, aside, pre, code, [contenteditable], .enja-s";
  const BLOCK_CHILD = "p, div, ul, ol, table, pre, blockquote, h1, h2, h3, h4, h5, h6";

  async function detectDirection() {
    if (settings.direction === "en-ja" || settings.direction === "ja-en") {
      return settings.direction;
    }
    const texts = [...document.querySelectorAll(CANDIDATE_SELECTOR)]
      .filter((el) => !el.closest(SKIP_CLOSEST))
      .map((el) => el.innerText.replace(/\s+/g, " ").trim())
      .filter((t) => t.length >= 15)
      .slice(0, 20);
    let en = 0, ja = 0;
    for (const t of texts) {
      const lang = await detectedLang(t);
      if (lang === "en") en++;
      else if (lang === "ja") ja++;
    }
    return ja > en ? "ja-en" : "en-ja";
  }

  // ---------- translation backends ----------

  async function makeChromeBackend(src, tgt) {
    if (!("Translator" in self)) return null;
    try {
      const availability = await Translator.availability({
        sourceLanguage: src, targetLanguage: tgt,
      });
      if (availability === "unavailable") return null;
      const translator = await Translator.create({
        sourceLanguage: src, targetLanguage: tgt,
      });
      return {
        name: "Chrome内蔵",
        translate: async (sentence) => (await translator.translate(sentence)).trim(),
      };
    } catch {
      return null;
    }
  }

  function makeOllamaBackend(direction) {
    return {
      name: `Ollama (${settings.model})`,
      translate: async (sentence, before, after) => {
        const resp = await chrome.runtime.sendMessage({
          type: "ollama-translate", sentence, before, after,
          model: settings.model, direction,
        });
        if (!resp?.ok) throw new Error(resp?.error || "no response");
        return resp.ja;
      },
    };
  }

  // ---------- difficulty scoring ----------

  function difficultyEn(s) {
    const words = s.match(/[A-Za-z']+/g) || [];
    if (!words.length) return 0;
    const avg = words.reduce((a, w) => a + w.length, 0) / words.length;
    const longRatio = words.filter((w) => w.length >= 8).length / words.length;
    return avg + 4 * longRatio + 0.05 * words.length;
  }

  function difficultyJa(s) {
    const kanji = (s.match(/[㐀-䶿一-鿿]/g) || []).length;
    return s.length + 2 * kanji;
  }

  function hashThreshold(s) {
    let h = 0x811c9dc5; // FNV-1a
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return (h >>> 0) / 2 ** 32;
  }

  // ---------- session state (rebuilt on direction flip) ----------

  let direction, src, tgt, backend, segmenter;
  let restore = [];   // [element, original nodes, created nodes]
  let spans = [];
  let queue = [];
  let running = 0;
  let host = null, slider = null, pct = null, tip = null;
  const CONCURRENCY = 3;
  const manual = new Map();

  function teardown() {
    queue = [];
    manual.clear();
    for (const [el, originals, created] of restore) {
      const present = created.filter((n) => n.parentNode === el);
      if (!present.length) continue;
      const marker = document.createTextNode("");
      el.insertBefore(marker, present[0]);
      for (const n of present) n.remove();
      for (const o of originals) el.insertBefore(o, marker);
      marker.remove();
    }
    restore = [];
    spans = [];
    host?.remove();
    host = null;
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("mouseover", onOver, true);
    document.removeEventListener("mouseout", onOut, true);
  }

  api.deactivate = () => {
    if (!alive) return;
    alive = false;
    teardown();
    try {
      chrome.runtime.sendMessage({ type: "enja-remove-css" });
    } catch {
      /* extension context may be gone (e.g. harness) */
    }
    delete window.__enjaReader;
  };

  // ---------- build ----------

  async function build(dir) {
    direction = dir;
    [src, tgt] = dir === "ja-en" ? ["ja", "en"] : ["en", "ja"];
    segmenter = new Intl.Segmenter(src, { granularity: "sentence" });

    backend = null;
    if (settings.backend !== "ollama") backend = await makeChromeBackend(src, tgt);
    if (!backend && settings.backend !== "chrome") backend = makeOllamaBackend(dir);
    if (!alive) return false;
    if (!backend) {
      alert("enja-reader: 翻訳バックエンドが利用できません。Chrome 138+ か、Ollama の起動が必要です。");
      return false;
    }

    // collect blocks in the source language
    const minLen = src === "ja" ? 12 : 25;
    const blocks = [];
    for (const el of document.querySelectorAll(CANDIDATE_SELECTOR)) {
      if (el.closest(SKIP_CLOSEST)) continue;
      if (el.querySelector(BLOCK_CHILD)) continue;
      if (!el.getClientRects().length) continue;
      const text = el.innerText.replace(/\s+/g, " ").trim();
      const isHeading = /^H[1-6]$/.test(el.tagName);
      if (text.length < (isHeading ? 4 : minLen)) continue;
      if ((await detectedLang(text)) !== src) continue;
      blocks.push({ el, text });
    }
    if (!alive) return false;

    for (const b of blocks) {
      const sentences = [...segmenter.segment(b.text)]
        .map((s) => s.segment.trim()).filter(Boolean);
      if (!sentences.length) continue;
      const originals = [...b.el.childNodes];
      const created = [];
      for (const n of originals) n.remove();
      sentences.forEach((sent, i) => {
        if (i > 0 && src === "en") {
          const sep = document.createTextNode(" ");
          created.push(sep);
          b.el.appendChild(sep);
        }
        const span = document.createElement("span");
        span.className = "enja-s";
        span.textContent = sent;
        spans.push({
          span, srcText: sent, out: null, pending: false, failed: false,
          before: sentences[i - 1] || "", after: sentences[i + 1] || "",
        });
        created.push(span);
        b.el.appendChild(span);
      });
      restore.push([b.el, originals, created]);
    }

    if (!spans.length) {
      alert("enja-reader: このページに処理対象の文が見つかりません。");
      teardown();
      return false;
    }

    // thresholds: for en->ja hard sentences flip to JA first (support);
    // for ja->en easy sentences flip to EN first (practice)
    if (settings.select === "difficulty") {
      const score = src === "ja" ? difficultyJa : difficultyEn;
      const hardFirst = direction === "en-ja";
      const order = spans.map((_, i) => i).sort((a, b) =>
        hardFirst
          ? score(spans[b].srcText) - score(spans[a].srcText)
          : score(spans[a].srcText) - score(spans[b].srcText));
      order.forEach((idx, rank) => { spans[idx].h = (rank + 0.5) / spans.length; });
    } else {
      for (const s of spans) s.h = hashThreshold(s.srcText);
    }

    buildBar();
    document.addEventListener("click", onClick, true);
    document.addEventListener("mouseover", onOver, true);
    document.addEventListener("mouseout", onOut, true);
    applyAll();
    return true;
  }

  // ---------- translation queue ----------

  function enqueue(rec, priority = false) {
    if (!alive || rec.out !== null || rec.failed) return;
    if (rec.pending) {
      if (priority) {
        const i = queue.indexOf(rec);
        if (i > 0) {
          queue.splice(i, 1);
          queue.unshift(rec);
        }
      }
      return;
    }
    rec.pending = true;
    rec.span.classList.add("enja-pending");
    priority ? queue.unshift(rec) : queue.push(rec);
    pump();
  }

  function pump() {
    while (alive && running < CONCURRENCY && queue.length) {
      const rec = queue.shift();
      const myBackend = backend;
      running++;
      myBackend.translate(rec.srcText, rec.before, rec.after)
        .then((out) => { rec.out = out; })
        .catch(() => { rec.failed = true; })
        .finally(() => {
          rec.pending = false;
          rec.span.classList.remove("enja-pending");
          running--;
          if (!alive || !spans.includes(rec)) return;
          render(rec);
          pump();
        });
    }
  }

  // ---------- rendering ----------

  function wantedTranslated(rec) {
    if (manual.has(rec)) return manual.get(rec);
    return rec.h < slider.value / 100;
  }

  function render(rec) {
    const want = wantedTranslated(rec);
    const showOut = want && rec.out !== null;
    rec.span.textContent = showOut ? rec.out : rec.srcText;
    rec.span.classList.toggle("enja-ja", showOut);
    rec.span.classList.toggle("enja-manual", manual.has(rec));
    rec.span.setAttribute("lang", showOut ? tgt : src);
    if (want && rec.out === null) enqueue(rec);
    updateBar();
  }

  function applyAll() {
    for (const rec of spans) render(rec);
  }

  // ---------- control bar ----------

  function buildBar() {
    host = document.createElement("div");
    host.id = "enja-bar-host";
    const shadow = host.attachShadow({ mode: "open" });
    const knobLabel = tgt === "ja" ? "日本語比率" : "英語比率";
    const dirLabel = direction === "en-ja" ? "英→日" : "日→英";
    shadow.innerHTML = `
      <style>
        :host { all: initial; }
        * { box-sizing: border-box; margin: 0; }
        .bar {
          position: fixed; top: 14px; right: 14px; z-index: 2147483647;
          background: rgba(252, 252, 253, .92); color: #1c1f24;
          backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
          border: 1px solid rgba(0,0,0,.08); border-radius: 14px;
          padding: 10px 14px 9px;
          font: 13px/1.5 "Segoe UI", "Hiragino Sans", "Yu Gothic UI", sans-serif;
          box-shadow: 0 6px 24px rgba(0,0,0,.14);
          display: flex; flex-direction: column; gap: 7px; width: 264px;
          transition: opacity .18s;
        }
        @media (prefers-color-scheme: dark) {
          .bar { background: rgba(27, 31, 36, .92); color: #e8eaed;
                 border-color: rgba(255,255,255,.09);
                 box-shadow: 0 6px 24px rgba(0,0,0,.45); }
          .pill { background: rgba(255,255,255,.08); }
          button.icon { color: #9aa4b2; }
          .meta { color: #9aa4b2; }
        }
        .head { display: flex; align-items: center; gap: 8px; }
        .logo { font-weight: 600; letter-spacing: .02em; font-size: 12.5px; }
        .pill {
          background: rgba(0,0,0,.06); border: none; border-radius: 999px;
          padding: 2px 10px; font-size: 11.5px; cursor: pointer; color: inherit;
          font-family: inherit;
        }
        .pill:hover { outline: 1.5px solid #4b8bf5; }
        .spacer { flex: 1; }
        button.icon {
          background: none; border: none; cursor: pointer; color: #667085;
          font-size: 14px; line-height: 1; padding: 2px 4px; font-family: inherit;
        }
        button.icon:hover { color: inherit; }
        .row { display: flex; align-items: center; gap: 8px; }
        .knob-label { font-size: 12px; white-space: nowrap; }
        input[type=range] {
          flex: 1; accent-color: #4b8bf5; height: 4px; cursor: pointer;
        }
        .pct { font-size: 11.5px; font-variant-numeric: tabular-nums;
               white-space: nowrap; min-width: 6.5em; text-align: right; }
        .meta { color: #667085; font-size: 11px; display: flex;
                justify-content: space-between; align-items: center; }
        .reset { background: none; border: none; color: inherit; cursor: pointer;
                 font-size: 11px; text-decoration: underline dotted; font-family: inherit; }
        .mini {
          position: fixed; top: 14px; right: 14px; z-index: 2147483647;
          width: 36px; height: 36px; border-radius: 999px; border: 1px solid rgba(0,0,0,.1);
          background: rgba(252,252,253,.94); color: #1c1f24; cursor: pointer;
          font-size: 15px; box-shadow: 0 4px 14px rgba(0,0,0,.18); display: none;
        }
        @media (prefers-color-scheme: dark) {
          .mini { background: rgba(27,31,36,.94); color: #e8eaed;
                  border-color: rgba(255,255,255,.12); }
        }
        .tip {
          position: fixed; z-index: 2147483647; max-width: 32rem; display: none;
          background: rgba(28, 31, 36, .96); color: #f2f4f7;
          font: 12.5px/1.65 "Segoe UI", "Hiragino Sans", "Yu Gothic UI", sans-serif;
          padding: 8px 11px; border-radius: 10px; pointer-events: none;
          box-shadow: 0 6px 20px rgba(0,0,0,.3);
        }
        @media (prefers-color-scheme: dark) {
          .tip { background: rgba(242, 244, 247, .97); color: #1c1f24; }
        }
      </style>
      <div class="bar">
        <div class="head">
          <span class="logo">enja</span>
          <button class="pill dir" title="翻訳方向を切り替え">${dirLabel} ⇄</button>
          <span class="spacer"></span>
          <button class="icon collapse" title="折りたたむ">–</button>
          <button class="icon close" title="解除して元に戻す">×</button>
        </div>
        <div class="row">
          <span class="knob-label">${knobLabel}</span>
          <input type="range" min="0" max="100" value="${initialRatio}">
          <span class="pct"></span>
        </div>
        <div class="meta">
          <span class="backend"></span>
          <button class="reset">個別切替をリセット</button>
        </div>
      </div>
      <button class="mini" title="enja-reader を開く">英⇄</button>
      <div class="tip"></div>`;
    document.documentElement.appendChild(host);

    slider = shadow.querySelector("input");
    pct = shadow.querySelector(".pct");
    tip = shadow.querySelector(".tip");
    shadow.querySelector(".backend").textContent =
      `${backend.name} · ${settings.select === "difficulty" ? "難易度順" : "安定ランダム"}`;

    slider.addEventListener("input", applyAll);
    shadow.querySelector(".reset").addEventListener("click", () => {
      manual.clear();
      applyAll();
    });
    shadow.querySelector(".close").addEventListener("click", api.deactivate);
    const barEl = shadow.querySelector(".bar");
    const mini = shadow.querySelector(".mini");
    shadow.querySelector(".collapse").addEventListener("click", () => {
      barEl.style.display = "none";
      mini.style.display = "block";
    });
    mini.addEventListener("click", () => {
      mini.style.display = "none";
      barEl.style.display = "flex";
    });
    shadow.querySelector(".dir").addEventListener("click", async () => {
      const next = direction === "en-ja" ? "ja-en" : "en-ja";
      teardown();
      const okBuild = await build(next);
      if (!okBuild && alive) api.deactivate();
    });
  }

  function updateBar() {
    if (!pct) return;
    const done = spans.filter((r) => r.span.classList.contains("enja-ja")).length;
    const pending = spans.filter((r) => r.pending).length;
    pct.textContent = `${slider.value}% · ${done}/${spans.length}` +
      (pending ? ` (訳${pending})` : "");
  }

  // ---------- page interactions ----------

  function recOf(target) {
    const span = target.closest?.(".enja-s");
    if (!span) return null;
    return spans.find((r) => r.span === span) || null;
  }

  function showTip(rec) {
    const showingOut = rec.span.classList.contains("enja-ja");
    tip.textContent = showingOut ? rec.srcText : (rec.out ?? "(翻訳中…)");
    tip.style.display = "block";
    const r = rec.span.getBoundingClientRect();
    tip.style.left = Math.min(r.left, innerWidth - 520) + "px";
    tip.style.top = r.bottom + 8 + "px";
    if (!showingOut && rec.out === null) enqueue(rec, true);
  }

  function onClick(e) {
    const rec = recOf(e.target);
    if (!rec) return;
    e.preventDefault();
    e.stopPropagation();
    manual.set(rec, !wantedTranslated(rec));
    if (manual.get(rec) && rec.out === null) enqueue(rec, true);
    render(rec);
    showTip(rec);
  }
  function onOver(e) {
    const rec = recOf(e.target);
    if (rec) showTip(rec);
  }
  function onOut() {
    if (tip) tip.style.display = "none";
  }

  // ---------- go ----------

  const ok = await build(await detectDirection());
  if (!ok && alive) api.deactivate();
})();
