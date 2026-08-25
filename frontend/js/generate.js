"use strict";

let retargetItems = [];

function selectedMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function renderRetargetList() {
  const container = document.getElementById("retarget-list");
  if (!retargetItems.length) {
    container.innerHTML = "<p>組み替え対象はありません。前年度ファイルを読み込んでください。</p>";
    return;
  }
  container.innerHTML = retargetItems
    .map((item) => `
      <label class="field">
        <input type="checkbox" value="${escapeHtml(item.code)}" checked>
        ${escapeHtml(item.code)} ${escapeHtml(item.name)}（${escapeHtml(item.teacher)}） — ${escapeHtml(item.reason)}
      </label>`)
    .join("");
}

async function onEnterGenerateView() {
  const isInherit = selectedMode() === "inherit";
  document.getElementById("retarget-panel").hidden = !isInherit;
  if (!isInherit || !window.appState.sessionId) return;

  try {
    retargetItems = await api.getRetarget(window.appState.sessionId);
    renderRetargetList();
  } catch (error) {
    document.getElementById("retarget-list").innerHTML =
      `<p class="log-ERROR">組み替え対象の取得に失敗しました: ${escapeHtml(error.message)}</p>`;
  }
}

const MODE_LABELS = {
  mock: "モック",
  optimize: "AI",
  inherit: "踏襲",
};

// 生成画面のスライダー。左から順に 0・1・2 で、値は API へ渡す語に直す。
const WEIGHT_STEPS = ["off", "normal", "high"];
const WEIGHT_LABELS = ["気にしない", "標準", "重視"];
const EFFORT_STEPS = ["off", "short", "long"];
const EFFORT_LABELS = ["しない", "短く（5 秒まで）", "じっくり（1 分まで）"];

const PARAMS = [
  { key: "student_gaps", label: "学生の空きコマを減らす",
    hint: "授業間の空き時間を減らし、なるべく連続して授業を受けられるように配置します。" },
  { key: "student_days", label: "学生の登校日数を減らす",
    hint: "授業を特定の曜日に集中させ、週の登校日数を減らします（※1日あたりの授業数は増えます）。" },
  { key: "teacher_gaps", label: "教員の空きコマを減らす",
    hint: "教員の授業と授業の間の空き時間をなるべく減らします。" },
  { key: "early_periods", label: "1〜4 限に集約する",
    hint: "教職課程（4・5限）との衝突を防ぐため、通常科目をなるべく1〜4限に優先配置します。" },
  { key: "seminar_adjacency", label: "ゼミを隣り合わせる",
    hint: "3年生（課題研究）と4年生（卒業研究）が交流できるよう、2つのゼミを連続した時限に配置します。" },
];

const PARAM_KEY = "timetable.params";

function readParams() {
  try {
    return JSON.parse(window.localStorage.getItem(PARAM_KEY)) || {};
  } catch (error) {
    return {};
  }
}

function saveParams(values) {
  try {
    window.localStorage.setItem(PARAM_KEY, JSON.stringify(values));
  } catch (error) {
    // 保存できなくても生成はできる
  }
}

function paramValues() {
  const values = {};
  document.querySelectorAll("#param-list input[type=range]").forEach((input) => {
    values[input.dataset.key] = Number(input.value);
  });
  return values;
}

function renderParams() {
  const saved = readParams();
  const rows = PARAMS.map((item) => {
    const value = Number.isInteger(saved[item.key]) ? saved[item.key] : 1;
    return `
      <div class="param">
        <label for="param-${item.key}">${escapeHtml(item.label)}</label>
        <input type="range" id="param-${item.key}" data-key="${item.key}"
               min="0" max="2" step="1" value="${value}">
        <span class="param-value" data-for="${item.key}">${WEIGHT_LABELS[value]}</span>
        <p class="hint param-hint">${escapeHtml(item.hint)}</p>
      </div>`;
  });
  const effort = Number.isInteger(saved.repair_effort) ? saved.repair_effort : 0;
  rows.push(`
    <div class="param param-effort">
      <label for="param-repair">見直しにかける時間</label>
      <input type="range" id="param-repair" data-key="repair_effort"
             min="0" max="2" step="1" value="${effort}">
      <span class="param-value" data-for="repair_effort">${EFFORT_LABELS[effort]}</span>
      <p class="hint param-hint">
        上記の設定を反映させるには「短く」以上を選択してください。「しない」の場合は設定が適用されません。
      </p>
    </div>`);
  document.getElementById("param-list").innerHTML = rows.join("");

  document.querySelectorAll("#param-list input[type=range]").forEach((input) => {
    input.addEventListener("input", () => {
      const key = input.dataset.key;
      const labels = key === "repair_effort" ? EFFORT_LABELS : WEIGHT_LABELS;
      document.querySelector(`.param-value[data-for="${key}"]`).textContent =
        labels[Number(input.value)];
      saveParams(paramValues());
    });
  });
}

function selectedWeights() {
  const values = paramValues();
  const weights = {};
  PARAMS.forEach((item) => { weights[item.key] = WEIGHT_STEPS[values[item.key] || 0]; });
  return weights;
}

function selectedEffort() {
  return EFFORT_STEPS[paramValues().repair_effort || 0];
}

function checkedRetargetCodes() {
  return Array.from(
    document.querySelectorAll("#retarget-list input:checked")
  ).map((input) => input.value);
}

function setStatus(message, isError) {
  const element = document.getElementById("generate-status");
  element.textContent = message;
  element.className = isError ? "log-ERROR" : "";
}

async function startGeneration() {
  const sessionId = window.appState.sessionId;
  if (!sessionId) {
    setStatus("先にファイルを読み込んでください", true);
    return;
  }

  const button = document.getElementById("generate-button");
  button.disabled = true;
  clearLog();
  openLogPanel();
  setStatus("生成中です…");

  try {
    const body = await api.startGeneration(
      sessionId, selectedMode(), checkedRetargetCodes(),
      selectedWeights(), selectedEffort()
    );
    if (body.mode !== selectedMode()) {
      const label = MODE_LABELS[body.mode] || body.mode;
      setStatus(`API キーが未設定のため ${label} モードで実行します`);
    }
    connectLogStream(sessionId, async (finished) => {
      button.disabled = false;
      if (!finished) {
        setStatus("ログ配信が切断されました。結果タブで状態を確認してください", true);
        return;
      }
      const result = await api.getResult(sessionId);
      if (result.status === "failed") {
        setStatus(`生成に失敗しました: ${result.error || "不明なエラー"}`, true);
        return;
      }
      setStatus(
        `完了: 配置 ${result.placements.length} 件 / ` +
        `未配置 ${result.unplaced.length} 件 / 違反 ${result.violations.length} 件`
      );
      document.querySelector('#tabs button[data-view="result"]').disabled = false;

      // 生成が終わったら結果を見せる。ログは畳んで画面を広く使う。
      // 失敗・切断のときは上で return しているので、ここへは来ない。
      collapseLogPanel();
      switchView("result");
    });
  } catch (error) {
    button.disabled = false;
    setStatus(`生成を開始できませんでした: ${error.message}`, true);
  }
}

function initGenerate() {
  renderParams();
  document.getElementById("generate-button").addEventListener("click", startGeneration);
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", onEnterGenerateView);
  });
}
