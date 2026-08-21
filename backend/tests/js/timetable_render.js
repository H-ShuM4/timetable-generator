// timetable.js の描画とコマ計算。ご要望で入れた挙動が壊れていないか見る。
//   - 各コマの中を 1年→2年→3年→4年 の順に並べる
//   - 掴んだ位置を基準にした複数コマの移動
//   - 未配置科目を落としたときのコマ組み立て（▲科目は連続 2 コマ）
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const { createDocument, attributeValues } = require("./dom_stub.js");
const JS_DIR = path.join(__dirname, "..", "..", "..", "frontend", "js");

function load(result) {
  const document = createDocument();
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

  return out;
}

console.log(JSON.stringify(run()));
