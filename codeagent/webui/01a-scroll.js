/* ================================================================
 * 01-core.js
 *   - DOM refs (log, msg, send, stop, thinkToggle, modelSelect)
 *   - Model selection persistence (localStorage)
 *   - Thinking toggle persistence
 *   - Session/agent identity (sessionId, projectId, agentId)
 *   - Core utility functions (escapeHtml, normReply, scrollLog, ...)
 *   - Chat inflight tracking (chatInflightBySid)
 *   - Refresh projects list
 * ================================================================ */

const log = document.getElementById('log');
const msg = document.getElementById('msg');
const sendBtn = document.getElementById('send');
const stopBtn = document.getElementById('stop');
const thinkToggle = document.getElementById('thinkToggle');
const modelSelect = document.getElementById('modelSelect');

// ── Smart auto-scroll (don't pull user away from history) ──────────────
let _userNearBottom = true;
const _SCROLL_THRESHOLD = 120; // px from bottom → "near bottom"

function scrollLog() {
  if (_userNearBottom && log) {
    log.scrollTop = log.scrollHeight;
  } else if (log) {
    // User scrolled away from bottom → show "new messages" hint
    _showNewMsgBtn();
  }
}
/** Force scroll to bottom regardless of user position (e.g. new message sent). */
function scrollLogForce() {
  if (!log) return;
  _userNearBottom = true;
  log.scrollTop = log.scrollHeight;
  _hideNewMsgBtn();
}

// ── New message floating button ───────────────────────────────────────
let _newContentPending = false;
const _newMsgBtn = document.getElementById('btnNewMessages');

function _updateNewMsgBtn() {
  if (!_newMsgBtn) return;
  if (!_userNearBottom && _newContentPending) {
    _newMsgBtn.style.display = 'inline-flex';
  } else {
    _newMsgBtn.style.display = 'none';
  }
}
function _showNewMsgBtn() {
  _newContentPending = true;
  _updateNewMsgBtn();
}
function _hideNewMsgBtn() {
  _newContentPending = false;
  _updateNewMsgBtn();
}

// Wire scroll detection to update button
function _initScrollDetection() {
  if (!log || log.dataset.scrollDetect === '1') return;
  log.dataset.scrollDetect = '1';
  log.addEventListener('scroll', () => {
    const dist = log.scrollHeight - log.scrollTop - log.clientHeight;
    _userNearBottom = dist <= _SCROLL_THRESHOLD;
    _updateNewMsgBtn();
  }, { passive: true });
}
_initScrollDetection();

// Click handler: scroll to bottom on button click
if (_newMsgBtn) {
  _newMsgBtn.addEventListener('click', () => {
    scrollLogForce();
  });
}

// ---------------- Model selection persistence ----------------
