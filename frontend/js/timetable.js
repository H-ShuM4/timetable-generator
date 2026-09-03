"use strict";

const DAYS = ["月", "火", "水", "木", "金"];
const PERIODS = [1, 2, 3, 4, 5];
const SOURCE_LABELS = {
  prelock: "事前ロック",
  gemini: "AI 配置",
  solver: "ソルバー補完",
  manual: "手動編集",
  inherited: "前年度踏襲",
};

let resultData = null;

// 取り消しの履歴。1 件は「その操作の直前に、どの科目がどのコマにいたか」。
// 合同科目と前後期の対応科目は一緒に動くため、画面側は掴んだ 1 件しか
// 知らない。何を戻せばよいかはサーバが move の応答で教えてくれる。
let undoStack = [];
const UNDO_LIMIT = 50;
let currentDepartment = "経営";
let currentTerm = "前期";
// 学科別か教員別か。教員は 82 名中 56 名が 3 学科以上にまたがるため、
// 学科のビューを渡り歩かないと 1 人の週の予定が分からなかった。
let currentView = "department";
let currentTeacher = null;
// 教員別の絞り込み文字列。実データの教員は 99 名で、プルダウンだけでは
// 目当ての先生まで延々スクロールすることになる。
let teacherFilter = "";

function parseSlot(label) {
  return { day: label.slice(0, 1), period: Number(label.slice(1)) };
}

function violatingCodes() {
  if (!resultData) return new Set();
  const codes = new Set();
  resultData.violations.forEach((violation) => {
    codes.add(violation.subject_code);
    if (violation.related_code) codes.add(violation.related_code);
  });
  return codes;
}

function matchesTeacher(name, query) {
  if (!query) return true;
  // 氏名は Excel 由来で姓名の間の空白が全角・半角で揺れる。両方落として比べる。
  const flat = (value) => String(value).replace(/[\s　]/g, "");
  return flat(name).includes(flat(query));
}

function teacherOptionsHtml(teachers) {
  return teachers
    .map((name) => `
      <option value="${escapeHtml(name)}"${name === currentTeacher ? " selected" : ""}>
        ${escapeHtml(name)}</option>`)
    .join("");
}

/** 絞り込みだけを描き直す。入力欄そのものは触らないので、打鍵で focus が飛ばない。 */
function applyTeacherFilter() {
  const matched = teachersWithClasses().filter((n) => matchesTeacher(n, teacherFilter));
  const select = document.getElementById("teacher-select");
  if (!select) return matched;

  if (matched.length && !matched.includes(currentTeacher)) {
    currentTeacher = matched[0];
  }
  select.innerHTML = teacherOptionsHtml(matched);
  // 該当が無いことは、選べる項目が無いことで伝わる。件数は出さない。
  select.disabled = matched.length === 0;
  return matched;
}

function teachersWithClasses() {
  const counts = new Map();
  resultData.placements.forEach((p) => {
    counts.set(p.teacher, (counts.get(p.teacher) || 0) + p.slots.length);
  });
  return [...counts.keys()].sort((a, b) => a.localeCompare(b, "ja"));
}

