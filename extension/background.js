// Service worker: injects the content script on action click and proxies
// Ollama requests (content scripts are subject to page CORS; the worker
// is not, thanks to host_permissions).

const OLLAMA_URL = "http://localhost:11434/api/chat";

const SYSTEM_PROMPT = [
  "You are a professional English-to-Japanese translator. ",
  "Translate the target sentence into natural, fluent Japanese. ",
  "Use the surrounding context only to resolve pronouns and terminology. ",
  "Strictly write in plain form (だ・である調). Never use です・ます form. ",
  "Output ONLY the Japanese translation — no explanations, no romaji, ",
  "no quotation marks around the output.\n\n",
  "Examples of the required style:\n",
  "The system is fast. → このシステムは速い。\n",
  "This is how training wheels work. → これが補助輪の仕組みである。\n",
  "It must be a knob, not a constant. → それは定数ではなくノブでなければならない。\n",
  "You can adjust the ratio at any time. → 比率はいつでも調整できる。",
].join("");

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id || !/^https?:/.test(tab.url || "")) return;
  await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["content.css"] });
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "ollama-translate") return false;
  ollamaTranslate(msg).then(
    (ja) => sendResponse({ ok: true, ja }),
    (err) => sendResponse({ ok: false, error: String(err) }),
  );
  return true; // keep the channel open for the async response
});

async function ollamaTranslate({ sentence, before, after, model }) {
  const parts = [];
  if (before) parts.push(`Context (before): ${before}`);
  if (after) parts.push(`Context (after): ${after}`);
  parts.push(`Target sentence: ${sentence}`);
  const resp = await fetch(OLLAMA_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: model || "gemma2",
      stream: false,
      options: { temperature: 0.2 },
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: parts.join("\n") },
      ],
    }),
  });
  if (!resp.ok) throw new Error(`Ollama HTTP ${resp.status}`);
  const data = await resp.json();
  let ja = (data.message?.content || "").trim();
  // strip quotes only when they wrap the whole output as a matched pair
  for (const [open, close] of [['"', '"'], ["「", "」"], ["『", "』"], ["“", "”"]]) {
    if (ja.startsWith(open) && ja.endsWith(close) && !ja.slice(open.length, -close.length).includes(close)) {
      ja = ja.slice(open.length, -close.length).trim();
    }
  }
  return ja;
}
