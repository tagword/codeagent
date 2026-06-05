/* ================================================================
 * 00-utils.js
 *   共享工具函数（顶层声明，字母序下排在所有文件最前）。
 *
 *   本文件必须先于其他 JS 加载（按字母序自动满足：00-* 排第一位）。
 *   各 *.js 文件直接调用 escapeHtml/escAttr，无需 import。
 *   （拼装式 SPA 的约定，不走 ES module。）
 *
 *   历史上散落在 5 个文件中的 6 个 escape 函数实现已统一：
 *     - 01c-session.js:802  escapeHtml    → 4 字符 &<>"
 *     - 01c-session.js:805  escAttr       → 4 字符 &"<>（与 body 顺序不同）
 *     - 08d-editor.js:73    escapeHtml    → DOM textContent 反射（5 字符 &<>"'）
 *     - 09f-remote.js:72    escapeHtml    → DOM textContent 反射（5 字符 &<>"'）
 *     - 09f-remote.js:76    escapeHtmlAttr→ 2 字符 "'（仅属性场景）
 *     - 11g-env-paths-git.js:3 escHtml    → 4 字符 &<>"
 *
 *   不一致导致 11g 的路径含 ' 时不转义、escAttr 不处理 ' 是真 XSS 风险。
 *   现统一为 2 个函数，均 5 字符 &<>"'：
 *     - escapeHtml(s)  HTML body 文本
 *     - escAttr(s)     HTML 属性值（语义与 body 相同，但语义明确 + 5 字符）
 * ================================================================ */

/** HTML 文本/属性通用转义。5 字符 &<>"' 全覆盖。 */
function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** HTML 属性值转义。与 escapeHtml 同语义，独立命名以强调使用场景。 */
function escAttr(s) {
  return escapeHtml(s);
}
