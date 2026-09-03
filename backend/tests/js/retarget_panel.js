// generate.js の踏襲モードまわり。
//
//   - 前年度の 2 本がそろわないと踏襲モードを押せないこと
//   - 何が足りないかが文言に出ること
//   - 組み替え対象が理由ごとにまとまり、件数が読めること
//
// 踏襲モードそのものは前年度の実データが無いと E2E で通せないので、
// 画面側の挙動はここで押さえる。
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const { element, createDocument, attributeValues } = require("./dom_stub.js");
const JS_DIR = path.join(__dirname, "..", "..", "..", "frontend", "js");

const REASONS = {
  parttime: "非専任（非常勤）",
  special: "非専任（特任）",
  fresh: "前年度に存在しない新規科目",
  teacher: "担当教員の変更",
};

function load(summary, selectedMode) {
  // モードのラジオ。querySelector は value を含むセレクタで引かれる。
  const modes = {};
  ["mock", "optimize", "inherit"].forEach((value) => {
    const radio = element(`mode-${value}`);
    radio.value = value;
    radio.checked = value === (selectedMode || "mock");
    radio.disabled = false;
    modes[value] = radio;
  });

  const checkboxes = [];
  const document = createDocument({
    matchers: {
      'value="inherit"': modes.inherit,
      'value="optimize"': modes.optimize,
      'value="mock"': modes.mock,
      'input[name="mode"]:checked': Object.values(modes).filter((m) => m.checked),
      "#retarget-list input[type=checkbox]": checkboxes,
      "#retarget-list input:checked": checkboxes.filter((b) => b.checked),
    },
  });

  const sandbox = {
    console, document,
    window: { appState: { sessionId: "s1", summary }, localStorage: {
      getItem: () => null, setItem() {}, removeItem() {},
    } },
    api: {},
    escapeHtml: (value) => String(value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;"),
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "generate.js"), "utf8"), sandbox);
  return { sandbox, document, modes, checkboxes };
}

const FULL = {
  subject_count: 658, intensive_count: 45,
  has_previous_year: true, has_previous_teachers: true,
};

function availability(summary, selectedMode) {
  const { sandbox, document, modes } = load(summary, selectedMode);
  sandbox.updateInheritAvailability();
  const note = document.nodes["inherit-note"];
  return {
    inherit_disabled: modes.inherit.disabled,
    note_hidden: note.hidden === true,
    note: note.textContent,
    mock_checked: modes.mock.checked,
    inherit_checked: modes.inherit.checked,
  };
}

function retargetList() {
  const items = [
    ...Array.from({ length: 3 }, (_, i) => ({
      code: `P${i}`, name: `非常勤の科目${i}`, teacher: "非常勤先生",
      reason: REASONS.parttime,
    })),
    { code: "S0", name: "特任の科目", teacher: "特任先生", reason: REASONS.special },
    { code: "S1", name: "特任の科目2", teacher: "特任先生", reason: REASONS.special },
    { code: "N0", name: '<img src=x onerror=alert(1)>', teacher: "新任先生",
      reason: REASONS.fresh },
  ];
  const { sandbox, document, checkboxes } = load(FULL);
  vm.runInContext(`retargetItems = ${JSON.stringify(items)};`, sandbox);
  sandbox.renderRetargetList();
  const html = document.nodes["retarget-list"].innerHTML;

  // 書き出された HTML からチェックボックスの実体を起こし、全解除を試す
  attributeValues(html, "value").forEach((value) => {
    const box = element(`box-${value}`);
    box.value = value;
    box.checked = true;
    box.type = "checkbox";
    checkboxes.push(box);
  });
  sandbox.setAllRetarget(false);

  return {
    summary_text: (html.match(/class="retarget-summary">([\s\S]*?)<\/p>/) || [])[1]
      .replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim(),
    group_headings: (html.match(/<summary>([\s\S]*?)<\/summary>/g) || [])
      .map((m) => m.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim()),
    group_count: (html.match(/class="retarget-group"/g) || []).length,
    groups_start_closed: !/class="retarget-group" open/.test(html),
    codes: attributeValues(html, "value"),
    has_raw_tag: html.includes("<img"),
    has_escaped_tag: html.includes("&lt;img"),
    all_cleared: checkboxes.every((b) => b.checked === false),
  };
}

function emptyList() {
  const { sandbox, document } = load(FULL);
  vm.runInContext("retargetItems = [];", sandbox);
  sandbox.renderRetargetList();
  return document.nodes["retarget-list"].innerHTML.replace(/\s+/g, " ").trim();
}

// AI モードは API キーが要る。キーが無いまま選べると、サーバが黙って
// モックへ落とすので「AI で作ったつもりの時間割」が出来上がる。
function aiAvailability(hasApiKey, selectedMode) {
  const { sandbox, document, modes } = load(FULL, selectedMode);
  sandbox.updateAiAvailability({ has_api_key: hasApiKey });
  const note = document.nodes["ai-note"];
  return {
    ai_disabled: modes.optimize.disabled,
    note_hidden: note.hidden === true,
    note: note.textContent,
    mock_checked: modes.mock.checked,
  };
}

// 踏襲モードでは重み付けを畳む。組み替え対象までスクロールが遠くなるため。
function weightsFolding(mode) {
  const { sandbox, document } = load(FULL, mode);
  sandbox.foldWeightsForMode();
  return document.nodes["params"].open;
}

// 組み替え対象を誰に任せるか。API キーが無ければ AI は選べない。
function retargetMethod(hasApiKey, picked) {
  const { sandbox, document } = load(FULL);
  // スタブは HTML の option を解釈しないので、既定値を明示して与える。
  const select = document.getElementById("retarget-method");
  select.value = picked || "solver";
  sandbox.updateAiAvailability({ has_api_key: hasApiKey });
  return {
    ai_disabled: select.disabled === true,
    value: select.value,
    chosen: sandbox.selectedRetargetMethod(),
  };
}

console.log(JSON.stringify({
  both_present: availability(FULL),
  timetable_only: availability({ ...FULL, has_previous_teachers: false }),
  teachers_only: availability({ ...FULL, has_previous_year: false }),
  neither: availability({ ...FULL, has_previous_year: false,
                          has_previous_teachers: false }),
  falls_back_to_mock: availability(
    { ...FULL, has_previous_teachers: false }, "inherit"),
  no_summary_yet: availability(undefined),
  list: retargetList(),
  empty: emptyList(),
  ai_with_key: aiAvailability(true),
  ai_without_key: aiAvailability(false),
  ai_falls_back_to_mock: aiAvailability(false, "optimize"),
  weights_open_for_mock: weightsFolding("mock"),
  weights_open_for_ai: weightsFolding("optimize"),
  weights_open_for_inherit: weightsFolding("inherit"),
  method_with_key: retargetMethod(true),
  method_with_key_and_ai: retargetMethod(true, "ai"),
  method_without_key: retargetMethod(false, "ai"),
}));
