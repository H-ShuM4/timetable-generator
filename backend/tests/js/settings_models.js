// settings.js の予備モデル欄と、logviewer.js のログパネル開閉。
// どちらも実機でしか確認できていなかった部分。
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const { element, createDocument, attributeValues } = require("./dom_stub.js");
const JS_DIR = path.join(__dirname, "..", "..", "..", "frontend", "js");

function loadSettings() {
  const boxes = [];
  const document = createDocument({ matchers: { ".fallback-model": boxes } });
  const sandbox = { console, document, window: {}, api: {} };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "settings.js"), "utf8"), sandbox);
  return { sandbox, document, boxes };
}

/** renderFallbackCandidates が書いた HTML から、チェックボックスの実体を作る。 */
function materialise(document, boxes) {
  const values = attributeValues(document.nodes["fallback-models"].innerHTML, "value");
  boxes.length = 0;
  values.forEach((value) => {
    const box = element(`box-${value}`);
    box.value = value;
    boxes.push(box);
  });
  return values;
}

function settingsCases() {
  const out = {};
  const { sandbox, document, boxes } = loadSettings();

  sandbox.renderFallbackCandidates();
  out.candidates = materialise(document, boxes);

  // 保存済みの設定を画面へ流し込む
  sandbox.applyFallbackModels(["gemini-3.6-flash", "自作モデル"]);
  out.checked_after_apply = boxes.filter((b) => b.checked).map((b) => b.value);
  out.extra_after_apply = document.nodes["fallback-extra"].value;

  // 画面から設定を集める。並び順がそのまま切り替え順になる
  boxes.forEach((b) => { b.checked = false; });
  boxes[3].checked = true;
  boxes[0].checked = true;
  document.nodes["fallback-extra"].value = " 手入力A , ,手入力B ";
  out.collected = sandbox.collectFallbackModels();

  boxes.forEach((b) => { b.checked = false; });
  document.nodes["fallback-extra"].value = "";
  out.collected_empty = sandbox.collectFallbackModels();
  return out;
}

function logPanelCases() {
  const document = createDocument();
  const sandbox = { console, document, window: {}, api: {}, EventSource: function () {} };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "logviewer.js"), "utf8"), sandbox);

  const panel = document.getElementById("log-panel");
  const toggle = document.getElementById("log-toggle");
  const seen = [];
  sandbox.openLogPanel();
  seen.push({ collapsed: panel.classList.contains("collapsed"), label: toggle.textContent });
  sandbox.collapseLogPanel();
  seen.push({ collapsed: panel.classList.contains("collapsed"), label: toggle.textContent });
  return seen;
}

console.log(JSON.stringify({
  settings: settingsCases(),
  log_panel: logPanelCases(),
  escape: {
    tag: (() => {
      const sandbox = { console, document: createDocument(), window: {}, api: {},
                        EventSource: function () {} };
      vm.createContext(sandbox);
      vm.runInContext(fs.readFileSync(path.join(JS_DIR, "logviewer.js"), "utf8"), sandbox);
      return sandbox.escapeHtml('<b>&"\'');
    })(),
  },
}));
