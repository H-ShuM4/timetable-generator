"use strict";

let logSource = null;
let logFilter = "ALL";
const logEntries = [];

function renderLogEntries() {
  const body = document.getElementById("log-body");
  body.innerHTML = logEntries
    .filter((entry) => logFilter === "ALL" || entry.level === logFilter)
    .map((entry) => {
      const stage = entry.stage ? `[${entry.stage}] ` : "";
      return `<div class="log-${entry.level}">${entry.timestamp} ${entry.level} ${stage}${escapeHtml(entry.message)}</div>`;
    })
    .join("");
  body.scrollTop = body.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function appendLog(event) {
  logEntries.push(event);
  renderLogEntries();
}

function clearLog() {
  logEntries.length = 0;
  renderLogEntries();
}

function openLogPanel() {
  document.getElementById("log-panel").classList.remove("collapsed");
  document.getElementById("log-toggle").textContent = "▼";
}

function connectLogStream(sessionId, onDone) {
  if (logSource) logSource.close();
  logSource = new EventSource(api.streamUrl(sessionId));

  logSource.onmessage = (message) => {
    if (!message.data || message.data === "{}") return;
    appendLog(JSON.parse(message.data));
  };
  logSource.addEventListener("done", () => {
    logSource.close();
    logSource = null;
    if (onDone) onDone();
  });
  logSource.onerror = () => {
    appendLog({
      level: "ERROR",
      message: "ログ配信が切断されました",
      timestamp: new Date().toISOString().slice(0, 19),
      stage: null,
    });
    if (logSource) logSource.close();
    logSource = null;
  };
}

function initLogViewer() {
  document.getElementById("log-toggle").addEventListener("click", () => {
    const panel = document.getElementById("log-panel");
    panel.classList.toggle("collapsed");
    document.getElementById("log-toggle").textContent =
      panel.classList.contains("collapsed") ? "▲" : "▼";
  });
  document.getElementById("log-filter").addEventListener("change", (event) => {
    logFilter = event.target.value;
    renderLogEntries();
  });
}