function renderTabs() {
  const departments = ["経営", "会計", "短期大学部"];
  const terms = ["前期", "後期"];
  const teachers = teachersWithClasses();
  if (currentView === "teacher" && !teachers.includes(currentTeacher)) {
    currentTeacher = teachers[0] || null;
  }
  const visible = teachers.filter((name) => matchesTeacher(name, teacherFilter));
  if (currentView === "teacher" && visible.length && !visible.includes(currentTeacher)) {
    currentTeacher = visible[0];
  }

  const axis = currentView === "department"
    ? `<div class="group">
         ${departments.map((d) => `
           <button class="dept-tab${d === currentDepartment ? " active" : ""}"
                   data-dept="${d}">${escapeHtml(d)}</button>`).join("")}
       </div>`
    : `<div class="group teacher-pick">
         <input type="search" id="teacher-search" placeholder="氏名で絞り込む"
                value="${escapeHtml(teacherFilter)}" autocomplete="off">
         <select id="teacher-select">${teacherOptionsHtml(visible)}</select>
       </div>`;

  document.getElementById("result-tabs").innerHTML = `
    <div class="group view-switch">
      <button class="view-tab${currentView === "department" ? " active" : ""}"
              data-view-mode="department">学科別</button>
      <button class="view-tab${currentView === "teacher" ? " active" : ""}"
              data-view-mode="teacher">教員別</button>
    </div>
    ${axis}
    <div class="group">
      ${terms.map((t) => `
        <button class="term-tab${t === currentTerm ? " active" : ""}"
                data-term="${t}">${t}</button>`).join("")}
    </div>`;

  document.querySelectorAll(".view-tab").forEach((button) => {
    button.addEventListener("click", () => {
      currentView = button.dataset.viewMode;
      renderTimetable();
    });
  });
  document.querySelectorAll(".dept-tab").forEach((button) => {
    button.addEventListener("click", () => {
      currentDepartment = button.dataset.dept;
      renderTimetable();
    });
  });
  document.querySelectorAll(".term-tab").forEach((button) => {
    button.addEventListener("click", () => {
      currentTerm = button.dataset.term;
      renderTimetable();
    });
  });
  const picker = document.getElementById("teacher-select");
  if (picker) {
    picker.addEventListener("change", () => {
      currentTeacher = picker.value;
      renderTimetable();
    });
  }

  const search = document.getElementById("teacher-search");
  if (search) {
    // 打鍵ごとに選択肢と件数だけを差し替える。表そのものは Enter か
    // プルダウンの選択で描き直す。1 文字ごとに 600 枚を描き直さない。
    search.addEventListener("input", () => {
      teacherFilter = search.value;
      applyTeacherFilter();
    });
    search.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      if (applyTeacherFilter().length) renderTimetable();
    });
  }
  if (currentView === "teacher") applyTeacherFilter();
}

// 前①・後① は学期の前半、前②・後② は後半に開講する。カード左端の
// レールをその半分だけ塗ることで、文字で [後①] と書かなくても
// 「学期のどこで開くか」が形で分かる。
const QUARTER_HALVES = { "前①": "first", "後①": "first", "前②": "second", "後②": "second" };

function cardHtml(placement, grabbedLabel, isViolating, showDepartment) {
  const source = escapeHtml(placement.source);
  const half = QUARTER_HALVES[placement.quarter];
  const sourceLabel = SOURCE_LABELS[placement.source] || placement.source;
  // レールは形だけなので、同じ内容を title に言葉で持たせる
  const title = escapeHtml(
    placement.quarter ? `${sourceLabel}・${placement.quarter}` : sourceLabel
  );
  return `
    <div class="card source-${source}${half ? ` quarter-${half}` : ""}${isViolating ? " violating" : ""}"
         draggable="true"
         data-code="${escapeHtml(placement.code)}"
         data-grabbed="${escapeHtml(grabbedLabel)}"
         title="${title}">
      <span class="card-rail" aria-hidden="true"></span>
      <span class="card-year y${escapeHtml(String(placement.year))}">${escapeHtml(String(placement.year))}年</span>
      <span class="card-name"
            data-teacher="${escapeHtml(placement.teacher)}">${escapeHtml(placement.name)}</span>
      <span class="card-meta">${escapeHtml(
        showDepartment ? placement.department : placement.teacher
      )}・${escapeHtml(placement.category)}</span>
    </div>`;
}

function visiblePlacements() {
  // 教員別では学科をまたいで集める。学科別では担当教員をまたいで集める。
  return resultData.placements.filter((p) =>
    p.term === currentTerm
    && (currentView === "teacher"
      ? p.teacher === currentTeacher
      : p.department === currentDepartment)
  );
}

