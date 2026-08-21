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
let currentDepartment = "経営";
let currentTerm = "前期";

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

function renderTabs() {
  const departments = ["経営", "会計", "短期大学部"];
  const terms = ["前期", "後期"];
  document.getElementById("result-tabs").innerHTML = `
    <div class="group">
      ${departments.map((d) => `
        <button class="dept-tab${d === currentDepartment ? " active" : ""}"
                data-dept="${d}">${d}</button>`).join("")}
    </div>
    <div class="group">
      ${terms.map((t) => `
        <button class="term-tab${t === currentTerm ? " active" : ""}"
                data-term="${t}">${t}</button>`).join("")}
    </div>`;

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
}

// 前①・後① は学期の前半、前②・後② は後半に開講する。カード左端の
// レールをその半分だけ塗ることで、文字で [後①] と書かなくても
// 「学期のどこで開くか」が形で分かる。
const QUARTER_HALVES = { "前①": "first", "後①": "first", "前②": "second", "後②": "second" };

function cardHtml(placement, grabbedLabel, isViolating) {
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
      <span class="card-meta">${escapeHtml(placement.teacher)}・${escapeHtml(placement.category)}</span>
    </div>`;
}

function renderGrid() {
  const violating = violatingCodes();
  const visible = resultData.placements.filter(
    (p) => p.department === currentDepartment && p.term === currentTerm
  );

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
        .map((p) => cardHtml(p, label, violating.has(p.code)))
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

  setCount("count-unplaced", resultData.unplaced.length);
  setCount("count-intensive", resultData.intensive.length);
  setCount("count-violations", resultData.violations.length, true);
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
  if (resultData.status !== "done") {
    document.getElementById("timetable-grid").innerHTML = "<p>まだ生成が完了していません。</p>";
    return;
  }
  renderTabs();
  renderGrid();
  renderSide();
}

function initTimetable() {
  document.getElementById("export-button").addEventListener("click", () => {
    if (!window.appState.sessionId) return;
    window.location.href = api.exportUrl(window.appState.sessionId);
  });
}
