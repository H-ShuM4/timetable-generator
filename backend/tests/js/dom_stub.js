// フロントの JS を node 上で動かすための最小限の DOM。
//
// ブラウザ全体を用意しなくても、「どんな HTML を書き出したか」「どの
// 要素が有効になったか」は確かめられる。実機でしか見つからなかった
// 不具合が続いたため、この程度でも押さえておく価値がある。
//
// 本物の DOM ではない。innerHTML は文字列として持つだけで、解析も
// 再描画もしない。要素を探す機能は用意した分しか動かない。

function createElement(id) {
  return {
    id,
    innerHTML: "",
    textContent: "",
    value: "",
    className: "",
    checked: false,
    disabled: false,
    prepended: null,
    classes: new Set(),
    classList: {
      add(name) { this.owner.classes.add(name); },
      remove(name) { this.owner.classes.delete(name); },
      contains(name) { return this.owner.classes.has(name); },
      toggle(name, force) {
        const on = force === undefined ? !this.owner.classes.has(name) : force;
        if (on) this.owner.classes.add(name); else this.owner.classes.delete(name);
        return on;
      },
    },
    prepend(node) { this.prepended = node; },
    addEventListener() {},
    querySelectorAll() { return []; },
  };
}

function element(id) {
  const node = createElement(id);
  node.classList.owner = node;
  return node;
}

/**
 * @param {object} options
 *   matchers: セレクタ文字列 → 返す要素（または要素の配列）の対応
 */
function createDocument(options = {}) {
  const nodes = {};
  const matchers = options.matchers || {};

  function lookup(selector) {
    for (const [needle, value] of Object.entries(matchers)) {
      if (selector.includes(needle)) return value;
    }
    return null;
  }

  return {
    nodes,
    getElementById(id) {
      if (!nodes[id]) nodes[id] = element(id);
      return nodes[id];
    },
    querySelector(selector) {
      const found = lookup(selector);
      return Array.isArray(found) ? found[0] : found;
    },
    querySelectorAll(selector) {
      const found = lookup(selector);
      if (!found) return [];
      return Array.isArray(found) ? found : [found];
    },
    createElement() { return element("created"); },
    addEventListener() {},
  };
}

/** innerHTML の文字列から data-属性の値を出現順に拾う。 */
function attributeValues(html, attribute) {
  const pattern = new RegExp(`${attribute}="([^"]*)"`, "g");
  const found = [];
  let match;
  while ((match = pattern.exec(html)) !== null) found.push(match[1]);
  return found;
}

module.exports = { element, createDocument, attributeValues };
