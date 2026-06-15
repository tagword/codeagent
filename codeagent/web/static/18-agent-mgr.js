/* ================================================================
 * 18-agent-mgr.js  —  单 Agent 配置页（v2）
 *
 * 简化版：去掉多 Agent 列表/搜索/创建/删除/切换，
 * 直接展示当前 Agent 的详情 + 编辑能力（描述/系统提示/工具）。
 * Skills/SysPrompt MD/外部集成由 13a-skills.js / 13b-tools.js 管理。
 * ================================================================ */

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

// ── 渲染当前 Agent 详情 ──
function renderCurrentAgent() {
  var aid = typeof agentId !== 'undefined' ? agentId : 'default';
  _agentMgrApi('/api/ui/agents/' + encodeURIComponent(aid))
    .then(function(data) {
      var a = data.agent;
      if (!a) { _setStatus('error', '未找到 Agent: ' + aid); return; }
      _renderAgentDetail(a);
      // 加载技能和 MD 文件
      if (typeof loadSkills === 'function') loadSkills(a.id);
      if (typeof loadMdFiles === 'function') setTimeout(function(){ loadMdFiles(a.id); }, 50);
    })
    .catch(function(err) {
      _setStatus('error', '加载 Agent 失败: ' + err.message);
    });
}

function _renderAgentDetail(a) {
  var color = _avatarColor(a.id);
  var name = a.name || a.id;
  var firstChar = name.charAt(0).toUpperCase();
  var isActive = a.id === (typeof agentId !== 'undefined' ? agentId : 'default');
  var tools = a.tools && a.tools.acquired && a.tools.acquired.allow ? a.tools.acquired.allow : [];

  document.getElementById('agentDetailTitle').textContent = 'Agent 配置: ' + (a.name || a.id);

  // 描述
  var descHtml = '<span class="agent-detail__desc-text">' + escHtml(a.description || '') + '</span>'
    + '<button class="btn btn--ghost btn--sm agent-detail__desc-edit-btn" onclick="_editDescription(\'' + escAttr(a.id) + '\')">✎</button>';

  // 工具
  var toolsHtml;
  if (!a.tools_configured) {
    toolsHtml = '<span class="agent-detail__tool-none agent-detail__tool-none--unrestricted">未限制（全部工具开放）</span>'
      + '<button class="btn btn--ghost btn--sm agent-detail__tool-edit-btn" onclick="_startEditTools(\'' + escAttr(a.id) + '\')">✎ 编辑</button>';
  } else if (tools.length === 0) {
    toolsHtml = '<span class="agent-detail__tool-none">仅基础工具</span>'
      + '<button class="btn btn--ghost btn--sm agent-detail__tool-edit-btn" onclick="_startEditTools(\'' + escAttr(a.id) + '\')">✎ 编辑</button>';
  } else {
    toolsHtml = '<div class="agent-detail__tools">' + tools.map(function(t){
        return '<span class="agent-detail__tool-tag">' + escHtml(t) + '</span>';
      }).join('') + '</div>'
      + '<button class="btn btn--ghost btn--sm agent-detail__tool-edit-btn" onclick="_startEditTools(\'' + escAttr(a.id) + '\')">✎ 编辑</button>';
  }

  var html = ''
    + '<div class="agent-detail">'
    // Hero
    + '<div class="agent-detail__hero">'
    + '<div class="agent-card__avatar agent-card__avatar--' + color + '">' + escHtml(firstChar) + '</div>'
    + '<div class="agent-detail__hero-info">'
    + '<div class="agent-detail__hero-name">' + escHtml(name) + '</div>'
    + '<div class="agent-detail__hero-id">' + escHtml(a.id) + '</div>'
    + '<div class="agent-detail__hero-desc" id="agentDetailDesc">' + descHtml + '</div>'
    + '<div class="agent-detail__hero-status' + (isActive ? ' agent-detail__hero-status--active' : '') + '">'
    + (isActive ? '🟢 当前活跃' : '⚪ 未激活') + '</div>'
    + '</div></div>'
    // Grid
    + '<div class="agent-detail__grid">'
    + '<div class="agent-detail__card" id="agentToolsCard" style="grid-column:1/-1">'
    + '<div class="agent-detail__card-title">已启用工具' + (a.tools_configured ? ' (' + tools.length + ')' : '') + '</div>'
    + '<div id="agentToolsContent">' + toolsHtml + '</div>'
    + '</div></div>'
    + '</div>';

  document.getElementById('agentDetailContent').innerHTML = html;
}

