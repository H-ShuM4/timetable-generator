// upload.js の restoreSession を、最小限の DOM スタブ上で動かす。
//
// ブラウザ操作は自動検証できておらず、結果タブが復元時に有効化されない
// 不具合を実機で初めて見つけた。ブラウザ全体を用意しなくても、この程度の
// スタブで「どのタブが有効になるか」は確かめられる。
//
// 出力は JSON 1 行。呼び出し側（pytest）が読む。
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const UPLOAD_JS = path.join(__dirname, "..", "..", "..", "frontend", "js", "upload.js");

const { createDocument } = require("./dom_stub.js");

function element(id) {
  return {
    id, innerHTML: "", textContent: "", disabled: true, prepended: null,
    prepend(node) { this.prepended = node; },
    addEventListener() {},
  };
}

function run(resultStatus, savedSessionId) {
  const nodes = {};
  const tabs = { generate: element("tab-generate"), result: element("tab-result") };
  const saved = savedSessionId ? { "timetable.sessionId": savedSessionId } : {};

  const sandbox = {
    console,
    window: {
      appState: { sessionId: null },
      localStorage: {
        getItem: (key) => (key in saved ? saved[key] : null),
        setItem: (key, value) => { saved[key] = value; },
        removeItem: (key) => { delete saved[key]; },
      },
    },
    document: {
      getElementById: (id) => (nodes[id] ||= element(id)),
      querySelector: (selector) =>
        selector.includes('"result"') ? tabs.result : tabs.generate,
      querySelectorAll: () => [],
      createElement: () => element("note"),
      addEventListener() {},
    },
    api: {
      getSession: async () => {
        if (!savedSessionId) throw new Error("見つかりません");
        return {
          session_id: savedSessionId,
          summary: {
            subject_count: 658, teacher_count: 99, intensive_count: 0,
            quarter_count: 0, by_department: {}, by_category: {},
            by_teacher_kind: {}, has_previous_year: false,
          },
          warnings: [],
        };
      },
      getResult: async () => ({ status: resultStatus }),
    },
    escapeHtml: (value) => String(value),
  };

  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(UPLOAD_JS, "utf8"), sandbox);
  return sandbox.restoreSession().then(() => ({
    session_id: sandbox.window.appState.sessionId,
    generate_tab_enabled: !tabs.generate.disabled,
    result_tab_enabled: !tabs.result.disabled,
    note: nodes["upload-summary"] ? (nodes["upload-summary"].prepended || {}).textContent : null,
    remembered: saved["timetable.sessionId"] || null,
  }));
}

function summaryMarkup() {
  const document = createDocument();
  const sandbox = {
    console, document, api: {},
    window: { appState: {}, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } },
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "..", "..",
    "frontend", "js", "logviewer.js"), "utf8"), sandbox);
  vm.runInContext(fs.readFileSync(UPLOAD_JS, "utf8"), sandbox);
  sandbox.renderSummary({
    subject_count: 658, teacher_count: 99, intensive_count: 45, quarter_count: 47,
    by_department: { "会計": 234, "経営": 262 },
    by_category: { "必修": 344 },
    by_teacher_kind: { "非常勤": 59 },
    has_previous_year: false,
  });
  sandbox.renderWarnings([{ kind: "missing_availability", message: "出勤可能日が空欄です" }]);
  return {
    stats: (document.nodes["upload-summary"].innerHTML
      .match(/class="stat-value">(\d+)</g) || []).map((m) => m.match(/>(\d+)</)[1]),
    tallies: (document.nodes["upload-summary"].innerHTML
      .match(/class="tally">([^<]*)</g) || []).map((m) => m.match(/>([^<]*)</)[1].trim()),
    warning_count_class: (document.nodes["upload-warnings"].innerHTML
      .match(/class="(count [a-z]+)"/) || [])[1] || null,
  };
}

(async () => {
  console.log(JSON.stringify({
    with_result: await run("done", "abc123"),
    without_result: await run("pending", "abc123"),
    nothing_saved: await run("done", null),
    summary: summaryMarkup(),
  }));
})();
