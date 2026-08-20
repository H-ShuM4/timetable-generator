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
    <div>
      ${departments.map((d) => `
        <button class="dept-tab${d === currentDepartment ? " active" : ""}"
                data-dept="${d}">${d}</button>`).join("")}
    </div>
    <div>
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

function cardHtml(placement, grabbedLabel, isViolating) {
  const quarter = placement.quarter ? `[${escapeHtml(placement.quarter)}]` : "";
  const source = escapeHtml(placement.source);
  const sourceLabel = escapeHtml(SOURCE_LABELS[placement.source] || placement.source);
  return `
    <div class="card source-${source}${isViolating ? " violating" : ""}"
         draggable="true"
         data-code="${escapeHtml(placement.code)}"
         data-grabbed="${escapeHtml(grabbedLabel)}"
         title="${sourceLabel}">
      <strong>${escapeHtml(placement.name)}${quarter}</strong><br>
      ${escapeHtml(placement.teacher)}<br>
      ${escapeHtml(String(placement.year))}年・${escapeHtml(placement.category)}
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
    return `<tr><th>${period}限</th>${cells}</tr>`;
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

function renderSide() {
  document.getElementById("unplaced-list").innerHTML =
    resultData.unplaced.map((s) => `<li>${describeSubjectRef(s)}</li>`).join("") || "<li>なし</li>";
  document.getElementById("intensive-list").innerHTML =
    resultData.intensive.map((s) => `<li>${describeSubjectRef(s)}</li>`).join("") || "<li>なし</li>";
  document.getElementById("violation-list").innerHTML =
    resultData.violations
      .map((v) => `<li class="log-ERROR">[${escapeHtml(v.rule_id)}] ${escapeHtml(v.message)}</li>`)
      .join("") || "<li>違反はありません</li>";
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

async function moveCard(code, grabbedLabel, targetLabel) {
  const placement = resultData.placements.find((p) => p.code === code);
  if (!placement) return;

  const slots = shiftedSlots(placement, grabbedLabel, targetLabel);
  if (slots.some((slot) => slot === null)) {
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
