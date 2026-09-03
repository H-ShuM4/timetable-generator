"use strict";

let retargetItems = [];

function selectedMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

// 踏襲モードは前年度の 2 本がそろって初めて働く。時間割だけ入れて教員一覧を
// 忘れると、研究日の比較が「前年度＝なし」対「今年度＝あり」となって全専任が
// 組み替え対象へ落ち、1 件も引き継がれない。実データでは 613 件中 613 件が
// 組み替えになる。エラーも出ないので「動いていない」ようにしか見えなかった。
const PREVIOUS_FILES = [
  { key: "has_previous_year", label: "前年度の時間割" },
  { key: "has_previous_teachers", label: "前年度の教員一覧" },
];

function missingPreviousFiles() {
  const summary = window.appState.summary;
  if (!summary) return PREVIOUS_FILES.map((file) => file.label);
  return PREVIOUS_FILES.filter((file) => !summary[file.key]).map((file) => file.label);
}

function updateInheritAvailability() {
  const radio = document.querySelector('input[name="mode"][value="inherit"]');
  const note = document.getElementById("inherit-note");
  const missing = missingPreviousFiles();

  radio.disabled = missing.length > 0;
  if (!missing.length) {
    note.hidden = true;
    note.textContent = "";
    return;
  }
  // textContent なのでエスケープは要らない（文言はこちらが決めた固定文字列）
  note.hidden = false;
  note.textContent =
    "踏襲モード　前年度の「時間割」と「教員一覧」の 2 つのファイルが必要です。"
    + "「1 ファイル読込」から、2 つとも読み込んでください。"
    + "※片方だけでは前年度の内容を引き継げません。";
  // 押せないモードが選ばれたままにしない
  if (radio.checked) {
    document.querySelector('input[name="mode"][value="mock"]').checked = true;
  }
}

function retargetSummary() {
  const summary = window.appState.summary || {};
  const total = (summary.subject_count || 0) - (summary.intensive_count || 0);
  const change = retargetItems.length;
  const keep = Math.max(0, total - change);
  return `<p class="retarget-summary">`
    + `${total} 科目のうち <b>${change}</b> 件を組み替え、`
    + `<b>${keep}</b> 件は前年度のコマのままにします</p>`;
}

function groupByReason(items) {
  const groups = new Map();
  items.forEach((item) => {
    if (!groups.has(item.reason)) groups.set(item.reason, []);
    groups.get(item.reason).push(item);
  });
  // 件数の多い順。同数なら理由名の順で、並びを決定的にする。
  return [...groups.entries()].sort(
    (a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], "ja")
  );
}

function setAllRetarget(checked) {
  document.querySelectorAll("#retarget-list input[type=checkbox]")
    .forEach((box) => { box.checked = checked; });
}

function renderRetargetList() {
  const container = document.getElementById("retarget-list");
  if (!retargetItems.length) {
    container.innerHTML =
      "<p>組み替えが要る科目はありません。すべて前年度のコマのままになります。</p>";
    return;
  }

  // 理由ごとに畳んでおく。実データでは非常勤だけで 141 件あり、
  // 開いたまま並べると何件あるのかが読み取れない。
  const groups = groupByReason(retargetItems).map(([reason, items]) => `
    <details class="retarget-group">
      <summary>${escapeHtml(reason)} <span class="count">${items.length}</span></summary>
      <div class="retarget-items">
        ${items.map((item) => `
          <label class="retarget-item">
            <input type="checkbox" value="${escapeHtml(item.code)}" checked>
            <span class="retarget-code">${escapeHtml(item.code)}</span>
            <span class="retarget-name">${escapeHtml(item.name)}</span>
            <span class="retarget-teacher">${escapeHtml(item.teacher)}</span>
          </label>`).join("")}
      </div>
    </details>`).join("");

  container.innerHTML = retargetSummary()
    + `<div class="retarget-actions">
         <button type="button" id="retarget-all">すべて選択</button>
         <button type="button" id="retarget-none">すべて解除</button>
       </div>`
    + groups;

  document.getElementById("retarget-all")
    .addEventListener("click", () => setAllRetarget(true));
  document.getElementById("retarget-none")
    .addEventListener("click", () => setAllRetarget(false));
}

