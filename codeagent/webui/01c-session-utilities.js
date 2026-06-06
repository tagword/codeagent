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

// ---------------- Per-session input draft ----------------

const DRAFT_KEY_PREFIX = STORAGE_KEYS.SESS_DRAFT_PREFIX || 'oa_sess_draft_';

function _draftKey(sid) {
  return DRAFT_KEY_PREFIX + String(sid || '');
}

/** 保存当前会话的输入框内容到 localStorage */
function saveMsgDraft() {
  if (typeof msg === 'undefined' || !msg) return;
  const sid = typeof sessionId !== 'undefined' ? sessionId : '';
  if (!sid) return;
  const text = msg.value || '';
  if (text) {
    trySetLS(_draftKey(sid), text);
  } else {
    tryRemoveLS(_draftKey(sid));
  }
}

/** 恢复指定会话的输入框内容，不清空则不清除 localStorage 记录 */
function restoreMsgDraft(sid, clearAfter) {
  if (typeof msg === 'undefined' || !msg) return;
  if (!sid) { msg.value = ''; return; }
  const saved = tryGetLS(_draftKey(sid), '');
  msg.value = saved;
  if (clearAfter && saved) {
    tryRemoveLS(_draftKey(sid));
  }
  // 触发 auto-resize
  if (typeof msg.style !== 'undefined') {
    msg.style.height = 'auto';
    msg.style.height = Math.min(msg.scrollHeight, 220) + 'px';
  }
}

// ---------------- Auto-save draft on blur ----------------
// 用户点击侧边栏/切换标签页等场景也会丢失焦点，借此兜底保存。
if (typeof msg !== 'undefined' && msg) {
  msg.addEventListener('blur', function () {
    if (typeof saveMsgDraft === 'function') saveMsgDraft();
  });
}

// ---------------- Restore draft on page load ----------------
(function restoreDraftOnLoad() {
  var sid = typeof sessionId !== 'undefined' ? sessionId : '';
  if (sid && typeof restoreMsgDraft === 'function') {
    restoreMsgDraft(sid);
  }
})();

// ---------------- Chat inflight tracking ----------------
// 主体实现在 01q-inflight.js（chatInflightBySid / bumpChatInflight / restoreRunningSessions）。