// 表そのものを組む。書き込み先を知らないので、画面のグリッドと印刷用の
// シートが同じ 1 本を通る。片方だけ直すと、刷った紙と画面が食い違う。
function gridMarkup(visible, byTeacher) {
  const violating = violatingCodes();

  const rows = PERIODS.map((period) => {
    const cells = DAYS.map((day) => {
      const label = `${day}${period}`;
      // 各コマの中は 1年→2年→3年→4年 の順に並べる。同じ年次の中は
      // 科目名、さらに授業コードで並べ、コマを移動しても順序が動かない
      // ようにする（renderTimetable がサーバから取り直して再描画する）。
      const cards = visible
        .filter((p) => p.slots.includes(label))
        .sort((a, b) =>
          a.year - b.year ||
          a.name.localeCompare(b.name, "ja") ||
          a.code.localeCompare(b.code)
        )
        .map((p) => cardHtml(p, label, violating.has(p.code), byTeacher))
        .join("");
      return `<td data-slot="${label}">${cards}</td>`;
    }).join("");
    return `<tr>
      <th><span class="period-number">${period}</span><span class="period-unit">限</span></th>
      ${cells}</tr>`;
  }).join("");

  return `
    <table class="timetable">
      <thead><tr><th></th>${DAYS.map((d) => `<th>${d}</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderGrid() {
  document.getElementById("timetable-grid").innerHTML =
    gridMarkup(visiblePlacements(), currentView === "teacher");
  attachDragHandlers();
}

// ---------------------------------------------------------------- 印刷

const PRINT_DEPARTMENTS = ["経営", "会計", "短期大学部"];
const PRINT_TERMS = ["前期", "後期"];

// 用紙ごとの描画領域（余白 10mm を引いた mm を 96dpi の CSS px に直したもの）。
// 何ページに分かれるかを、印刷ダイアログを開く前に測るのに使う。
const PAPERS = {
  a4: { label: "A4 横", css: "A4 landscape", width: 1047, height: 718 },
  a3: { label: "A3 横", css: "A3 landscape", width: 1512, height: 1047 },
};

function placementsIn(department, term) {
  return resultData.placements.filter(
    (p) => p.department === department && p.term === term
  );
}

function printSheet(heading, body) {
  return `<section class="print-sheet">
    <h3 class="print-heading">${escapeHtml(heading)}</h3>
    ${body}
  </section>`;
}

function intensiveSheet() {
  return printSheet("集中講義",
    `<ul class="print-list">${
      resultData.intensive.map((s) => `<li>${describeSubjectRef(s)}</li>`).join("")
      || "<li>なし</li>"
    }</ul>`);
}

/** 学科 × 学期で 1 枚ずつ。事務局が全体を見渡すときの揃い。 */
function buildTermSheets() {
  return PRINT_DEPARTMENTS.flatMap((department) =>
    PRINT_TERMS.map((term) => printSheet(
      `${department}・${term}`,
      gridMarkup(placementsIn(department, term), false)
    ))
  ).join("") + intensiveSheet();
}

/** 学科ごとに 1 枚。前期と後期を左右に並べ、年間の流れを 1 枚で見せる。 */
function buildDepartmentSheets() {
  return PRINT_DEPARTMENTS.map((department) => printSheet(
    department,
    `<div class="print-pair">${
      PRINT_TERMS.map((term) => `
        <div class="print-half">
          <h4 class="print-subheading">${escapeHtml(term)}</h4>
          ${gridMarkup(placementsIn(department, term), false)}
        </div>`).join("")
    }</div>`
  )).join("") + intensiveSheet();
}

const SHEET_BUILDERS = { term: buildTermSheets, department: buildDepartmentSheets };

// 画面の見やすさ（レールの色・年次の濃淡・BIZ UD 書体）をそのまま紙へ
// 持っていくため、PDF はブラウザの印刷で出す。同じ CSS・同じ書体で描かれる
// ので見た目が一致し、追加のライブラリも要らない。事務局の PC がオフライン
// でも確実に動く。
function buildPrintSheets(unit, compact) {
  if (!resultData) return;
  const stamped = new Date().toLocaleString("ja-JP", {
    year: "numeric", month: "long", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
  const box = document.getElementById("print-sheets");
  box.className = compact ? "compact" : "";
  box.innerHTML =
    `<p class="print-stamp">時間割自動生成システム　${escapeHtml(stamped)} 出力</p>`
    + (SHEET_BUILDERS[unit] || buildTermSheets)();
}

function clearPrintSheets() {
  // 613 件ぶんのカードを抱えたままにしない。
  const box = document.getElementById("print-sheets");
  box.innerHTML = "";
  box.className = "";
}

/** 選ばれた用紙を @page へ当てる。クラスでは切り替えられない。 */
function applyPaper(paper) {
  const size = (PAPERS[paper] || PAPERS.a3).css;
  document.getElementById("print-page-size").textContent =
    `@page { size: ${size}; margin: 10mm; }`;
}

/**
 * 組んだシートを印刷幅で測り、1 枚に収まらないものを返す。
 *
 * 印刷ダイアログを開くまで何ページになるか分からないと、A4 を選んで
 * 割れていることに刷ってから気づく。測ってから出す。
 */
function oversizedSheets(paper) {
  const page = PAPERS[paper] || PAPERS.a3;
  const box = document.getElementById("print-sheets");
  const keep = box.style.cssText;
  box.style.cssText =
    `display:block;position:absolute;left:-10000px;top:0;width:${page.width}px`;
  const over = [...box.querySelectorAll(".print-sheet")]
    .map((sheet) => ({
      heading: sheet.querySelector(".print-heading").textContent.trim(),
      pages: Math.ceil(sheet.getBoundingClientRect().height / page.height),
    }))
    .filter((row) => row.pages > 1);
  box.style.cssText = keep;
  return over;
}

function describeSubjectRef(subject) {
  return `${escapeHtml(subject.code)} ${escapeHtml(subject.name)}`
    + `（${escapeHtml(subject.teacher)}・${escapeHtml(subject.department)}・`
    + `${escapeHtml(String(subject.year))}年・${escapeHtml(subject.term)}・`
    + `${escapeHtml(subject.category)}）`;
}

function setCount(id, value, alert) {
  const element = document.getElementById(id);
  element.textContent = String(value);
  element.classList.toggle("alert", Boolean(alert) && value > 0);
}

const DAYS_ORDER = ["月", "火", "水", "木", "金"];

function renderTeacherPanel() {
  const panel = document.getElementById("teacher-panel");
  if (currentView !== "teacher" || !currentTeacher) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;

  const mine = resultData.placements.filter((p) => p.teacher === currentTeacher);
  const thisTerm = mine.filter((p) => p.term === currentTerm);
  const perDay = DAYS_ORDER.map((day) => ({
    day,
    count: thisTerm.reduce(
      (total, p) => total + p.slots.filter((s) => s.startsWith(day)).length, 0
    ),
  }));
  const info = (resultData.teachers || []).find((t) => t.name === currentTeacher);
  const facts = [`<span class="tally">区分 <b>${escapeHtml(info ? info.kind : "不明")}</b></span>`];
  if (info && info.research_day) {
    facts.push(`<span class="tally">研究日 <b>${escapeHtml(info.research_day)}</b></span>`);
  }
  if (info && info.available_slots.length) {
    facts.push(`<span class="tally">出勤可能 <b>${info.available_slots.length}</b> コマ</span>`);
  }

  panel.innerHTML = `
    <div class="teacher-head">
      <span class="teacher-name">${escapeHtml(currentTeacher)}</span>
      ${facts.join("")}
    </div>
    <div class="teacher-load">
      <span class="tally">${escapeHtml(currentTerm)} <b>${thisTerm.length}</b> コマ</span>
      <span class="tally">通年 <b>${mine.length}</b> コマ</span>
      ${perDay.map(({ day, count }) => `
        <span class="day-load${count === 0 ? " empty" : ""}">
          ${day}<b>${count}</b></span>`).join("")}
    </div>`;
}

function renderSide() {
  // 未配置科目もドラッグで置けるようにする。置く手段が画面に無いと、
  // 制約の都合で自動配置できなかった科目に事務局が手出しできない。
  document.getElementById("unplaced-list").innerHTML =
    resultData.unplaced
      .map((s) => `<li class="unplaced-card" draggable="true" data-code="${escapeHtml(s.code)}">`
        + `${describeSubjectRef(s)}</li>`)
      .join("") || "<li>なし</li>";
  document.getElementById("intensive-list").innerHTML =
    resultData.intensive.map((s) => `<li>${describeSubjectRef(s)}</li>`).join("") || "<li>なし</li>";
  document.getElementById("violation-list").innerHTML =
    resultData.violations
      .map((v) => `<li>[${escapeHtml(v.rule_id)}] ${escapeHtml(v.message)}</li>`)
      .join("") || "<li>違反はありません</li>";

  renderInheritSkipped();

  // 未配置は「あれば手を打つ」もの。0 件のときに場所を取らせない。
  document.getElementById("block-unplaced").open = resultData.unplaced.length > 0;

  setCount("count-unplaced", resultData.unplaced.length);
  setCount("count-intensive", resultData.intensive.length);
  setCount("count-violations", resultData.violations.length, true);
}

function renderInheritSkipped() {
  // 踏襲モード以外では空なので、丸ごと隠す。
  const skipped = resultData.inherit_skipped || [];
  const block = document.getElementById("block-inherit-skipped");
  if (!block) return;
  block.hidden = skipped.length === 0;
  if (!skipped.length) return;

  document.getElementById("inherit-skipped-list").innerHTML = skipped
    .map((entry) => {
      const partner = entry.related
        ? `（相手: ${escapeHtml(entry.related.name)}）`
        : "";
      return `<li>[${escapeHtml(entry.rule_id)}] ${describeSubjectRef(entry.subject)}`
        + `<span class="skip-reason">${escapeHtml(entry.message)}${partner}</span></li>`;
    })
    .join("");
  // 朱は制約違反だけに使う。踏襲できなかったのは違反ではない。
  setCount("count-inherit-skipped", skipped.length);
}

function attachDragHandlers() {
  document.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", JSON.stringify({
        code: card.dataset.code,
        grabbed: card.dataset.grabbed,
      }));
    });
  });

  document.querySelectorAll(".unplaced-card").forEach((item) => {
    item.addEventListener("dragstart", (event) => {
      // grabbed が無いものを未配置として扱う
      event.dataTransfer.setData("text/plain", JSON.stringify({ code: item.dataset.code }));
    });
  });

  document.querySelectorAll("#timetable-grid td").forEach((cell) => {
    cell.addEventListener("dragover", (event) => {
      event.preventDefault();
      cell.classList.add("dragover");
    });
    cell.addEventListener("dragleave", () => cell.classList.remove("dragover"));
    cell.addEventListener("drop", async (event) => {
      event.preventDefault();
      cell.classList.remove("dragover");
      const payload = JSON.parse(event.dataTransfer.getData("text/plain"));
      await moveCard(payload.code, payload.grabbed, cell.dataset.slot);
    });
  });
}

