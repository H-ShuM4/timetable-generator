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

function renderSummary(summary) {
  const entries = [
    ["科目数", summary.subject_count],
    ["教員数", summary.teacher_count],
    ["集中講義", summary.intensive_count],
    ["クオーター科目", summary.quarter_count],
  ];
  const byDept = Object.entries(summary.by_department)
    .map(([key, value]) => `${key} ${value}`).join(" / ");
  const byCat = Object.entries(summary.by_category)
    .map(([key, value]) => `${key} ${value}`).join(" / ");
  const byKind = Object.entries(summary.by_teacher_kind)
    .map(([key, value]) => `${key} ${value}`).join(" / ");

  document.getElementById("upload-summary").innerHTML = `
    <h3>読み込み結果</h3>
    <ul>
      ${entries.map(([k, v]) => `<li>${k}: ${v}</li>`).join("")}
      <li>学科別: ${byDept}</li>
      <li>科目区分別: ${byCat}</li>
      <li>教員区分別: ${byKind}</li>
      <li>前年度データ: ${summary.has_previous_year ? "あり" : "なし"}</li>
    </ul>`;
}

function renderWarnings(warnings) {
  const container = document.getElementById("upload-warnings");
  if (!warnings.length) {
    container.innerHTML = "<p>警告はありません。</p>";
    return;
  }
  container.innerHTML = `
    <h3>警告 ${warnings.length} 件</h3>
    <ul>${warnings.map((w) => `<li>[${escapeHtml(w.kind)}] ${escapeHtml(w.message)}</li>`).join("")}</ul>`;
}

async function submitFiles() {
  const button = document.getElementById("upload-button");
  button.disabled = true;
  const formData = new FormData();
  selectedFiles.forEach((entry) => formData.append(entry.role, entry.file));

  try {
    const body = await api.uploadFiles(formData);
    window.appState.sessionId = body.session_id;
    renderSummary(body.summary);
    renderWarnings(body.warnings);
    document.querySelector('#tabs button[data-view="generate"]').disabled = false;
  } catch (error) {
    document.getElementById("upload-summary").innerHTML =
      `<p class="log-ERROR">読み込みに失敗しました: ${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
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
}
