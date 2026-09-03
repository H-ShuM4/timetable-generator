"use strict";

// 画面の切り替えと起動。**ここがフロントの入口である。**
//
// 素の HTML / CSS / JavaScript で書いてある。フレームワークも CDN も
// 使っていない。事務局 PC はオフラインやプロキシ配下で動くことがあり、
// 外から何かを取りに行く作りにすると、そこで止まってしまうためである。
// 読み込む順は index.html の末尾にあり、後ろのファイルが前のファイルの
// 関数を呼ぶ（モジュールではないので、すべて同じ大域に載る）。
//
//   api.js        サーバとのやりとり。ここだけが fetch を持つ
//   upload.js     ① ファイル読込
//   settings.js   設定
//   logviewer.js  下端のログ（SSE で受ける）
//   generate.js   ② 生成
//   timetable.js  ③ 結果
//   main.js       画面の切り替えと起動（このファイル）
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
