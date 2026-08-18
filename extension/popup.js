// Popup: activate/deactivate on the current tab + persistent settings.

const DEFAULTS = {
  backend: "auto", select: "hash", ratio: 30, model: "gemma2", direction: "auto",
};

const $ = (id) => document.getElementById(id);
const toggleBtn = $("toggle");

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function isActive(tabId) {
  try {
    const [res] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => !!window.__enjaReader,
    });
    return !!res?.result;
  } catch {
    return null; // page we can't script (chrome://, store, etc.)
  }
}

function renderToggle(state) {
  if (state === null) {
    toggleBtn.textContent = "このページでは使えません";
    toggleBtn.disabled = true;
    return;
  }
  toggleBtn.disabled = false;
  toggleBtn.classList.toggle("active", state);
  toggleBtn.textContent = state ? "解除して元に戻す" : "このページで有効化";
}

async function init() {
  const settings = Object.assign(
    {}, DEFAULTS, await chrome.storage.sync.get(Object.keys(DEFAULTS)),
  );
  $("direction").value = settings.direction;
  $("select").value = settings.select;
  $("backend").value = settings.backend;
  $("model").value = settings.model;
  $("ratio").value = settings.ratio;
  $("ratioVal").textContent = `${settings.ratio}%`;
  $("modelField").style.display = settings.backend === "chrome" ? "none" : "flex";

  const tab = await currentTab();
  const state = tab && /^https?:/.test(tab.url || "") ? await isActive(tab.id) : null;
  renderToggle(state);

  toggleBtn.addEventListener("click", async () => {
    toggleBtn.disabled = true;
    // content.js toggles: it deactivates itself if already active
    if (!(await isActive(tab.id))) {
      await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["content.css"] });
    }
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    window.close();
  });

  for (const id of ["direction", "select", "backend", "model"]) {
    $(id).addEventListener("change", () => {
      chrome.storage.sync.set({ [id]: $(id).value });
      if (id === "backend") {
        $("modelField").style.display = $(id).value === "chrome" ? "none" : "flex";
      }
    });
  }
  $("ratio").addEventListener("input", () => {
    $("ratioVal").textContent = `${$("ratio").value}%`;
    chrome.storage.sync.set({ ratio: Number($("ratio").value) });
  });
}

init();
