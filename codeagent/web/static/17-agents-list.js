/* ═══════════════════════════════════════════════════════════════
 * 17-agents-list.js — page-agent 多 Agent 管理：列表 + 切换 + 新建/删除
 *
 * 定位（与 page-config 的分工）：
 *   page-agent  = 多 Agent 管理（agent 列表、选中详情、团队组合）
 *   page-config = 系统级配置（不含 agent_id）
 *
 * 后端 API 早已完备（/api/ui/agents CRUD），本模块把列表能力接出来。
 * 与 18-agent-mgr.js 的分工：
 *   本模块   → 左侧 agent 列表（选择 / 新建 / 删除）
 *   18-*.js  → 右侧选中 agent 的详情（描述 / 工具编辑）
 * ═══════════════════════════════════════════════════════════════ */

var _agentListCache = [];
var _agentListFilter = '';

/** 拉取 agent 列表并渲染。 */
function refreshAgentList() {
  var box = document.getElementById('agentListItems');
  if (!box) return;
  box.innerHTML = '<div class="agent-list__loading">加载中…</div>';

  fetch(apiUrl('/api/ui/agents'))
    .then(function (r) { return r.json(); })
    .then(function (d) {
      _agentListCache = (d && d.agents) || [];
      _renderAgentList();
    })
    .catch(function (e) {
      box.innerHTML = '<div class="agent-list__error">加载失败：' + escHtml(String(e)) + '</div>';
    });
}

/** 按当前过滤词渲染列表。 */
function _renderAgentList() {
  var box = document.getElementById('agentListItems');
  if (!box) return;

  var q = (_agentListFilter || '').trim().toLowerCase();
  var items = _agentListCache.filter(function (a) {
    if (!q) return true;
    return (a.id || '').toLowerCase().indexOf(q) >= 0
        || (a.name || '').toLowerCase().indexOf(q) >= 0
        || (a.description || '').toLowerCase().indexOf(q) >= 0;
  });

  var countEl = document.getElementById('agentListCount');
  if (countEl) countEl.textContent = '(' + items.length + ')';

  if (!items.length) {
    box.innerHTML = '<div class="agent-list__empty">'
      + (_agentListCache.length ? '无匹配的 Agent' : '还没有 Agent，点击「＋ 新建」创建')
      + '</div>';
    return;
  }

  var activeId = (typeof agentId !== 'undefined' ? agentId : 'default');
  box.innerHTML = items.map(function (a) {
    var color = _avatarColor(a.id);
    var name = a.name || a.id;
    var firstChar = name.charAt(0).toUpperCase();
    var isActive = a.id === activeId;
    var desc = a.description || '';
    var toolCount = (a.tools && a.tools.acquired && a.tools.acquired.allow)
      ? a.tools.acquired.allow.length : 0;
    var toolLabel = a.tools_configured ? (toolCount + ' 工具') : '全部工具';

    return ''
      + '<div class="agent-list__item' + (isActive ? ' agent-list__item--active' : '') + '"'
      + ' data-agent-id="' + escAttr(a.id) + '"'
      + ' onclick="selectAgentFromList(\'' + escAttr(a.id) + '\')">'
      + '<div class="agent-card__avatar agent-card__avatar--' + color + '">' + escHtml(firstChar) + '</div>'
      + '<div class="agent-list__meta">'
      + '<div class="agent-list__name">' + escHtml(name)
      + (isActive ? ' <span class="agent-list__badge">当前</span>' : '') + '</div>'
      + '<div class="agent-list__sub">' + escHtml(a.id) + ' · ' + escHtml(toolLabel) + '</div>'
      + (desc ? '<div class="agent-list__desc">' + escHtml(desc) + '</div>' : '')
      + '</div>'
      + '<button class="agent-list__del" title="删除该 Agent"'
      + ' onclick="event.stopPropagation();deleteAgentFromList(\'' + escAttr(a.id) + '\')">✕</button>'
      + '</div>';
  }).join('');
}

/** 列表项过滤输入。 */
function filterAgentList(value) {
  _agentListFilter = value || '';
  _renderAgentList();
}

/** 点击列表项：切换当前活跃 agent 并刷新详情。 */
function selectAgentFromList(aid) {
  if (!aid) return;
  fetch(apiUrl('/api/ui/agents/' + encodeURIComponent(aid)))
    .then(function (r) { return r.json(); })
    .then(function () {
      // 更新全局 agentId 并触发详情刷新（18-agent-mgr.js 的 renderCurrentAgent）
      if (typeof agentId !== 'undefined') {
        agentId = aid;
        try { localStorage.setItem('seed_active_agent_id', aid); } catch (e) {}
      }
      if (typeof renderCurrentAgent === 'function') renderCurrentAgent();
      _renderAgentList();
      if (typeof _setStatus === 'function') _setStatus('ok', '已选中 ' + aid);
    })
    .catch(function (e) {
      if (typeof _setStatus === 'function') _setStatus('err', '切换失败：' + e);
    });
}

/** 新建 agent（弹窗输入 id + 可选描述）。 */
function createAgentFromList() {
  var aid = (window.prompt('新 Agent ID（字母/数字/下划线/连字符）：') || '').trim();
  if (!aid) return;
  var desc = (window.prompt('描述（可选）：') || '').trim();

  fetch(apiUrl('/api/ui/agents'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: aid, description: desc })
  })
    .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
    .then(function (res) {
      if (!res.ok) {
        if (typeof _setStatus === 'function') _setStatus('err', res.d.detail || '创建失败');
        return;
      }
      if (typeof _setStatus === 'function') _setStatus('ok', '已创建 ' + aid);
      refreshAgentList();
    })
    .catch(function (e) {
      if (typeof _setStatus === 'function') _setStatus('err', '创建失败：' + e);
    });
}

/** 删除 agent（二次确认）。 */
function deleteAgentFromList(aid) {
  if (!aid) return;
  if (aid === (typeof agentId !== 'undefined' ? agentId : 'default')) {
    if (typeof _setStatus === 'function') _setStatus('err', '不能删除当前活跃 Agent');
    return;
  }
  if (!window.confirm('确定删除 Agent「' + aid + '」？此操作不可撤销。')) return;

  fetch(apiUrl('/api/ui/agents/' + encodeURIComponent(aid)), { method: 'DELETE' })
    .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
    .then(function (res) {
      if (!res.ok) {
        if (typeof _setStatus === 'function') _setStatus('err', res.d.detail || '删除失败');
        return;
      }
      if (typeof _setStatus === 'function') _setStatus('ok', '已删除 ' + aid);
      refreshAgentList();
    })
    .catch(function (e) {
      if (typeof _setStatus === 'function') _setStatus('err', '删除失败：' + e);
    });
}

/** 初始化：页面切到 agent 时刷新列表。 */
function initAgentsList() {
  refreshAgentList();
  // 若已有 switchToPage 钩子则挂载；否则监听活动栏点击
  document.addEventListener('click', function (ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('[data-mode="agent"]') : null;
    if (el) refreshAgentList();
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAgentsList);
} else {
  initAgentsList();
}
