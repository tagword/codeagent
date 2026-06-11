// Agent 管理面板 v2
// 依赖: 00-utils.js (apiUrl, escapeHtml, escAttr)

var _currentAgents = [];
var _currentPresets = [];
var _currentDetailAgentId = null;

// ── 头像色板 ──
var _AVATAR_COLORS = [
  'default','blue','teal','pink','amber','cyan','rose','violet','emerald','orange'
];

function _avatarColor(agentId) {
  if (!agentId) return 'default';
  var idx = 0;
  for (var i = 0; i < agentId.length; i++) idx = (idx * 31 + agentId.charCodeAt(i)) % _AVATAR_COLORS.length;
  return _AVATAR_COLORS[idx];
}

function _agentMgrApi(path, options) {
  return fetch(apiUrl(path), options || {}).then(function(r){
    if (!r.ok) return r.json().then(function(e){ throw new Error(e.detail || '请求失败') });
    return r.json();
  });
}

// ── 获取当前全局 agentId ──
function _getActiveAgentId() {
  if (typeof agentId !== 'undefined') return agentId;
  return 'default';
}

// ── 搜索过滤 ──
function _filterAgents(agents, query) {
  if (!query || !query.trim()) return agents;
  var q = query.trim().toLowerCase();
  return agents.filter(function(a){
    return (a.id && a.id.toLowerCase().indexOf(q) >= 0)
        || (a.name && a.name.toLowerCase().indexOf(q) >= 0)
        || (a.system_prompt && a.system_prompt.toLowerCase().indexOf(q) >= 0);
  });
}

function _onSearchInput() {
  var q = document.getElementById('agentSearch').value;
  _renderAgentList(_filterAgents(_currentAgents, q));
}

// ── 列表渲染 ──
function _renderAgentList(agents) {
  var el = document.getElementById('agentList');
  var countEl = document.getElementById('agentCount');
  var activeId = _getActiveAgentId();

  if (!agents || agents.length === 0) {
    el.innerHTML = '<div class="agent-list__empty">'
      + (document.getElementById('agentSearch').value
        ? '没有匹配的 Agent，试试其他关键词'
        : '暂无 Agent，点击上方「+ 新建」创建一个')
      + '</div>';
    if (countEl) countEl.textContent = '0';
    return;
  }

  if (countEl) countEl.textContent = agents.length + ' 个';

  var html = '<div class="agent-list__grid">';
  agents.forEach(function(a){
    var name = a.name || a.id;
    var firstChar = name.charAt(0).toUpperCase();
    var desc = a.system_prompt ? a.system_prompt.substring(0, 80) : '';
    if (desc.length >= 80) desc += '…';
    var toolCount = a.tools && a.tools.acquired && a.tools.acquired.allow
      ? a.tools.acquired.allow.length : 0;
    var isActive = a.id === activeId;
    var activeClass = isActive ? ' agent-card--active' : '';
    var color = _avatarColor(a.id);

    html += '<div class="agent-card' + activeClass + '" data-agent-id="' + escAttr(a.id) + '">'
      + '<div class="agent-card__avatar agent-card__avatar--' + color + '">' + escHtml(firstChar) + '</div>'
      + '<div class="agent-card__body">'
      + '<div class="agent-card__name">' + escHtml(name) + '</div>'
      + '<span class="agent-card__id">' + escHtml(a.id) + '</span>'
      + '<div class="agent-card__desc">' + escHtml(desc || '无描述') + '</div>'
      + '<div class="agent-card__meta">'
      + '<span class="agent-card__tag' + (isActive ? ' agent-card__tag--active' : '') + '">'
      + (isActive ? '当前' : toolCount + ' 工具')
      + '</span>'
      + '</div></div>'
      + '<div class="agent-card__actions">'
      + (isActive ? '' : '<button class="agent-card__action-btn agent-card__action-btn--switch" title="切换到此 Agent" data-action="switch">✓</button>')
      + '<button class="agent-card__action-btn" title="编辑" data-action="edit">✎</button>'
      + '<button class="agent-card__action-btn agent-card__action-btn--danger" title="删除" data-action="delete">✕</button>'
      + '</div></div>';
  });
  html += '</div>';
  el.innerHTML = html;

  // 事件绑定
  el.querySelectorAll('.agent-card').forEach(function(card){
    // 点击卡片 → 查看详情
    card.addEventListener('click', function(e){
      // 如果点的是操作按钮，不触发详情
      if (e.target.closest('.agent-card__actions')) return;
      var id = card.dataset.agentId;
      _showAgentDetail(id);
    });

    // 操作按钮
    card.querySelectorAll('[data-action]').forEach(function(btn){
      btn.addEventListener('click', function(e){
        e.stopPropagation();
        var id = card.dataset.agentId;
        var action = btn.dataset.action;
        if (action === 'switch') _agentMgrSwitchAgent(id);
        else if (action === 'edit') _openAgentModal(id);
        else if (action === 'delete') _deleteAgent(id);
      });
    });
  });
}

