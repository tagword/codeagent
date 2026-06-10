// Agent 管理面板
// 依赖: 00-utils.js (apiUrl, escapeHtml)
// API: /api/ui/agents, /api/ui/agent-presets

var _currentAgents = [];
var _currentPresets = [];

function _agentMgrApi(path, options) {
  return fetch(apiUrl(path), options || {}).then(function(r){
    if (!r.ok) return r.json().then(function(e){ throw new Error(e.detail || '请求失败') });
    return r.json();
  });
}

// ── 列表渲染 ──────────────────────────────────────────

function _renderAgentList(agents) {
  var el = document.getElementById('agentList');
  if (!agents || agents.length === 0) {
    el.innerHTML = '<div class="agent-list__empty">暂无 Agent</div>';
    return;
  }
  var html = '<div class="agent-list__grid">';
  agents.forEach(function(a){
    var name = a.name || a.id;
    var desc = a.system_prompt ? a.system_prompt.substring(0, 60) : '';
    if (desc.length >= 60) desc += '…';
    var toolCount = a.tools && a.tools.acquired && a.tools.acquired.allow
      ? a.tools.acquired.allow.length : 0;
    html += '<div class="agent-card" data-agent-id="' + escAttr(a.id) + '">'
      + '<div class="agent-card__icon">🤖</div>'
      + '<div class="agent-card__body">'
      + '<div class="agent-card__name">' + escHtml(name) + '</div>'
      + '<div class="agent-card__desc">' + escHtml(desc || '无描述') + '</div>'
      + '<div class="agent-card__meta">'
      + '<span class="agent-card__tools">' + toolCount + ' 个工具</span>'
      + '<span class="agent-card__id">' + escHtml(a.id) + '</span>'
      + '</div></div>'
      + '</div>';
  });
  html += '</div>';
  el.innerHTML = html;

  // 点击卡片查看详情
  el.querySelectorAll('.agent-card').forEach(function(card){
    card.addEventListener('click', function(){
      var id = card.dataset.agentId;
      _showAgentDetail(id);
    });
  });
}

function _showAgentDetail(agentId) {
  _agentMgrApi('/api/ui/agents/' + encodeURIComponent(agentId)).then(function(data){
    var a = data.agent;
    var fieldset = document.getElementById('fieldsetAgentDetail');
    fieldset.style.display = '';
    document.getElementById('agentDetailTitle').textContent = 'Agent: ' + (a.name || a.id);

    var html = '<div class="agent-detail">'
      + '<div class="agent-detail__row"><strong>ID:</strong> ' + escHtml(a.id) + '</div>'
      + '<div class="agent-detail__row"><strong>系统提示:</strong></div>'
      + '<pre class="agent-detail__pre">' + escHtml(a.system_prompt || '(空)') + '</pre>'
      + '<div class="agent-detail__row"><strong>工具:</strong></div>'
      + '<div class="agent-detail__tools">';
    var tools = a.tools && a.tools.acquired && a.tools.acquired.allow ? a.tools.acquired.allow : [];
    if (tools.length === 0) {
      html += '<span class="agent-detail__tool-none">未配置</span>';
    } else {
      tools.forEach(function(t){
        html += '<span class="agent-detail__tool-tag">' + escHtml(t) + '</span>';
      });
    }
    html += '</div></div>';
    document.getElementById('agentDetailContent').innerHTML = html;

    document.getElementById('btnAgentEdit').onclick = function(){ _openAgentModal(a.id); };
    document.getElementById('btnAgentDelete').onclick = function(){ _deleteAgent(a.id); };
  }).catch(function(err){
    _agentSetStatus('error', err.message);
  });
}

function _deleteAgent(agentId) {
  if (!confirm('确认删除 Agent "' + agentId + '"？')) return;
  _agentMgrApi('/api/ui/agents/' + encodeURIComponent(agentId), { method: 'DELETE' }).then(function(){
    _agentSetStatus('ok', '已删除');
    _loadAgentList();
    document.getElementById('fieldsetAgentDetail').style.display = 'none';
  }).catch(function(err){
    _agentSetStatus('error', err.message);
  });
}

// ── 模板 / 工具列表 ─────────────────────────────────────

function _loadPresets() {
  _agentMgrApi('/api/ui/agent-presets').then(function(data){
    _currentPresets = data.presets || [];
    var sel = document.getElementById('selAgentPreset');
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
    _renderAgentList(_currentAgents);
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

// ── 创建 / 编辑 Modal ─────────────────────────────────

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
  var allowed = currentTools && currentTools.acquired && currentTools.acquired.allow
    ? currentTools.acquired.allow : [];
  // 展示常用工具列表供勾选
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

  // Collect checked tools
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

  var bodyData = {
    id: agentId,
    system_prompt: systemPrompt,
    tools: tools,
  };

  // If creating from preset
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
    if (isEdit) _showAgentDetail(agentId);
  }).catch(function(err){
    _agentSetStatus('error', err.message);
  });
}

// ── 初始化 ─────────────────────────────────────────────

function initAgentMgr() {
  // Buttons
  document.getElementById('btnAgentCreate').addEventListener('click', function(){ _openAgentModal(); });
  document.getElementById('btnAgentRefresh').addEventListener('click', _loadAgentList);
  document.getElementById('btnAgentModalClose').addEventListener('click', function(){
    document.getElementById('agentModal').style.display = 'none';
  });
  document.getElementById('btnAgentModalCancel').addEventListener('click', function(){
    document.getElementById('agentModal').style.display = 'none';
  });
  document.getElementById('btnAgentModalSave').addEventListener('click', _saveAgent);

  // Preset select change → auto-fill
  document.getElementById('selAgentPreset').addEventListener('change', function(){
    var presetId = this.value;
    if (!presetId) return;
    var preset = _currentPresets.find(function(p){ return p.id === presetId; });
    if (!preset) return;
    document.getElementById('inpAgentSystemPrompt').value = preset.system_prompt || '';
    if (preset.tools) {
      _renderToolCheckboxes(preset.tools);
    }
  });

  _loadPresets();
  _loadAgentList();
}

// Auto-init when DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAgentMgr);
} else {
  initAgentMgr();
}
