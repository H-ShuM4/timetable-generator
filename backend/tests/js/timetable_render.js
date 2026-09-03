// timetable.js の描画とコマ計算。ご要望で入れた挙動が壊れていないか見る。
//   - 各コマの中を 1年→2年→3年→4年 の順に並べる
//   - 掴んだ位置を基準にした複数コマの移動
//   - 未配置科目を落としたときのコマ組み立て（▲科目は連続 2 コマ）
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const { createDocument, attributeValues } = require("./dom_stub.js");
const JS_DIR = path.join(__dirname, "..", "..", "..", "frontend", "js");

function load(result, matchers) {
  const document = createDocument({ matchers: matchers || {} });
  const sandbox = {
    console,
    document,
    window: { appState: { sessionId: "s1" }, alert() {} },
    api: {},
  };
  vm.createContext(sandbox);
  // escapeHtml は logviewer.js にある。描画がそれに依存している。
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "logviewer.js"), "utf8"), sandbox);
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "timetable.js"), "utf8"), sandbox);
  // resultData は let 宣言なのでサンドボックスのプロパティにはならない。
  // 値を渡すにはコンテキストの中で代入する必要がある。
  vm.runInContext(`resultData = ${JSON.stringify(result)};`, sandbox);
  return sandbox;
}

function placement(code, name, year, slots, extra) {
  return Object.assign({
    code, name, year, slots, teacher: "教員甲", department: "経営",
    term: "前期", category: "必修", source: "solver", quarter: null,
  }, extra || {});
}

const shuffled = {
  placements: [
    placement("C4", "科目丁", 4, ["月1"]),
    placement("C1", "科目甲", 1, ["月1"]),
    placement("C3", "科目丙", 3, ["月1"]),
    placement("C2", "科目乙", 2, ["月1"]),
    // 同じ 1 年の 2 件目。科目名で並ぶ
    placement("C0", "科目W", 1, ["月1"]),
  ],
  unplaced: [], intensive: [], violations: [],
};

const withViolation = {
  placements: [placement("V1", "科目甲", 1, ["火2"]), placement("V2", "科目乙", 1, ["火3"])],
  unplaced: [], intensive: [],
  violations: [{ rule_id: "H2", subject_code: "V1", message: "重複", related_code: "V2" }],
};

// 教員ビューの検証用。1 人の教員が学科をまたいで持つ状態を作る。
const acrossDepartments = {
  placements: [
    placement("M1", "経営の科目", 1, ["月1"], { teacher: "渡り先生", department: "経営" }),
    placement("A1", "会計の科目", 2, ["火2"], { teacher: "渡り先生", department: "会計" }),
    placement("J1", "短大の科目", 1, ["水3"], { teacher: "渡り先生", department: "短期大学部" }),
    placement("X1", "別の先生の科目", 1, ["月1"], { teacher: "別先生", department: "経営" }),
    placement("L1", "後期の科目", 1, ["木4"], { teacher: "渡り先生", term: "後期" }),
  ],
  unplaced: [], intensive: [], violations: [],
  teachers: [
    { name: "渡り先生", kind: "専任", research_day: "金", available_slots: [] },
    { name: "別先生", kind: "非常勤", research_day: null, available_slots: ["月1", "月2"] },
  ],
};

// 期間レールの検証用。開講期間が違う 3 枚を同じコマに置く。
const quarters = {
  placements: [
    placement("Q0", "通し科目", 2, ["月1"], { quarter: null, source: "gemini" }),
    placement("Q1", "前半科目", 3, ["月1"], { quarter: "後①", source: "prelock" }),
    placement("Q2", "後半科目", 4, ["月1"], { quarter: "前②", source: "manual" }),
  ],
  unplaced: [], intensive: [], violations: [],
};

const doubleSlot = {
  placements: [placement("D1", "▲科目", 1, ["水2", "水3"])],
  unplaced: [
    { code: "U1", name: "未配置甲", teacher: "教員乙", department: "経営", year: 1,
      term: "前期", category: "必修", slots_required: 1, requires_consecutive: false },
    { code: "U2", name: "▲未配置乙", teacher: "教員乙", department: "経営", year: 1,
      term: "前期", category: "必修", slots_required: 2, requires_consecutive: true },
  ],
  intensive: [], violations: [],
};

const withInheritSkips = {
  placements: [placement("K1", "踏襲できた科目", 1, ["月1"], { source: "inherited" })],
  unplaced: [], intensive: [], violations: [],
  inherit_skipped: [
    {
      subject: { code: "S1", name: '<img src=x onerror=alert(1)>', teacher: "専任甲",
                 department: "経営", year: 1, term: "前期", category: "必修" },
      rule_id: "H1", message: "専任甲 が 月1 に 別科目 と重複しています",
      related: { code: "K1", name: "踏襲できた科目", teacher: "専任甲",
                 department: "経営", year: 1, term: "前期", category: "必修" },
    },
  ],
};

// 印刷用シートの検証。学科 × 学期の 6 通りと、末尾の集中講義。
const forPrinting = {
  placements: [
    placement("P1", "経営前期の科目", 1, ["月1"], { department: "経営", term: "前期" }),
    placement("P2", "経営後期の科目", 2, ["月2"], { department: "経営", term: "後期" }),
    placement("P3", "会計前期の科目", 1, ["火1"], { department: "会計", term: "前期" }),
    placement("P4", "会計後期の科目", 3, ["火2"], { department: "会計", term: "後期" }),
    placement("P5", "短大前期の科目", 1, ["水1"], { department: "短期大学部", term: "前期" }),
    placement("P6", "短大後期の科目", 2, ["水2"], { department: "短期大学部", term: "後期" }),
    placement("P7", '<img src=x onerror=alert(1)>', 1, ["木1"],
              { department: "経営", term: "前期" }),
  ],
  unplaced: [],
  intensive: [
    { code: "I1", name: "集中の科目", teacher: "教員丙", department: "短期大学部",
      year: 1, term: "通年", category: "選択", slots_required: 1,
      requires_consecutive: false },
  ],
  violations: [],
};