function shiftedSlots(placement, grabbedLabel, targetLabel) {
  const grabbed = parseSlot(grabbedLabel);
  const target = parseSlot(targetLabel);
  const dayIndex = DAYS.indexOf(target.day) - DAYS.indexOf(grabbed.day);
  const periodShift = target.period - grabbed.period;

  return placement.slots.map((label) => {
    const slot = parseSlot(label);
    const day = DAYS[DAYS.indexOf(slot.day) + dayIndex];
    const period = slot.period + periodShift;
    return day && period >= 1 && period <= 5 ? `${day}${period}` : null;
  });
}

function slotsFromScratch(subject, targetLabel) {
  // 未配置科目には掴んだ位置が無いので、必要コマ数から組み立てる。
  // ▲科目は同一日の連続 2 コマ（H10）なので、落とした位置を先頭にする。
  const target = parseSlot(targetLabel);
  const count = subject.slots_required || 1;
  const slots = [];
  for (let offset = 0; offset < count; offset += 1) {
    const period = target.period + offset;
    if (period > 5) return null;
    slots.push(`${target.day}${period}`);
  }
  return slots;
}

function rememberForUndo(previous) {
  if (!previous || !previous.length) return;
  undoStack.push(previous);
  if (undoStack.length > UNDO_LIMIT) undoStack.shift();
  updateUndoButton();
}

