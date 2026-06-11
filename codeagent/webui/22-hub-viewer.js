// Hub 消息查看器 — SSE 实时流 + 历史消息

var _hubEventSource = null;
var _hubMessages = [];
var _hubFilterAgent = '';

function _hubApi(path, opts) {
  return fetch(apiUrl(path), opts || {}).then(function(r){
    if (!r.ok) return r.json().then(function(e){ throw new Error(e.detail || '请求失败') });
    return r.json();
  });
}

// ── 页面切换 ──
function switchToHubPage() {
  if (typeof switchToPage === 'function') switchToPage('hub');
}

// ── 加载历史消息 ──
function _loadHubHistory() {
  var url = '/api/ui/hub/messages?limit=100';
  if (_hubFilterAgent) url += '&agent_id=' + encodeURIComponent(_hubFilterAgent);
  _hubApi(url).then(function(data){
    _hubMessages = data.messages || [];
    _renderHubMessages();
  }).catch(function(err){
    console.warn('加载 Hub 历史失败:', err);
  });
}

// ── 渲染消息列表 ──
function _renderHubMessages() {
  var el = document.getElementById('hubMessageList');
  if (!el) return;
  if (_hubMessages.length === 0) {
    el.innerHTML = '<div class="hub__empty">暂无消息</div>';
    return;
  }
  var html = '';
  _hubMessages.forEach(function(msg){
    var time = msg.ts ? new Date(msg.ts * 1000).toLocaleTimeString() : '';
    var agentColor = _colorForAgent(msg.frm);
    html += '<div class="hub-msg hub-msg--' + agentColor + '">'
      + '<div class="hub-msg__head">'
      + '<span class="hub-msg__from" style="color:var(--agent-accent,' + _colorHex(agentColor) + ')">' + escHtml(msg.frm) + '</span>'
      + '<span class="hub-msg__arrow">→</span>'
      + '<span class="hub-msg__to">' + escHtml(msg.to === 'all' ? '全部' : msg.to) + '</span>'
      + '<span class="hub-msg__time">' + escHtml(time) + '</span>'
      + '</div>'
      + '<div class="hub-msg__body">' + escHtml(msg.content || '') + '</div>'
      + '</div>';
  });
  el.innerHTML = html;
  // Scroll to top (newest first)
  el.scrollTop = 0;
}

function _colorHex(name) {
  var m = { indigo: '#6366f1', teal: '#14b8a6', pink: '#ec4899', amber: '#f59e0b',
            cyan: '#06b6d4', lime: '#84cc16', rose: '#f43f5e', sky: '#0ea5e9',
            violet: '#8b5cf6', emerald: '#10b981' };
  return m[name] || '#6366f1';
}

// ── SSE 连接 ──
function _connectHubSSE() {
  if (_hubEventSource) { _hubEventSource.close(); _hubEventSource = null; }
  var url = apiUrl('/api/ui/hub/events');
  _hubEventSource = new EventSource(url);
  _hubEventSource.onmessage = function(ev) {
    try {
      var msg = JSON.parse(ev.data);
      // Prepend to history
      _hubMessages.unshift(msg);
      if (_hubMessages.length > 200) _hubMessages.length = 200;
      // Update badge
      _updateHubBadge();
      // Re-render if filter matches
      if (!_hubFilterAgent || msg.frm === _hubFilterAgent || msg.to === _hubFilterAgent) {
        _renderHubMessages();
      }
    } catch(e) { /* ignore parse errors */ }
  };
  _hubEventSource.onerror = function() {
    // Will auto-reconnect by EventSource spec
  };
}

function _updateHubBadge() {
  var btn = document.querySelector('.activity-btn[data-mode="hub"]');
  if (!btn) return;
  var unread = _hubMessages.filter(function(m){ return m.to === 'all' || m.to === ''; }).length;
  var badge = btn.querySelector('.badge');
  if (unread > 0) {
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'badge';
      btn.appendChild(badge);
    }
    badge.textContent = unread > 99 ? '99+' : unread;
  } else if (badge) {
    badge.remove();
  }
}

// ── 发送消息 ──
function _sendHubMessage() {
  var frm = document.getElementById('hubSendFrom').value.trim();
  var to = document.getElementById('hubSendTo').value.trim();
  var content = document.getElementById('hubSendContent').value.trim();
  if (!frm || !content) return;
  _hubApi('/api/ui/hub/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ frm: frm, to: to || 'all', content: content }),
  }).then(function(){
    document.getElementById('hubSendContent').value = '';
  }).catch(function(err){
    console.warn('发送失败:', err);
  });
}

// ── 活动栏按钮 ──
function _activateHubButton() {
  var btn = document.querySelector('.activity-btn[data-mode="hub"]');
  if (btn) return;
  var teamBtn = document.querySelector('.activity-btn[data-mode="team"]');
  if (!teamBtn) return;
  btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'activity-btn';
  btn.dataset.mode = 'hub';
  btn.title = 'Hub';
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.75"/><path d="M12 7v5l3 3" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>';
  teamBtn.parentNode.insertBefore(btn, teamBtn);
  btn.addEventListener('click', function(){
    if (typeof switchActivityMode === 'function') {
      switchActivityMode('hub');
    } else {
      document.querySelectorAll('.activity-btn').forEach(function(b){ b.classList.remove('active'); });
      btn.classList.add('active');
    }
    switchToHubPage();
    _loadHubHistory();
    _connectHubSSE();
  });
}

// ── 初始化 ──
function initHubViewer() {
  _activateHubButton();

  document.getElementById('btnHubSend').addEventListener('click', _sendHubMessage);
  document.getElementById('hubSendContent').addEventListener('keydown', function(e){
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _sendHubMessage(); }
  });
  document.getElementById('btnHubClear').addEventListener('click', function(){
    _hubMessages = [];
    _renderHubMessages();
    _updateHubBadge();
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initHubViewer);
} else {
  initHubViewer();
}
