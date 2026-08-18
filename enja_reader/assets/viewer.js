/* enja-reader viewer: renders sentence pairs and drives the JA-ratio knob.
 * Depends only on: #data (JSON script tag), #doc, #ratio, #pct, #reset, #tip.
 * Kept free of build-time logic so a Chrome extension can reuse it as-is. */

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

let openList = null; // {el, ordered, level}

function listContainerFor(b) {
  const ordered = !!b.ordered;
  if (!openList || openList.ordered !== ordered || openList.level !== (b.level || 0)) {
    const el = document.createElement(ordered ? "ol" : "ul");
    if (b.level) el.style.marginLeft = (b.level * 1.2) + "rem";
    docEl.appendChild(el);
    openList = { el, ordered, level: b.level || 0 };
  }
  return openList.el;
}

for (const b of blocks) {
  if (b.kind !== "list_item") openList = null;

  if (b.kind === "code") {
    const pre = document.createElement("pre");
    pre.textContent = b.text;
    docEl.appendChild(pre);
    continue;
  }

  let container;
  if (b.kind === "heading") {
    container = document.createElement("h" + Math.min(b.level || 1, 6));
  } else if (b.kind === "list_item") {
    container = document.createElement("li");
  } else if (b.kind === "quote") {
    container = document.createElement("blockquote");
  } else {
    container = document.createElement("p");
  }

  b.sentences.forEach((s, i) => {
    if (i > 0) container.appendChild(document.createTextNode(" "));
    container.appendChild(makeSentence(s));
  });

  if (b.kind === "list_item") {
    listContainerFor(b).appendChild(container);
  } else {
    docEl.appendChild(container);
  }
}

function langFor(el, ratio) {
  if (manual.has(el)) return manual.get(el);
  return parseFloat(el.dataset.h) < ratio ? "ja" : "en";
}

function apply() {
  const ratio = slider.value / 100;
  let jaCount = 0;
  for (const el of spans) {
    const lang = langFor(el, ratio);
    if (lang === "ja") jaCount++;
    el.textContent = el.dataset[lang];
    el.classList.toggle("ja", lang === "ja");
    el.classList.toggle("manual", manual.has(el));
    el.setAttribute("lang", lang);
  }
  pct.textContent = slider.value + "% (" + jaCount + "/" + spans.length + "文)";
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
