/* ================================================================
 * 01c-session-utilities.js
 *   sessionId 初始化 + 共用工具函数（normReply / formatBubbleTime）。
 *
 *   加载顺序：01c-session-identity.js 之后（依赖 agentId / projectId），
 *   但在所有引用 sessionId 的代码（01c-session-tree.js 等）之前。
 *
 *   依赖 01c-session-identity.js 的 agentId / projectId。
 * ================================================================ */

let sessionId = loadSessionIdForAgent(agentId, projectId);

// ---------------- Core utility functions ----------------
// escapeHtml/escAttr 已统一在 00-utils.js（顶层声明）。

function normReply(s) {
  return String(s || '').replace(/\r\n/g, '\n').trim();
}
function formatBubbleTime(at) {
  if (at == null || at === '') return '';
  const d = typeof at === 'number' ? new Date(at) : new Date(at);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  });
}

// ---------------- Chat inflight tracking ----------------
// 主体实现在 01q-inflight.js（chatInflightBySid / bumpChatInflight / restoreRunningSessions）。
