"use strict";

const ROLE_LABELS = {
  curriculum: "カリキュラム一覧（今年度）",
  teachers: "教員一覧（今年度）",
  previous_curriculum: "前年度の時間割（任意）",
  previous_teachers: "前年度の教員一覧（任意）",
};

let selectedFiles = [];

function guessRole(name, used) {
  const isPrevious = /前年度|previous|昨年/.test(name);
  const isTeacher = /教員|teacher/.test(name);
  const candidates = isPrevious
    ? (isTeacher ? ["previous_teachers"] : ["previous_curriculum"])
    : (isTeacher ? ["teachers"] : ["curriculum"]);
  const fallback = ["curriculum", "teachers", "previous_curriculum", "previous_teachers"];
  return candidates.concat(fallback).find((role) => !used.has(role)) || "curriculum";
}

function renderFileAssignment() {
  const container = document.getElementById("file-assign");
  container.innerHTML = "";
  const used = new Set();

  selectedFiles.forEach((entry, index) => {
    entry.role = entry.role || guessRole(entry.file.name, used);
    used.add(entry.role);

    const row = document.createElement("div");
    row.className = "field";
    const select = document.createElement("select");
    Object.entries(ROLE_LABELS).forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = value === entry.role;
      select.appendChild(option);
    });
    select.addEventListener("change", () => { selectedFiles[index].role = select.value; });

    row.append(document.createTextNode(entry.file.name + " → "), select);
    container.appendChild(row);
  });

  const roles = new Set(selectedFiles.map((entry) => entry.role));
  document.getElementById("upload-button").disabled =
    !(roles.has("curriculum") && roles.has("teachers"));
}

function addFiles(fileList) {
  Array.from(fileList).forEach((file) => selectedFiles.push({ file, role: null }));
  renderFileAssignment();
}

function tallies(counts) {
  // 内訳は「会計 234 / 経営 262」と 1 行に潰すより、数字を拾える形にする。
  return Object.entries(counts)
    .map(([key, value]) => `<span class="tally">${escapeHtml(key)} <b>${value}</b></span>`)
    .join("");
}

function renderSummary(summary) {
  const stats = [
    ["科目", summary.subject_count],
    ["教員", summary.teacher_count],
    ["集中講義", summary.intensive_count],
    ["クオーター科目", summary.quarter_count],
  ];
  const breakdown = [
    ["学科別", tallies(summary.by_department)],
    ["科目区分別", tallies(summary.by_category)],
    ["教員区分別", tallies(summary.by_teacher_kind)],
    // 踏襲モードは前年度の 2 本がそろって初めて働く。片方だけ欠けても
    // 1 件も踏襲されないので、まとめず別々に出す。
    ["前年度の時間割",
      `<span class="tally">${summary.has_previous_year ? "あり" : "なし"}</span>`],
    ["前年度の教員一覧",
      `<span class="tally">${summary.has_previous_teachers ? "あり" : "なし"}</span>`],
  ];

  document.getElementById("upload-summary").innerHTML = `
    <div class="panel">
      <h3>読み込み結果</h3>
      <div class="stat-row">
        ${stats.map(([label, value]) => `
          <div class="stat">
            <span class="stat-value">${value}</span>
            <span class="stat-label">${escapeHtml(label)}</span>
          </div>`).join("")}
      </div>
      <dl class="breakdown">
        ${breakdown.map(([label, body]) =>
          `<dt>${escapeHtml(label)}</dt><dd>${body}</dd>`).join("")}
      </dl>
    </div>`;
}

function renderWarnings(warnings) {
  const container = document.getElementById("upload-warnings");
  if (!warnings.length) {
    container.innerHTML = '<p class="hint">警告はありません。</p>';
    return;
  }
  container.innerHTML = `
    <div class="panel">
      <h3>警告 <span class="count warn">${warnings.length}</span></h3>
      <!-- w.kind は内部の識別子。利用者に見せる意味が無いのでログだけに残す -->
      <ul>${warnings.map((w) => `<li>${escapeHtml(w.message)}</li>`).join("")}</ul>
    </div>`;
}

