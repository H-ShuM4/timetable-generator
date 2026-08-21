"use strict";

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
  startGeneration(sessionId, mode, retargetCodes) {
    return request(`/api/generate/${sessionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, retarget_codes: retargetCodes || [] }),
    });
  },
  getResult(sessionId) {
    return request(`/api/result/${sessionId}`);
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
  exportUrl(sessionId) {
    return `/api/export/${sessionId}`;
  },
};
