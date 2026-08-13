"use strict";

function applySettings(body) {
  document.getElementById("model").value = body.model;
  document.getElementById("max-retries").value = body.max_retries;
  document.getElementById("api-key-status").textContent =
    body.has_api_key ? `保存済み（${body.api_key_masked}）` : "未設定";
}

function showStatus(message, isError) {
  const element = document.getElementById("settings-status");
  element.textContent = message;
  element.className = isError ? "log-ERROR" : "";
}

async function initSettings() {
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
      }));
      showStatus("設定を保存しました");
    } catch (error) {
      showStatus(`保存に失敗しました: ${error.message}`, true);
    }
  });
}