function _agentMgrSwitchAgent(agentId) {
  // 优先用 23-agent-switcher.js 的切换函数（会同步更新下拉菜单 + WS）
  if (typeof _switchToAgent === 'function') {
    _switchToAgent(agentId);
    _agentSetStatus('ok', '已切换到 ' + agentId);
    // 刷新列表高亮
    setTimeout(function(){
      _renderAgentList(_filterAgents(_currentAgents, document.getElementById('agentSearch').value));
    }, 100);
    return;
  }
  // Fallback
  _agentMgrApi('/api/ui/session/switch-agent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId }),
  }).then(function(){
    if (typeof window.agentId !== 'undefined') window.agentId = agentId;
    _agentSetStatus('ok', '已切换到 ' + agentId);
    _renderAgentList(_filterAgents(_currentAgents, document.getElementById('agentSearch').value));
    if (typeof refreshSessionList === 'function') refreshSessionList();
    if (typeof loadChatTree === 'function') loadChatTree(agentId);
  }).catch(function(err){
    _agentSetStatus('error', err.message);
  });
}

// ── 详情 ──
function _showAgentDetail(agentId) {
  _currentDetailAgentId = agentId;
  _agentMgrApi('/api/ui/agents/' + encodeURIComponent(agentId)).then(function(data){
    var a = data.agent;
    var activeId = _getActiveAgentId();
    var isActive = a.id === activeId;
    var color = _avatarColor(a.id);
    var name = a.name || a.id;
    var firstChar = name.charAt(0).toUpperCase();

    // 显示详情面板，隐藏列表操作栏
    document.getElementById('fieldsetAgents').style.display = 'none';
    document.getElementById('fieldsetAgentDetail').style.display = '';
    document.getElementById('agentDetailTitle').textContent = name;

    // 切换按钮文本
    var switchBtn = document.getElementById('btnAgentSwitch');
    if (isActive) {
      switchBtn.style.display = 'none';
    } else {
      switchBtn.style.display = '';
      switchBtn.textContent = '切换到此 Agent';
    }

    // 编辑/删除按钮绑定
    document.getElementById('btnAgentEdit').onclick = function(){ _openAgentModal(a.id); };
    document.getElementById('btnAgentDelete').onclick = function(){ _deleteAgent(a.id); };
    document.getElementById('btnAgentSwitch').onclick = function(){ _agentMgrSwitchAgent(a.id); };
    document.getElementById('btnAgentDetailBack').onclick = function(){ _backToList(); };

    // 渲染
    var tools = a.tools && a.tools.acquired && a.tools.acquired.allow ? a.tools.acquired.allow : [];
    var promptHtml = a.system_prompt
      ? '<pre class="agent-detail__prompt">' + escHtml(a.system_prompt) + '</pre>'
      : '<pre class="agent-detail__prompt"></pre>';

    var toolsHtml = tools.length === 0
      ? '<span class="agent-detail__tool-none">未配置工具</span>'
      : '<div class="agent-detail__tools">' + tools.map(function(t){
          return '<span class="agent-detail__tool-tag">' + escHtml(t) + '</span>';
        }).join('') + '</div>';

    var html = ''
      + '<div class="agent-detail">'
      // Hero
      + '<div class="agent-detail__hero">'
      + '<div class="agent-card__avatar agent-card__avatar--' + color + '">' + escHtml(firstChar) + '</div>'
      + '<div class="agent-detail__hero-info">'
      + '<div class="agent-detail__hero-name">' + escHtml(name) + '</div>'
      + '<div class="agent-detail__hero-id">' + escHtml(a.id) + '</div>'
      + '<div class="agent-detail__hero-status' + (isActive ? ' agent-detail__hero-status--active' : '') + '">'
      + (isActive ? '🟢 当前活跃' : '⚪ 未激活')
      + '</div></div></div>'
      // Grid: 系统提示 + 工具
      + '<div class="agent-detail__grid">'
      + '<div class="agent-detail__card">'
      + '<div class="agent-detail__card-title">系统提示词</div>'
      + promptHtml
      + '</div>'
      + '<div class="agent-detail__card">'
      + '<div class="agent-detail__card-title">已启用工具 (' + tools.length + ')</div>'
      + toolsHtml
      + '</div></div>'
      // Session list
      + '<div class="agent-detail__section">'
      + '<h4 class="agent-detail__section-title">📋 会话列表</h4>'
      + '<div id="agentSessionList" class="agent-detail__session-list"><div class="agent-loading"><div class="agent-loading__spinner"></div><span>加载中...</span></div></div>'
      + '</div></div>';

    document.getElementById('agentDetailContent').innerHTML = html;
    _loadAgentSessions(agentId);
  }).catch(function(err){
    _agentSetStatus('error', err.message);
  });
}