function updateUndoButton() {
  const button = document.getElementById("undo-button");
  if (!button) return;
  button.disabled = undoStack.length === 0;
  button.title = undoStack.length
    ? `直前の移動を取り消します（あと ${undoStack.length} 回）`
    : "取り消せる移動はありません";
}

async function undoLastMove() {
  const previous = undoStack.pop();
  updateUndoButton();
  if (!previous) return;

  // まず元のコマへ戻す。1 件戻せば、同じコマに入る仲間もついてくる。
  const placed = previous.find((entry) => entry.slots.length);
  try {
    if (placed) {
      const body = await api.moveSubject(
        window.appState.sessionId, placed.code, placed.slots
      );
      if (!body.applied) {
        window.alert("元の位置へ戻せませんでした。手で戻してください。");
        return;
      }
    }
    // 元は未配置だったものを未配置へ返す
    for (const entry of previous) {
      if (!entry.slots.length) {
        await api.unplaceSubject(window.appState.sessionId, entry.code);
      }
    }
    await renderTimetable();
  } catch (error) {
    window.alert(`取り消しに失敗しました: ${error.message}`);
  }
}

async function moveCard(code, grabbedLabel, targetLabel) {
  const placement = resultData.placements.find((p) => p.code === code);
  const unplaced = resultData.unplaced.find((s) => s.code === code);
  if (!placement && !unplaced) return;

  const slots = placement
    ? shiftedSlots(placement, grabbedLabel, targetLabel)
    : slotsFromScratch(unplaced, targetLabel);
  if (slots === null || slots.some((slot) => slot === null)) {
    window.alert("移動先が時間割の範囲外です");
    return;
  }

  try {
    const body = await api.moveSubject(window.appState.sessionId, code, slots);
    if (!body.applied) {
      const reasons = body.violations
        .map((v) => `[${v.rule_id}] ${v.message}`).join("\n");
      window.alert(`この位置には配置できません:\n${reasons}`);
      return;
    }
    rememberForUndo(body.previous);
    await renderTimetable();
  } catch (error) {
    window.alert(`移動に失敗しました: ${error.message}`);
  }
}