function printCase() {
  const sandbox = load(forPrinting);
  sandbox.buildPrintSheets();
  const box = sandbox.document.nodes["print-sheets"];
  const html = box.innerHTML;
  const out = {
    headings: (html.match(/class="print-heading">([^<]*)</g) || [])
      .map((m) => m.match(/>([^<]*)</)[1].trim()),
    sheets: (html.match(/class="print-sheet"/g) || []).length,
    tables: (html.match(/class="timetable"/g) || []).length,
    codes: attributeValues(html, "data-code"),
    has_raw_tag: html.includes("<img"),
    has_escaped_tag: html.includes("&lt;img"),
    has_intensive: html.includes("集中の科目"),
    has_stamp: html.includes("print-stamp"),
  };
  sandbox.clearPrintSheets();
  out.cleared = box.innerHTML === "";
  return out;
}

function run() {
  const out = {};

  let sandbox = load(shuffled);
  sandbox.renderGrid();
  const html = sandbox.document.nodes["timetable-grid"].innerHTML;
  out.year_order = attributeValues(html, "data-code");

  sandbox = load(withViolation);
  out.violating_codes = Array.from(sandbox.violatingCodes()).sort();
  sandbox.renderGrid();
  out.violating_html = sandbox.document.nodes["timetable-grid"].innerHTML;

  sandbox = load(quarters);
  sandbox.renderGrid();
  const grid = sandbox.document.nodes["timetable-grid"].innerHTML;
  out.card_classes = (grid.match(/class="card [^"]*"/g) || []);
  out.card_titles = attributeValues(grid, "title");
  out.year_chips = (grid.match(/class="card-year y\d"/g) || []);
  out.rail_count = (grid.match(/class="card-rail"/g) || []).length;

  sandbox = load(doubleSlot);
  // 水3 のカードを掴んで木4 へ落とす（1 日ぶん右、1 コマぶん下）
  out.shifted = sandbox.shiftedSlots(doubleSlot.placements[0], "水3", "木4");
  // 先頭のコマを掴んで 5 限へ落とすと、2 コマ目が枠外になる
  out.shifted_out_of_range = sandbox.shiftedSlots(doubleSlot.placements[0], "水2", "木5");
  out.from_scratch_single = sandbox.slotsFromScratch(doubleSlot.unplaced[0], "月2");
  out.from_scratch_double = sandbox.slotsFromScratch(doubleSlot.unplaced[1], "月2");
  out.from_scratch_overflow = sandbox.slotsFromScratch(doubleSlot.unplaced[1], "月5");

  sandbox.renderSide();
  out.unplaced_html = sandbox.document.nodes["unplaced-list"].innerHTML;

  // ---- 踏襲できなかった科目 -----------------------------------------
  sandbox = load(withInheritSkips);
  sandbox.renderSide();
  out.skip_block_hidden = sandbox.document.nodes["block-inherit-skipped"].hidden === true;
  out.skip_count = sandbox.document.nodes["count-inherit-skipped"].textContent;
  out.skip_count_is_alert =
    sandbox.document.nodes["count-inherit-skipped"].classes.has("alert");
  out.skip_html = sandbox.document.nodes["inherit-skipped-list"].innerHTML
    .replace(/\s+/g, " ").trim();

  sandbox = load(shuffled);
  sandbox.renderSide();
  out.skip_block_hidden_when_empty =
    sandbox.document.nodes["block-inherit-skipped"].hidden === true;

  sandbox = load(acrossDepartments);
  vm.runInContext('currentView = "teacher"; currentTeacher = "渡り先生";', sandbox);
  sandbox.renderGrid();
  const teacherGrid = sandbox.document.nodes["timetable-grid"].innerHTML;
  out.teacher_view_codes = attributeValues(teacherGrid, "data-code");
  out.teacher_view_meta = (teacherGrid.match(/class="card-meta">([^<]*)</g) || [])
    .map((m) => m.match(/>([^<]*)</)[1].trim());
  sandbox.renderTeacherPanel();
  const panel = sandbox.document.nodes["teacher-panel"];
  out.teacher_panel_hidden = panel.hidden;
  out.teacher_panel = panel.innerHTML.replace(/\s+/g, " ").trim();

  sandbox = load(acrossDepartments);
  sandbox.renderTeacherPanel();
  out.panel_hidden_in_department_view = sandbox.document.nodes["teacher-panel"].hidden;

  sandbox = load({
    placements: [placement("X1", '<script>"x"', 1, ["月1"])],
    unplaced: [], intensive: [], violations: [],
  });
  sandbox.renderGrid();
  const dangerous = sandbox.document.nodes["timetable-grid"].innerHTML;
  out.escaped_has_raw_tag = dangerous.includes("<script>");
  out.escaped_has_raw_quote = /data-code="[^"]*"[^>]*"x"/.test(dangerous);
  const nameAt = dangerous.indexOf('class="card-name"');
  out.escaped_sample = dangerous.slice(nameAt, nameAt + 80);

  out.print_sheets = printCase();

  return out;
}

console.log(JSON.stringify(run()));
