
const chatInflightBySid = {};
/** 待发送附件（06b-attachments.js 读写；须在此提前声明避免 TDZ） */
var pendingAttachments = [];

/**
 * 刚刚结束运行的会话集合（sid → true）。
 * agent 运行结束后显示绿色实心圆点（不闪烁），用户点击后清除。
 * 通过 localStorage 持久化，刷新页面后仍可恢复。
 */
const chatCompletedBySid = {};
var _COMPLETED_STORAGE_KEY = STORAGE_KEYS.SESS_COMPLETED;

/** 从 localStorage 恢复会话已完成状态 */
function restoreCompletedSessions() {
  try {
    var raw = localStorage.getItem(_COMPLETED_STORAGE_KEY);
    if (!raw) return;
    var obj = JSON.parse(raw);
    if (obj && typeof obj === 'object') {
      Object.keys(obj).forEach(function(k) {
        chatCompletedBySid[k] = true;
      });
    }
  } catch (_) {}
}

/** 将会话已完成状态持久化到 localStorage */
function persistCompletedSessions() {
  try {
    var keys = Object.keys(chatCompletedBySid);
    if (keys.length === 0) {
      localStorage.removeItem(_COMPLETED_STORAGE_KEY);
    } else {
      var obj = {};
      keys.forEach(function(k) { obj[k] = true; });
      localStorage.setItem(_COMPLETED_STORAGE_KEY, JSON.stringify(obj));
    }
  } catch (_) {}
}

let lastLocalAgentReplyNorm = '';
let lastLocalAgentReplyAt = 0;
let pinSessionToTopOnce = '';

function isSessionRunning(sid) {
  return (chatInflightBySid[String(sid || '')] || 0) > 0;
}

function composeHasSendPayload() {
  const text = msg && msg.value ? msg.value.trim() : '';
  const hasPending = pendingAttachments && pendingAttachments.length > 0;
  return !!(text || hasPending);
}

/** 幂等设置会话 running / idle（单一状态源，避免 +/- 计数漂移） */
function setSessionRunning(sid, running) {
  const k = String(sid || '');
  if (!k) return;
  if (running) {
    chatInflightBySid[k] = 1;
    delete chatCompletedBySid[k];
    persistCompletedSessions();
  } else {
    delete chatInflightBySid[k];
    chatCompletedBySid[k] = true;
    persistCompletedSessions();
  }
  updateComposerButtons();
  if (typeof applySessionRunningState === 'function') applySessionRunningState(k);
  if (typeof applySessionCompletedState === 'function') applySessionCompletedState(k);
}

function updateComposerButtons() {
  const active = isSessionRunning(sessionId);
  const showStop = active && !composeHasSendPayload();
  if (typeof stopBtn !== 'undefined' && stopBtn) stopBtn.disabled = !active;
  if (sendBtn) {
    sendBtn.classList.toggle('is-stop', showStop);
    sendBtn.classList.toggle('is-finishing', active && composeHasSendPayload());
    sendBtn.title = showStop
      ? '停止（等待本轮回答完成）'
      : (active ? '发送补充消息 (Enter)' : '发送 (Enter)');
    const sendIcon = sendBtn.querySelector('.compose__send-icon');
    const stopIcon = sendBtn.querySelector('.compose__stop-icon');
    if (sendIcon) sendIcon.style.display = showStop ? 'none' : '';
    if (stopIcon) stopIcon.style.display = showStop ? '' : 'none';
    sendBtn.disabled = false;
  }
}

/** 清除会话的「已完成」状态（用户点击后调用） */
function clearSessionCompleted(sid) {
  const k = String(sid || '');
  if (!k) return;
  delete chatCompletedBySid[k];
  persistCompletedSessions();
  if (typeof applySessionCompletedState === 'function') applySessionCompletedState(k);
}

function bumpChatInflight(sid, delta) {
  if (delta > 0) setSessionRunning(sid, true);
  else if (delta < 0) setSessionRunning(sid, false);
}
function rememberLocalAgentReply(text) {
  const n = normReply(text);
  if (!n) return;
  lastLocalAgentReplyNorm = n;
  lastLocalAgentReplyAt = Date.now();
}
function resetAgentReplyDedupe() {
  lastLocalAgentReplyNorm = '';
  lastLocalAgentReplyAt = 0;
  // Also reset streaming bubble state so a new conversation starts fresh.
  // (global vars defined in 03-markdown.js)
  if (typeof _streamBubbleWrap !== 'undefined') _streamBubbleWrap = null;
  if (typeof _streamConsumedLen !== 'undefined') _streamConsumedLen = 0;
}

/**
 * 页面刷新后从后端恢复正在运行中的会话状态（心跳指示）。
 * 并同时从 localStorage 恢复已完成会话状态（绿色实心）。
 * 由 initWebUiSessions 在最开始时调用。
 */
async function restoreRunningSessions() {
  // 1. 从 localStorage 恢复已完成（绿色实心）状态
  restoreCompletedSessions();
  // 2. 从后端 API 恢复正在运行中的状态
  try {
    const aid = (typeof agentId !== 'undefined') ? agentId : 'default';
    const r = await fetch('/api/ui/sessions/running?agent_id=' + encodeURIComponent(aid));
    if (!r.ok) return;
    const j = await r.json();
    if (j && Array.isArray(j.running)) {
      j.running.forEach(function(sid) {
        if (sid) setSessionRunning(String(sid), true);
      });
    }
  } catch (_) {}
}

// ---- 项目路径显示：切换项目时更新 topbar ---- //
document.addEventListener('project-changed', function(e) {
  var pathEl = document.getElementById('currentProjectPath');
  if (!pathEl) return;
  var pid = (e && e.detail && e.detail.projectId) || projectId || '';
  var path = '';
  if (pid && treeProjectsCache && treeProjectsCache.aid === agentId) {
    for (var i = 0; i < treeProjectsCache.projects.length; i++) {
      var p = treeProjectsCache.projects[i];
      if (p.id === pid && p.path) {
        path = p.path;
        break;
      }
    }
  }
  if (path) {
    pathEl.textContent = path;
    pathEl.style.display = '';
  } else {
    pathEl.style.display = 'none';
  }
});