function _backToList() {
  _currentDetailAgentId = null;
  document.getElementById('fieldsetAgents').style.display = '';
  document.getElementById('fieldsetAgentDetail').style.display = 'none';
}

function _loadAgentSessions(agentId) {
  var url = '/api/ui/agents/' + encodeURIComponent(agentId) + '/sessions';
  fetch(apiUrl(url))
    .then(function(r){ return r.json(); })
    .then(function(data){
      var el = document.getElementById('agentSessionList');
      if (!el) return;
      var sessions = data.sessions || [];
      if (sessions.length === 0) {
        el.innerHTML = '<div class="agent-detail__empty">该 Agent 暂无会话</div>';
        return;
      }
      var html = '';
      sessions.forEach(function(s){
        var title = s.title || s.id || '(未命名)';
        var time = s.updated_at || s.created_at || '';
        if (time) {
          try { time = new Date(time).toLocaleString(); } catch(e) { time = ''; }
        }
        html += '<div class="agent-detail__session-item" data-session-id="' + escAttr(s.id) + '">'
          + '<span class="agent-detail__session-title">' + escHtml(title) + '</span>'
          + (time ? '<span class="agent-detail__session-time">' + escHtml(time) + '</span>' : '')
          + '</div>';
      });
      el.innerHTML = html;
      el.querySelectorAll('.agent-detail__session-item').forEach(function(item){
        item.addEventListener('click', function(){
          var sid = item.dataset.sessionId;
          if (sid && typeof switchToPage === 'function') {
            switchToPage('page-chat');
          }
        });
      });
    })
    .catch(function(){
      var el = document.getElementById('agentSessionList');
      if (el) el.innerHTML = '<span class="agent-detail__empty">加载失败</span>';
    });
}

function _deleteAgent(agentId) {
  if (!confirm('确认删除 Agent "' + agentId + '"？此操作不可撤销。')) return;
  _agentMgrApi('/api/ui/agents/' + encodeURIComponent(agentId), { method: 'DELETE' }).then(function(){
    _agentSetStatus('ok', '已删除 ' + agentId);
    _loadAgentList();
    if (_currentDetailAgentId === agentId) _backToList();
  }).catch(function(err){
    _agentSetStatus('error', err.message);
  });
}

// ── 预设 / 工具列表 ──
function _loadPresets() {
  _agentMgrApi('/api/ui/agent-presets').then(function(data){
    _currentPresets = data.presets || [];
    var sel = document.getElementById('selAgentPreset');
    if (!sel) return;
    sel.innerHTML = '<option value="">— 不使用模板 —</option>';
    _currentPresets.forEach(function(p){
      sel.innerHTML += '<option value="' + escAttr(p.id) + '">' + escHtml(p.name) + '</option>';
    });
  }).catch(function(err){
    console.warn('加载模板失败:', err);
  });
}

function _loadAgentList() {
  _agentMgrApi('/api/ui/agents').then(function(data){
    _currentAgents = data.agents || [];
    var q = document.getElementById('agentSearch').value;
    _renderAgentList(_filterAgents(_currentAgents, q));
  }).catch(function(err){
    _agentSetStatus('error', err.message);
  });
}

function _agentSetStatus(type, msg) {
  var el = document.getElementById('agentStatus');
  if (!el) return;
  el.textContent = msg;
  el.className = 'status-line status-line--' + type;
  if (type === 'ok') {
    setTimeout(function(){ el.textContent = ''; el.className = 'status-line'; }, 3000);
  }
}

