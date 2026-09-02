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

  const axis = currentView === "department"
    ? `<div class="group">
         ${departments.map((d) => `
           <button class="dept-tab${d === currentDepartment ? " active" : ""}"
                   data-dept="${d}">${escapeHtml(d)}</button>`).join("")}
       </div>`
    : `<div class="group">
         <label class="teacher-pick">
           <span>教員</span>
           <select id="teacher-select">
             ${teachers.map((name) => `
               <option value="${escapeHtml(name)}"${name === currentTeacher ? " selected" : ""}>
                 ${escapeHtml(name)}</option>`).join("")}
           </select>
         </label>
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
      <span class="card-name">${escapeHtml(placement.name)}</span>
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

function renderGrid() {
  const violating = violatingCodes();
  const byTeacher = currentView === "teacher";
  const visible = visiblePlacements();

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

  document.getElementById("timetable-grid").innerHTML = `
    <table class="timetable">
      <thead><tr><th></th>${DAYS.map((d) => `<th>${d}</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  attachDragHandlers();
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
  document.getElementById("export-button").addEventListener("click", () => {
    if (!window.appState.sessionId) return;
    window.location.href = api.exportUrl(window.appState.sessionId);
  });
}
