"use strict";

function switchView(name) {
  document.querySelectorAll("#tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
  if (name === "result") renderTimetable();
  if (name === "generate") onEnterGenerateView();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("#tabs button").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  initUpload();
  initSettings();
  initLogViewer();
  initGenerate();
  initTimetable();
});