// ── 新建/编辑 Modal ──
function _openAgentModal(agentId) {
  var isEdit = !!agentId;
  document.getElementById('agentModalTitle').textContent = isEdit ? '编辑 Agent' : '新建 Agent';
  document.getElementById('agentModal').style.display = '';

  var inpId = document.getElementById('inpAgentId');
  var inpSp = document.getElementById('inpAgentSystemPrompt');

  if (isEdit) {
    inpId.disabled = true;
    _agentMgrApi('/api/ui/agents/' + encodeURIComponent(agentId)).then(function(data){
      inpId.value = data.agent.id;
      inpSp.value = data.agent.system_prompt || '';
      _renderToolCheckboxes(data.agent.tools);
    });
  } else {
    inpId.disabled = false;
    inpId.value = '';
    inpSp.value = '';
    _renderToolCheckboxes(null);
  }
}

function _renderToolCheckboxes(currentTools) {
  var container = document.getElementById('agentToolCheckboxList');
  if (!container) return;
  var allowed = currentTools && currentTools.acquired && currentTools.acquired.allow
    ? currentTools.acquired.allow : [];
  var allTools = [
    'file_read', 'file_write', 'file_edit_tool', 'bash_exec',
    'web_search_tool', 'web_fetch', 'db', 'code_check',
    'grep_tool', 'glob_tool', 'git'
  ];
  var html = '';
  allTools.forEach(function(t){
    var checked = allowed.indexOf(t) >= 0 ? ' checked' : '';
    html += '<label class="checkbox-label"><input type="checkbox" class="agent-tool-cb" value="' + escAttr(t) + '"' + checked + '> ' + t + '</label>';
  });
  container.innerHTML = html;
}

function _saveAgent() {
  var agentId = document.getElementById('inpAgentId').value.trim();
  var systemPrompt = document.getElementById('inpAgentSystemPrompt').value.trim();
  if (!agentId) { _agentSetStatus('error', 'Agent ID 不能为空'); return; }

  var checked = [];
  document.querySelectorAll('#agentToolCheckboxList .agent-tool-cb:checked').forEach(function(cb){
    checked.push(cb.value);
  });
  var tools = { acquired: { allow: checked } };

  var isEdit = !!document.getElementById('inpAgentId').disabled;
  var url = isEdit
    ? '/api/ui/agents/' + encodeURIComponent(agentId)
    : '/api/ui/agents';
  var method = isEdit ? 'PUT' : 'POST';

  var bodyData = { id: agentId, system_prompt: systemPrompt, tools: tools };

  if (!isEdit) {
    var presetId = document.getElementById('selAgentPreset').value;
    if (presetId) {
      var preset = _currentPresets.find(function(p){ return p.id === presetId; });
      if (preset) {
        bodyData.system_prompt = preset.system_prompt;
        bodyData.tools = preset.tools;
      }
    }
  }

  _agentMgrApi(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(bodyData),
  }).then(function(){
    _agentSetStatus('ok', isEdit ? '已更新' : '已创建');
    document.getElementById('agentModal').style.display = 'none';
    _loadAgentList();
    if (isEdit && _currentDetailAgentId === agentId) _showAgentDetail(agentId);
  }).catch(function(err){
    _agentSetStatus('error', err.message);
  });
}

// ── 初始化 ──
function initAgentMgr() {
  document.getElementById('btnAgentCreate').addEventListener('click', function(){ _openAgentModal(); });
  document.getElementById('btnAgentRefresh').addEventListener('click', _loadAgentList);

  // 搜索
  var searchInput = document.getElementById('agentSearch');
  if (searchInput) {
    searchInput.addEventListener('input', _onSearchInput);
  }

  // Modal buttons
  document.getElementById('btnAgentModalClose').addEventListener('click', function(){
    document.getElementById('agentModal').style.display = 'none';
  });
  document.getElementById('btnAgentModalCancel').addEventListener('click', function(){
    document.getElementById('agentModal').style.display = 'none';
  });
  document.getElementById('btnAgentModalSave').addEventListener('click', _saveAgent);

  // Preset select
  var presetSel = document.getElementById('selAgentPreset');
  if (presetSel) {
    presetSel.addEventListener('change', function(){
      var presetId = this.value;
      if (!presetId) return;
      var preset = _currentPresets.find(function(p){ return p.id === presetId; });
      if (!preset) return;
      document.getElementById('inpAgentSystemPrompt').value = preset.system_prompt || '';
      if (preset.tools) _renderToolCheckboxes(preset.tools);
    });
  }

  _loadPresets();
  _loadAgentList();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAgentMgr);
} else {
  initAgentMgr();
}
