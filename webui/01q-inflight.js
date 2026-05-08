
const chatInflightBySid = {};
let lastLocalAgentReplyNorm = '';
let lastLocalAgentReplyAt = 0;
let pinSessionToTopOnce = '';

function updateComposerButtons() {
  const active = (chatInflightBySid[sessionId] || 0) > 0;
  if (stopBtn) stopBtn.disabled = !active;
}
function bumpChatInflight(sid, delta) {
  const k = String(sid || '');
  if (!k) return;
  const n = (chatInflightBySid[k] || 0) + delta;
  if (n <= 0) delete chatInflightBySid[k];
  else chatInflightBySid[k] = n;
  updateComposerButtons();
  if (typeof applySessionRunningState === 'function') applySessionRunningState(k);
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