async function submitFiles() {
  const button = document.getElementById("upload-button");
  button.disabled = true;
  const formData = new FormData();
  selectedFiles.forEach((entry) => formData.append(entry.role, entry.file));

  try {
    const body = await api.uploadFiles(formData);
    adoptSession(body);
  } catch (error) {
    document.getElementById("upload-summary").innerHTML =
      `<p class="log-ERROR">読み込みに失敗しました: ${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

const SESSION_KEY = "timetable.sessionId";

function adoptSession(body, restored) {
  // サーバ側はアップロードした Excel を保存しており、同じ読み込み処理を
  // 通し直して復元できる。ID を localStorage に置いておけば、ブラウザの
  // 再読み込みやサーバの再起動をまたいで続きから作業できる。
  window.appState.sessionId = body.session_id;
  // 生成画面が踏襲モードの可否を判断するのに要る。アップロード・復元・
  // 保存済みセッションの選び直しが 3 つともここを通るので、1 箇所で足りる。
  window.appState.summary = body.summary;
  try {
    window.localStorage.setItem(SESSION_KEY, body.session_id);
  } catch (error) {
    // プライベートモードなどで保存できなくても動作は続ける
  }
  renderSummary(body.summary);
  renderWarnings(body.warnings);
  document.querySelector('#tabs button[data-view="generate"]').disabled = false;
  return restored ? adoptRestoredResult(body.session_id) : Promise.resolve();
}

async function adoptRestoredResult(sessionId) {
  // 生成結果もサーバに残っている。結果タブは生成完了時にしか有効化されて
  // いなかったため、復元しても結果に辿り着けなかった。
  let hasResult = false;
  try {
    hasResult = (await api.getResult(sessionId)).status === "done";
  } catch (error) {
    // 結果が無いだけ。読み込み済みデータは使えるので続行する
  }
  if (hasResult) {
    document.querySelector('#tabs button[data-view="result"]').disabled = false;
  }

  // セッション ID は利用者が使う場面が無い。復元されたことだけ伝える。
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = hasResult
    ? "前回の読み込みデータと生成結果を復元しました。「③ 結果」から続きを編集できます。"
    : "前回読み込んだデータを復元しました。"
      + "別の Excel を読み込むと、そちらに切り替わります。";
  document.getElementById("upload-summary").prepend(note);
}

function describeSavedSession(row) {
  // ファイル名は利用者が付ける自由文字列なので、属性値の中も含めて escape する。
  const when = (row.created_at || "").replace("T", " ") || "日時不明";
  const names = Object.values(row.files || {});
  const files = names.length ? names.join("・") : "ファイル名不明";
  const result = row.has_result ? "（生成結果あり）" : "";
  return `${escapeHtml(when)} — ${escapeHtml(files)}${result}`;
}

async function adoptSavedSession(sessionId) {
  // 復元と同じ経路を通す。タブの有効化も localStorage への記録も
  // adoptSession が面倒を見るので、ここでは選んだ ID を渡すだけにする。
  await adoptSession(await api.getSession(sessionId), true);
}

async function renderSavedSessions() {
  const panel = document.getElementById("saved-sessions");
  let rows = [];
  try {
    rows = await api.listSessions();
  } catch (error) {
    // 一覧が引けなくても、これから読み込む道は塞がない
  }
  if (!rows.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  document.getElementById("saved-session-list").innerHTML = rows
    .map((row) => `
      <li>
        <button type="button" class="saved-session"
                data-session="${escapeHtml(row.session_id)}">
          ${describeSavedSession(row)}
        </button>
      </li>`)
    .join("");

  document.querySelectorAll("#saved-session-list button").forEach((button) => {
    button.addEventListener("click", () => adoptSavedSession(button.dataset.session));
  });
}

async function restoreSession() {
  let saved = null;
  try {
    saved = window.localStorage.getItem(SESSION_KEY);
  } catch (error) {
    return;
  }
  if (!saved) return;
  try {
    await adoptSession(await api.getSession(saved), true);
  } catch (error) {
    // 保存期間を過ぎて消えたセッション。次回から探さない
    try {
      window.localStorage.removeItem(SESSION_KEY);
    } catch (ignored) {
      // 消せなくても実害はない
    }
  }
}

function initUpload() {
  const dropzone = document.getElementById("dropzone");
  const input = document.getElementById("file-input");

  ["dragenter", "dragover"].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    dropzone.addEventListener(name, () => dropzone.classList.remove("dragover"));
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    addFiles(event.dataTransfer.files);
  });
  input.addEventListener("change", () => addFiles(input.files));
  document.getElementById("upload-button").addEventListener("click", submitFiles);
  restoreSession();
  renderSavedSessions();
}
