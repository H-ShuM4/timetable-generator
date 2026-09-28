"use strict";

// サーバとのやりとりを 1 か所に集める。
//
// **fetch を書くのはこのファイルだけにする。** 各画面が直に叩くと、
// エラーの出し方（サーバが返す detail の拾い方）が画面ごとにばらけ、
// 事務局に届く文言が場所によって変わってしまう。
//
// window.appState.sessionId は「いま扱っている読み込みデータ」を指す。
// 読込・生成・結果の 3 画面が同じものを見るため、大域に 1 つだけ置く。
window.appState = { sessionId: null };

async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch (_) { /* JSON でない応答はそのまま */ }
    throw new Error(detail);
  }
  return response.json();
}

const api = {
  uploadFiles(formData) {
    return request("/api/upload", { method: "POST", body: formData });
  },
  getSettings() {
    return request("/api/settings");
  },
  putSettings(payload) {
    return request("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  putApiKey(apiKey) {
    return request("/api/settings/api-key", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
  },
  deleteApiKey() {
    return request("/api/settings/api-key", { method: "DELETE" });
  },
  listSessions() {
    return request("/api/sessions");
  },
  getSession(sessionId) {
    return request(`/api/sessions/${sessionId}`);
  },
  getRetarget(sessionId) {
    return request(`/api/retarget/${sessionId}`);
  },
  startGeneration(sessionId, mode, retargetCodes, weights, repairEffort, retargetWith) {
    return request(`/api/generate/${sessionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode,
        // null は「自動検出に任せる」。空配列は「すべて解除」で意味が違う。
        retarget_codes: retargetCodes ?? null,
        weights: weights || {},
        repair_effort: repairEffort || "off",
        retarget_with: retargetWith || "solver",
      }),
    });
  },
  cancelGeneration(sessionId) {
    return request(`/api/generate/${sessionId}/cancel`, { method: "POST" });
  },
  getResult(sessionId) {
    return request(`/api/result/${sessionId}`);
  },
  unplaceSubject(sessionId, code) {
    return request(`/api/result/${sessionId}/unplace`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
  },
  moveSubject(sessionId, code, slots) {
    return request(`/api/result/${sessionId}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, slots }),
    });
  },
  streamUrl(sessionId) {
    return `/api/generate/${sessionId}/stream`;
  },
  // 保存するファイル名は事務局が決める。整えるのはサーバ側
  // （Windows が使えない文字を落とす）なので、ここでは素通しする。
  exportUrl(sessionId, name) {
    return `/api/export/${sessionId}?name=${encodeURIComponent(name || "")}`;
  },
};
