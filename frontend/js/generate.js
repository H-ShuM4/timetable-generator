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
  optimize: "最適化",
  inherit: "踏襲",
};

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
      sessionId, selectedMode(), checkedRetargetCodes()
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
    });
  } catch (error) {
    button.disabled = false;
    setStatus(`生成を開始できませんでした: ${error.message}`, true);
  }
}

function initGenerate() {
  document.getElementById("generate-button").addEventListener("click", startGeneration);
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", onEnterGenerateView);
  });
}