// ── 编辑工具 ──
function _startEditTools(agentId) {
  var contentEl = document.getElementById('agentToolsContent');
  if (!contentEl) return;
  contentEl.innerHTML = '<div class="agent-loading"><div class="agent-loading__spinner"></div><span>加载工具列表...</span></div>';

  fetch(apiUrl('/api/ui/tools/available'))
    .then(function(r){ return r.json(); })
    .then(function(data){
      var allTools = data.tools || [];
      return fetch(apiUrl('/api/ui/agents/' + encodeURIComponent(agentId)))
        .then(function(r){ return r.json(); })
        .then(function(d){
          var a = d.agent;
          var allowed = a.tools && a.tools.acquired && a.tools.acquired.allow ? a.tools.acquired.allow : [];
          return {allTools: allTools, allowed: allowed, agentId: agentId};
        });
    })
    .then(function(ctx){
      var html = '<div class="agent-tool-edit">';
      ctx.allTools.forEach(function(t){
        var checked = ctx.allowed.indexOf(t) >= 0 ? ' checked' : '';
        html += '<label class="checkbox-label"><input type="checkbox" class="agent-tool-cb" value="' + escAttr(t) + '"' + checked + '> ' + escHtml(t) + '</label>';
      });
      html += '</div>'
        + '<div class="agent-detail__tool-actions">'
        + '<button class="btn btn--primary btn--sm" onclick="_saveTools(\'' + escAttr(ctx.agentId) + '\')">💾 保存</button>'
        + '<button class="btn btn--ghost btn--sm" onclick="renderCurrentAgent()">取消</button>'
        + '</div>';
      contentEl.innerHTML = html;
    })
    .catch(function(err){
      contentEl.innerHTML = '<span class="agent-detail__tool-none">加载失败: ' + escHtml(err.message) + '</span>'
        + '<button class="btn btn--ghost btn--sm" onclick="renderCurrentAgent()">返回</button>';
    });
}

function _saveTools(agentId) {
  var checked = [];
  document.querySelectorAll('#agentToolsContent .agent-tool-cb:checked').forEach(function(cb){
    checked.push(cb.value);
  });
  var toolsData = { acquired: { allow: checked } };

  fetch(apiUrl('/api/ui/agents/' + encodeURIComponent(agentId)), {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ tools: toolsData })
  })
    .then(function(r){ return r.json(); })
    .then(function(){
      _setStatus('ok', '工具已更新');
      renderCurrentAgent();
    })
    .catch(function(err){
      _setStatus('error', '保存失败: ' + err.message);
    });
}

// ── 编辑描述 ──
function _editDescription(agentId) {
  var descEl = document.getElementById('agentDetailDesc');
  if (!descEl) return;
  var current = descEl.textContent.replace('✎', '').trim();
  descEl.innerHTML = '<input type="text" class="input agent-detail__desc-input" id="inpAgentDesc" value="' + escAttr(current) + '" placeholder="一句话描述这个 Agent 的用途" />'
    + '<button class="btn btn--primary btn--sm" onclick="_saveDescription(\'' + escAttr(agentId) + '\')">保存</button>'
    + '<button class="btn btn--ghost btn--sm" onclick="renderCurrentAgent()">取消</button>';
  var inp = document.getElementById('inpAgentDesc');
  if (inp) { inp.focus(); inp.select(); }
}

function _saveDescription(agentId) {
  var desc = document.getElementById('inpAgentDesc') ? document.getElementById('inpAgentDesc').value.trim() : '';
  fetch(apiUrl('/api/ui/agents/' + encodeURIComponent(agentId)), {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ description: desc })
  })
    .then(function(r){ return r.json(); })
    .then(function(){
      _setStatus('ok', '描述已更新');
      renderCurrentAgent();
    })
    .catch(function(err){
      _setStatus('error', '保存失败: ' + err.message);
    });
}

// ── 状态提示 ──
function _setStatus(type, msg) {
  var el = document.getElementById('agentStatus');
  if (!el) return;
  el.textContent = msg;
  el.className = 'status-line status-line--' + type;
  if (type === 'ok') {
    setTimeout(function(){ el.textContent = ''; el.className = 'status-line'; }, 3000);
  }
}

// ── 初始化 ──
function initAgentMgr() {
  renderCurrentAgent();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAgentMgr);
} else {
  initAgentMgr();
}
