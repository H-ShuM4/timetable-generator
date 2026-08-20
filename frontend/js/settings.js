"use strict";

// 予備モデルのチェックボックスに並べる候補。新しい順。ここに無い名前は
// 「その他」欄に自由入力でき、保存後もそちらに残る。
const FALLBACK_CANDIDATES = [
  "gemini-3.7-flash",
  "gemini-3.6-flash",
  "gemini-3.5-flash",
  "gemini-3-flash-preview",
  "gemini-2.5-flash",
];

function renderFallbackCandidates() {
  document.getElementById("fallback-models").innerHTML = FALLBACK_CANDIDATES
    .map(
      (name) =>
        `<label><input type="checkbox" class="fallback-model" value="${name}"> ${name}</label>`
    )
    .join("");
}

function applyFallbackModels(models) {
  const selected = new Set(models);
  document.querySelectorAll(".fallback-model").forEach((box) => {
    box.checked = selected.has(box.value);
  });
  // 候補一覧に無い名前は失わずに「その他」欄へ戻す
  document.getElementById("fallback-extra").value = models
    .filter((name) => !FALLBACK_CANDIDATES.includes(name))
    .join(", ");
}

function collectFallbackModels() {
  // 送る順がそのまま切り替え順になる。候補一覧の並び（新しい順）を保つ。
  const checked = Array.from(document.querySelectorAll(".fallback-model"))
    .filter((box) => box.checked)
    .map((box) => box.value);
  const extra = document
    .getElementById("fallback-extra")
    .value.split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  return [...checked, ...extra];
}

function applySettings(body) {
  document.getElementById("model").value = body.model;
  document.getElementById("max-retries").value = body.max_retries;
  applyFallbackModels(body.fallback_models || []);
  document.getElementById("api-key-status").textContent =
    body.has_api_key ? `保存済み（${body.api_key_masked}）` : "未設定";
}

function showStatus(message, isError) {
  const element = document.getElementById("settings-status");
  element.textContent = message;
  element.className = isError ? "log-ERROR" : "";
}

async function initSettings() {
  renderFallbackCandidates();
  try {
    applySettings(await api.getSettings());
  } catch (error) {
    showStatus(`設定の読み込みに失敗しました: ${error.message}`, true);
  }

  document.getElementById("save-key").addEventListener("click", async () => {
    const input = document.getElementById("api-key");
    if (!input.value.trim()) {
      showStatus("API キーを入力してください", true);
      return;
    }
    try {
      applySettings(await api.putApiKey(input.value.trim()));
      input.value = "";
      showStatus("API キーを保存しました");
    } catch (error) {
      showStatus(`保存に失敗しました: ${error.message}`, true);
    }
  });

  document.getElementById("delete-key").addEventListener("click", async () => {
    try {
      applySettings(await api.deleteApiKey());
      showStatus("API キーを削除しました");
    } catch (error) {
      showStatus(`削除に失敗しました: ${error.message}`, true);
    }
  });

  document.getElementById("save-settings").addEventListener("click", async () => {
    try {
      applySettings(await api.putSettings({
        model: document.getElementById("model").value.trim(),
        max_retries: Number(document.getElementById("max-retries").value),
        fallback_models: collectFallbackModels(),
      }));
      showStatus("設定を保存しました");
    } catch (error) {
      showStatus(`保存に失敗しました: ${error.message}`, true);
    }
  });
}