// AI モードは API キーが要る。キーが無いまま選ぶと、サーバは黙ってモックへ
// 落とす。走り終わってから「AI で作ったつもりだった」と気づくのは遅すぎる。
function updateAiAvailability(settings) {
  const radio = document.querySelector('input[name="mode"][value="optimize"]');
  const note = document.getElementById("ai-note");
  const ready = Boolean(settings && settings.has_api_key);

  radio.disabled = !ready;
  if (ready) {
    note.hidden = true;
    note.textContent = "";
    return;
  }
  note.hidden = false;
  note.textContent =
    "AI モード　Gemini の API キーが必要です。"
    + "画面右上の「設定」から登録してください。";
  if (radio.checked) {
    document.querySelector('input[name="mode"][value="mock"]').checked = true;
  }
}

// 踏襲モードでは重み付けを畳む。6 本のスライダーが先に来ると、その日いちばん
// 触りたい「組み替え対象」がスクロールの先へ押し出される。
function foldWeightsForMode() {
  document.getElementById("params").open = selectedMode() !== "inherit";
}

async function onEnterGenerateView() {
  updateInheritAvailability();
  try {
    updateAiAvailability(await api.getSettings());
  } catch (error) {
    // 設定が引けなくても生成の道は塞がない
  }
  foldWeightsForMode();
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

function setRunning(running) {
  document.getElementById("generate-button").disabled = running;
  const cancel = document.getElementById("cancel-button");
  cancel.disabled = !running;
  cancel.textContent = "中止する";
}

async function cancelGeneration() {
  const sessionId = window.appState.sessionId;
  if (!sessionId) return;

  const cancel = document.getElementById("cancel-button");
  cancel.disabled = true;
  cancel.textContent = "中止しています…";
  try {
    await api.cancelGeneration(sessionId);
    // 実際に止まるのは段の変わり目なので、押してすぐには終わらない。
    // 終わりは SSE の done で受け取る。
    setStatus("中止しています。区切りのよいところで止まります…");
  } catch (error) {
    setRunning(true);
    setStatus(`中止できませんでした: ${error.message}`, true);
  }
}

async function startGeneration() {
  const sessionId = window.appState.sessionId;
  if (!sessionId) {
    setStatus("先にファイルを読み込んでください", true);
    return;
  }

  setRunning(true);
  clearLog();
  openLogPanel();
  setStatus("生成中です…");
  // ログパネルは画面下端に固定で開くため、そのままだとボタンの列を
  // 覆ってしまい、中止したくても押せない。生成中に一番使うのは中止なので、
  // 開けたあとで見える位置へ寄せる。
  document.getElementById("cancel-button").scrollIntoView({ block: "center" });

  try {
    // 組み替え対象は踏襲モードでしか意味を持たない。他のモードでは
    // null を送り、サーバ側の自動検出に触れないようにする。
    const retarget = selectedMode() === "inherit" ? checkedRetargetCodes() : null;
    const body = await api.startGeneration(
      sessionId, selectedMode(), retarget, selectedWeights(), selectedEffort()
    );
    if (body.mode !== selectedMode()) {
      const label = MODE_LABELS[body.mode] || body.mode;
      setStatus(`API キーが未設定のため ${label} モードで実行します`);
    }
    connectLogStream(sessionId, async (finished) => {
      setRunning(false);
      if (!finished) {
        setStatus("ログ配信が切断されました。結果タブで状態を確認してください", true);
        return;
      }
      const result = await api.getResult(sessionId);
      if (result.status === "failed") {
        setStatus(`生成に失敗しました: ${result.error || "不明なエラー"}`, true);
        return;
      }
      if (result.status === "cancelled") {
        // 中止は失敗ではない。結果は残さないので結果タブも開けない。
        setStatus("生成を中止しました。もう一度始めるには「生成を開始」を押してください");
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
    setRunning(false);
    setStatus(`生成を開始できませんでした: ${error.message}`, true);
  }
}

function initGenerate() {
  renderParams();
  document.getElementById("generate-button").addEventListener("click", startGeneration);
  document.getElementById("cancel-button").addEventListener("click", cancelGeneration);
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", onEnterGenerateView);
  });
}
