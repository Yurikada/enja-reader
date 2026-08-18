// enja-reader content script: sentence-level EN/JA blending on any page.
// Injected on action click; clicking the action again deactivates.
// Translation backends: Chrome built-in Translator API (default) or
// local Ollama proxied through the service worker.
(async () => {
  if (window.__enjaReader) {
    window.__enjaReader.deactivate();
    return;
  }

  const settings = Object.assign(
    { backend: "auto", select: "hash", ratio: 30, model: "gemma2" },
    await chrome.storage.sync.get(["backend", "select", "ratio", "model"]),
  );

  // ---------- translation backends ----------

  async function makeChromeBackend() {
    if (!("Translator" in self)) return null;
    try {
      const availability = await Translator.availability({
        sourceLanguage: "en", targetLanguage: "ja",
      });
      if (availability === "unavailable") return null;
      const translator = await Translator.create({
        sourceLanguage: "en", targetLanguage: "ja",
      });
      return {
        name: "Chrome内蔵",
        translate: async (sentence) => (await translator.translate(sentence)).trim(),
      };
    } catch {
      return null;
    }
  }

  function makeOllamaBackend() {
    return {
      name: `Ollama (${settings.model})`,
      translate: async (sentence, before, after) => {
        const resp = await chrome.runtime.sendMessage({
          type: "ollama-translate", sentence, before, after, model: settings.model,
        });
        if (!resp?.ok) throw new Error(resp?.error || "no response");
        return resp.ja;
      },
    };
  }

  let backend = null;
  if (settings.backend !== "ollama") backend = await makeChromeBackend();
  if (!backend && settings.backend !== "chrome") backend = makeOllamaBackend();
  if (!backend) {
    alert("enja-reader: 翻訳バックエンドが利用できません。Chrome 138+ か、Ollama の起動が必要です。");
    return;
  }

  // ---------- block collection ----------

  const SKIP_CLOSEST = "nav, footer, aside, pre, code, [contenteditable], .enja-s";
  const BLOCK_CHILD = "p, div, ul, ol, table, pre, blockquote, h1, h2, h3, h4, h5, h6";

  function latinRatio(text) {
    const letters = text.match(/\p{L}/gu) || [];
    if (!letters.length) return 0;
    const latin = text.match(/[A-Za-z]/g) || [];
    return latin.length / letters.length;
  }

  function collectBlocks() {
    const blocks = [];
    for (const el of document.querySelectorAll(
      "p, h1, h2, h3, h4, h5, h6, li, blockquote, dd, figcaption",
    )) {
      if (el.closest(SKIP_CLOSEST)) continue;
      if (el.querySelector(BLOCK_CHILD)) continue;
      if (!el.getClientRects().length) continue;
      const text = el.innerText.replace(/\s+/g, " ").trim();
      const isHeading = /^H[1-6]$/.test(el.tagName);
      if (text.length < (isHeading ? 4 : 25)) continue;
      if (latinRatio(text) < 0.5) continue;
      blocks.push({ el, text, isHeading });
    }
    return blocks;
  }

  // ---------- sentence segmentation & thresholds ----------

  const segmenter = new Intl.Segmenter("en", { granularity: "sentence" });

  function splitSentences(text) {
    return [...segmenter.segment(text)]
      .map((s) => s.segment.trim())
      .filter(Boolean);
  }

  function hashThreshold(s) {
    let h = 0x811c9dc5; // FNV-1a
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return (h >>> 0) / 2 ** 32;
  }

  function difficultyScore(s) {
    const words = s.match(/[A-Za-z']+/g) || [];
    if (!words.length) return 0;
    const avg = words.reduce((a, w) => a + w.length, 0) / words.length;
    const longRatio = words.filter((w) => w.length >= 8).length / words.length;
    return avg + 4 * longRatio + 0.05 * words.length;
  }

  // ---------- wrap page sentences into spans ----------

  const blocks = collectBlocks();
  const spans = [];
  const restore = []; // [el, originalHTML]

  for (const b of blocks) {
    const sentences = splitSentences(b.text);
    if (!sentences.length) continue;
    restore.push([b.el, b.el.innerHTML]);
    b.el.textContent = "";
    sentences.forEach((sent, i) => {
      if (i > 0) b.el.appendChild(document.createTextNode(" "));
      const span = document.createElement("span");
      span.className = "enja-s";
      span.textContent = sent;
      span.dataset.en = sent;
      spans.push({
        span, en: sent, ja: null, pending: false,
        before: sentences[i - 1] || "", after: sentences[i + 1] || "",
      });
      b.el.appendChild(span);
    });
  }

  if (!spans.length) {
    alert("enja-reader: このページに処理対象の英文が見つかりません。");
    return;
  }

  if (settings.select === "difficulty") {
    const order = spans.map((_, i) => i)
      .sort((a, b) => difficultyScore(spans[b].en) - difficultyScore(spans[a].en));
    order.forEach((idx, rank) => { spans[idx].h = (rank + 0.5) / spans.length; });
  } else {
    for (const s of spans) s.h = hashThreshold(s.en);
  }

  const manual = new Map(); // span record -> forced lang

  // ---------- translation queue (lazy, concurrency-limited) ----------

  const queue = [];
  let running = 0;
  const CONCURRENCY = 3;

  function enqueue(rec, priority = false) {
    if (rec.ja !== null || rec.pending || rec.failed) return;
    rec.pending = true;
    rec.span.classList.add("enja-pending");
    priority ? queue.unshift(rec) : queue.push(rec);
    pump();
  }

  function pump() {
    while (running < CONCURRENCY && queue.length) {
      const rec = queue.shift();
      running++;
      backend.translate(rec.en, rec.before, rec.after)
        .then((ja) => { rec.ja = ja; })
        .catch(() => { rec.failed = true; })
        .finally(() => {
          rec.pending = false;
          rec.span.classList.remove("enja-pending");
          running--;
          render(rec);
          pump();
        });
    }
  }

  // ---------- rendering ----------

  function wantedLang(rec) {
    if (manual.has(rec)) return manual.get(rec);
    return rec.h < slider.value / 100 ? "ja" : "en";
  }

  function render(rec) {
    const lang = wantedLang(rec);
    const showJa = lang === "ja" && rec.ja !== null;
    rec.span.textContent = showJa ? rec.ja : rec.en;
    rec.span.classList.toggle("enja-ja", showJa);
    rec.span.classList.toggle("enja-manual", manual.has(rec));
    rec.span.setAttribute("lang", showJa ? "ja" : "en");
    if (lang === "ja" && rec.ja === null) enqueue(rec);
    updateBar();
  }

  function applyAll() {
    for (const rec of spans) render(rec);
  }

  // ---------- control bar (shadow DOM, isolated from page CSS) ----------

  const host = document.createElement("div");
  host.id = "enja-bar-host";
  const shadow = host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      .bar { position: fixed; top: 12px; right: 12px; z-index: 2147483647;
             background: #1b1f24ee; color: #e6e6e6; border-radius: 10px;
             padding: 10px 14px; font: 13px/1.5 "Segoe UI", "Yu Gothic UI", sans-serif;
             box-shadow: 0 4px 16px rgba(0,0,0,.35); display: flex;
             flex-direction: column; gap: 6px; min-width: 240px; }
      .row { display: flex; align-items: center; gap: 8px; }
      input[type=range] { flex: 1; accent-color: #60a5fa; }
      .pct { min-width: 7.5em; font-variant-numeric: tabular-nums; text-align: right; }
      .meta { color: #98a2b3; font-size: 11px; display: flex; justify-content: space-between; gap: 8px; }
      button { background: none; border: 1px solid #3a4048; color: #98a2b3;
               border-radius: 6px; padding: 2px 8px; cursor: pointer; font-size: 11px; }
      button:hover { color: #e6e6e6; }
      .tip { position: fixed; z-index: 2147483647; max-width: 30rem; display: none;
             background: #e6e6e6; color: #111; font-size: 12.5px; line-height: 1.6;
             padding: 7px 10px; border-radius: 8px; pointer-events: none; }
    </style>
    <div class="bar">
      <div class="row">
        <span>日本語比率</span>
        <input type="range" min="0" max="100" value="${settings.ratio}">
        <span class="pct"></span>
      </div>
      <div class="meta">
        <span class="backend"></span>
        <span>
          <button class="reset">個別リセット</button>
          <button class="close">解除</button>
        </span>
      </div>
    </div>
    <div class="tip"></div>`;
  document.documentElement.appendChild(host);

  const slider = shadow.querySelector("input");
  const pct = shadow.querySelector(".pct");
  const tip = shadow.querySelector(".tip");
  shadow.querySelector(".backend").textContent =
    `${backend.name} / ${settings.select}`;

  function updateBar() {
    const ja = spans.filter((r) => r.span.classList.contains("enja-ja")).length;
    const pending = spans.filter((r) => r.pending).length;
    pct.textContent = `${slider.value}% (${ja}/${spans.length}文` +
      (pending ? ` 訳${pending}` : "") + ")";
  }

  slider.addEventListener("input", applyAll);
  shadow.querySelector(".reset").addEventListener("click", () => {
    manual.clear();
    applyAll();
  });
  shadow.querySelector(".close").addEventListener("click", deactivate);

  // ---------- page interactions ----------

  function recOf(target) {
    const span = target.closest?.(".enja-s");
    if (!span) return null;
    return spans.find((r) => r.span === span) || null;
  }

  function showTip(rec) {
    const showingJa = rec.span.classList.contains("enja-ja");
    const other = showingJa ? rec.en : (rec.ja ?? "(翻訳中…)");
    tip.textContent = other;
    tip.style.display = "block";
    const r = rec.span.getBoundingClientRect();
    tip.style.left = Math.min(r.left, innerWidth - 500) + "px";
    tip.style.top = r.bottom + 8 + "px";
    if (!showingJa && rec.ja === null) enqueue(rec, true);
  }

  function onClick(e) {
    const rec = recOf(e.target);
    if (!rec) return;
    e.preventDefault();
    e.stopPropagation();
    const current = wantedLang(rec);
    manual.set(rec, current === "ja" ? "en" : "ja");
    if (manual.get(rec) === "ja" && rec.ja === null) enqueue(rec, true);
    render(rec);
    showTip(rec);
  }
  function onOver(e) {
    const rec = recOf(e.target);
    if (rec) showTip(rec);
  }
  function onOut() { tip.style.display = "none"; }

  document.addEventListener("click", onClick, true);
  document.addEventListener("mouseover", onOver, true);
  document.addEventListener("mouseout", onOut, true);

  // ---------- deactivate ----------

  function deactivate() {
    for (const [el, htmlText] of restore) el.innerHTML = htmlText;
    host.remove();
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("mouseover", onOver, true);
    document.removeEventListener("mouseout", onOut, true);
    delete window.__enjaReader;
  }

  window.__enjaReader = { deactivate };
  applyAll();
})();