async function renderTimetable() {
  if (!window.appState.sessionId) return;
  try {
    resultData = await api.getResult(window.appState.sessionId);
  } catch (error) {
    document.getElementById("timetable-grid").innerHTML =
      `<p class="log-ERROR">結果の取得に失敗しました: ${escapeHtml(error.message)}</p>`;
    return;
  }
  if (resultData.status === "failed") {
    document.getElementById("timetable-grid").innerHTML =
      `<p class="log-ERROR">生成に失敗しました: ${escapeHtml(resultData.error || "不明なエラー")}</p>`;
    return;
  }
  if (resultData.status === "cancelled") {
    document.getElementById("timetable-grid").innerHTML =
      "<p>生成を中止しました。「② 生成」からやり直してください。</p>";
    return;
  }
  if (resultData.status !== "done") {
    document.getElementById("timetable-grid").innerHTML = "<p>まだ生成が完了していません。</p>";
    return;
  }
  renderTabs();
  renderTeacherPanel();
  renderGrid();
  renderSide();
  refreshExportOptions();
}

function initTimetable() {
  document.getElementById("undo-button").addEventListener("click", undoLastMove);
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "z") {
      // 結果画面を開いているときだけ効かせる
      if (!document.getElementById("view-result").classList.contains("active")) return;
      event.preventDefault();
      undoLastMove();
    }
  });
  document.getElementById("export-button").addEventListener("click", exportResult);
  // 印刷が終わったら（保存でも取り消しでも）組んだシートを捨てる。
  window.addEventListener("afterprint", clearPrintSheets);

  EXPORT_CONTROLS.forEach((id) => {
    const control = document.getElementById(id);
    control.value = readExportSetting(id, control.value);
    control.addEventListener("change", () => {
      saveExportSetting(id, control.value);
      refreshExportOptions();
    });
  });
  refreshExportOptions();
}

const EXPORT_CONTROLS = [
  "export-format", "export-unit", "export-paper", "export-density",
];
const EXPORT_KEY = "timetable.export";

function readExportSetting(id, fallback) {
  try {
    return (JSON.parse(window.localStorage.getItem(EXPORT_KEY)) || {})[id] || fallback;
  } catch (error) {
    return fallback;
  }
}

function saveExportSetting(id, value) {
  try {
    const saved = JSON.parse(window.localStorage.getItem(EXPORT_KEY)) || {};
    saved[id] = value;
    window.localStorage.setItem(EXPORT_KEY, JSON.stringify(saved));
  } catch (error) {
    // 保存できなくても出力はできる
  }
}

function exportSettings() {
  return {
    format: document.getElementById("export-format").value,
    unit: document.getElementById("export-unit").value,
    paper: document.getElementById("export-paper").value,
    compact: document.getElementById("export-density").value === "compact",
  };
}

/** PDF のときだけ選択肢を出し、何ページに分かれるかを先に測って伝える。 */
function refreshExportOptions() {
  const settings = exportSettings();
  const options = document.getElementById("export-options");
  options.hidden = settings.format !== "pdf";
  if (options.hidden || !resultData) return;

  buildPrintSheets(settings.unit, settings.compact);
  const over = oversizedSheets(settings.paper);
  clearPrintSheets();

  const note = document.getElementById("export-note");
  const paper = (PAPERS[settings.paper] || PAPERS.a3).label;
  note.textContent = over.length
    ? `${paper}では ${over.map((row) => `${row.heading}（${row.pages} ページ）`).join("、")}`
      + " が 1 枚に収まりません。用紙か詰め方を変えると 1 枚にできます。"
    : `${paper}で、どの区分も 1 枚に収まります。`;
  note.classList.toggle("warn", over.length > 0);
}

function exportResult() {
  if (!window.appState.sessionId) return;
  const settings = exportSettings();

  if (settings.format === "pdf") {
    // 印刷ダイアログで「PDF として保存」を選んでもらう。画面と同じ CSS で
    // 描かれるので、レールの色も年次の濃淡もそのまま紙に載る。
    buildPrintSheets(settings.unit, settings.compact);
    applyPaper(settings.paper);
    window.print();
    return;
  }
  window.location.href = api.exportUrl(window.appState.sessionId);
}
