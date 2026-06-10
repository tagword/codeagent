// Agent 聊天切换器 — 聊天顶部下拉框
// 显示所有可用 Agent，切换时更新当前会话上下文

var _agentSwitcherInitialized = false;
var _agentSwitcherAgents = [];
var _currentSwitcherAgentId = null;

function initAgentSwitcher() {
  if (_agentSwitcherInitialized) return;
  _agentSwitcherInitialized = true;

  var sel = document.getElementById('agentSwitcher');
  if (!sel) return;

  // 加载 agent 列表
  _refreshAgentSwitcher();

  // 切换事件
  sel.addEventListener('change', function(){
    var targetId = this.value;
    if (!targetId || targetId === _currentSwitcherAgentId) return;
    _switchToAgent(targetId);
  });
}

function _refreshAgentSwitcher() {
  fetch(apiUrl('/api/ui/agents'))
    .then(function(r){ return r.json(); })
    .then(function(data){
      _agentSwitcherAgents = data.agents || [];
      var sel = document.getElementById('agentSwitcher');
      if (!sel) return;
      sel.innerHTML = '';
      _agentSwitcherAgents.forEach(function(a){
        var name = a.name || a.id;
        var opt = document.createElement('option');
        opt.value = a.id;
        opt.textContent = name;
        sel.appendChild(opt);
      });
      // 如果当前有选中的 agent，保持选中
      if (_currentSwitcherAgentId) {
        sel.value = _currentSwitcherAgentId;
      }
    })
    .catch(function(err){
      console.warn('加载 Agent 列表失败:', err);
    });
}

function _switchToAgent(agentId) {
  if (!agentId) return;
  _currentSwitcherAgentId = agentId;

  var sel = document.getElementById('agentSwitcher');
  if (sel) sel.value = agentId;

  // 通知后端切换
  fetch(apiUrl('/api/ui/session/switch-agent'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId }),
  })
    .then(function(r){ return r.json(); })
    .then(function(data){
      // 更新全局 agentId（01c-session-identity.js 中定义的可写变量）
      if (typeof window.agentId !== 'undefined') {
        window.agentId = agentId;
      }

      // 更新会话 ID — 如果有当前会话则切换到该 agent 的会话
      if (data.sessions && data.sessions.length > 0) {
        var firstSession = data.sessions[0];
        if (firstSession.id && typeof setSessionId === 'function') {
          setSessionId(firstSession.id);
        }
      }

      // 重新连接 WebSocket（带上新的 agent_id）
      if (typeof reconnectWsForSession === 'function') {
        reconnectWsForSession();
      }

      // 重新加载聊天树
      if (typeof loadChatTree === 'function') {
        loadChatTree(agentId);
      }

      // 更新 session 列表
      if (typeof refreshSessionList === 'function') {
        refreshSessionList();
      }

      // 更新所有 agent 卡片高亮
      document.querySelectorAll('[data-agent-id]').forEach(function(el){
        el.classList.toggle('agent-card--active', el.dataset.agentId === agentId);
      });
    })
    .catch(function(err){
      console.error('切换 Agent 失败:', err);
    });
}

// 在页面初始化完成后执行
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAgentSwitcher);
} else {
  initAgentSwitcher();
}
