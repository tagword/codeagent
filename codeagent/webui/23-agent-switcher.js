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
      // 切换成功 — 重新加载聊天会话列表
      console.log('切换到 Agent:', agentId);
      if (typeof loadChatTree === 'function') loadChatTree(agentId);
      // 如果当前在聊天页且有会话列表，刷新它
      if (typeof addTreeSession === 'function') {
        // 会话列表会在 tree 加载时自动更新
      }
      // 更新所有 agent 相关 UI 的选中状态
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
