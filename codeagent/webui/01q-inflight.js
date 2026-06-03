
const chatInflightBySid = {};

/**
 * 刚刚结束运行的会话集合（sid → true）。
 * agent 运行结束后显示绿色实心圆点（不闪烁），用户点击后清除。
 * 通过 localStorage 持久化，刷新页面后仍可恢复。
 */
const chatCompletedBySid = {};
var _COMPLETED_STORAGE_KEY = 'oaSessionCompletedMap';

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

function updateComposerButtons() {
  const active = (chatInflightBySid[sessionId] || 0) > 0;
  if (sendBtn) {
    sendBtn.classList.toggle('is-stop', active);
    const sendIcon = sendBtn.querySelector('.compose__send-icon');
    const stopIcon = sendBtn.querySelector('.compose__stop-icon');
    if (sendIcon) sendIcon.style.display = active ? 'none' : '';
    if (stopIcon) stopIcon.style.display = active ? '' : 'none';
    sendBtn.title = active ? '停止' : '发送 (Enter)';
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
  const k = String(sid || '');
  if (!k) return;
  const n = (chatInflightBySid[k] || 0) + delta;
  if (n <= 0) {
    delete chatInflightBySid[k];
    // 运行结束：标记为「已完成」状态（绿色实心）
    if (delta < 0) {
      chatCompletedBySid[k] = true;
      persistCompletedSessions();
    }
  } else {
    chatInflightBySid[k] = n;
    // 重新运行时清除已完成标记
    delete chatCompletedBySid[k];
    persistCompletedSessions();
  }
  updateComposerButtons();
  if (typeof applySessionRunningState === 'function') applySessionRunningState(k);
  if (typeof applySessionCompletedState === 'function') applySessionCompletedState(k);
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
        if (sid) {
          const k = String(sid);
          if (!chatInflightBySid[k]) chatInflightBySid[k] = 1;
          // 运行中的会话不应同时标记为「已完成」
          delete chatCompletedBySid[k];
          persistCompletedSessions();
        }
      });
    }
  } catch (_) {}
}

/**
 * 定时轮询后端 running 状态，确保页面长时间不刷新时
 * 侧边栏的「运行中」状态指示器也能同步更新。
 * 每 5 秒轮询一次，仅在页面可见时执行。
 */
var _runningPollTimer = null;

function startRunningStatePolling() {
  stopRunningStatePolling();
  _runningPollTimer = setInterval(pollRunningState, 5000);
  // 立即执行一次
  pollRunningState();
}

function stopRunningStatePolling() {
  if (_runningPollTimer) {
    clearInterval(_runningPollTimer);
    _runningPollTimer = null;
  }
}

async function pollRunningState() {
  // 页面不可见时不轮询，节省资源
  if (typeof document !== 'undefined' && document.hidden) return;
  try {
    const aid = (typeof agentId !== 'undefined') ? agentId : 'default';
    const r = await fetch('/api/ui/sessions/running?agent_id=' + encodeURIComponent(aid));
    if (!r.ok) return;
    const j = await r.json();
    if (!j || !Array.isArray(j.running)) return;

    // 将后端返回的运行中会话同步到前端状态
    const runningSet = new Map();
    j.running.forEach(function(sid) {
      if (sid) {
        const k = String(sid);
        runningSet.set(k, true);
        // 后端认为在运行中，但前端没有标记 → 补上
        if (!chatInflightBySid[k]) {
          chatInflightBySid[k] = 1;
          delete chatCompletedBySid[k];
          if (typeof applySessionRunningState === 'function') applySessionRunningState(k);
          if (typeof applySessionCompletedState === 'function') applySessionCompletedState(k);
        }
      }
    });

    // 前端标记为运行中、但后端已不认为在运行的会话 → 清理
    Object.keys(chatInflightBySid).forEach(function(k) {
      if (!runningSet.has(k)) {
        delete chatInflightBySid[k];
        // 标记为已完成（如果之前不是已完成状态）
        if (!chatCompletedBySid[k]) {
          chatCompletedBySid[k] = true;
          persistCompletedSessions();
        }
        if (typeof applySessionRunningState === 'function') applySessionRunningState(k);
        if (typeof applySessionCompletedState === 'function') applySessionCompletedState(k);
      }
    });

    updateComposerButtons();
  } catch (_) {
    // 轮询失败静默处理
  }
}

// 在 DOM 加载完成后启动轮询
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startRunningStatePolling);
  } else {
    startRunningStatePolling();
  }
  // 页面可见性变化时恢复轮询
  document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
      pollRunningState();
    }
  });
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
