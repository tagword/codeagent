// 团队协作面板 — 多 Agent 真实协作（列表 / 新建 / 运行 / 实时步骤轮询）
// 挂载在 Agent 页 page-agent 的 #fieldsetTeams 内。
// 后端：/api/ui/teams*  (CRUD)  +  /api/ui/teams/{id}/run  +  /api/ui/runs*

var _teamsCache = [];
var _agentsCache = [];
var _teamPollTimers = {}; // run_id -> interval id

function _teamsApi(path, options) {
  return fetch(apiUrl(path), options || {}).then(function(r){
    if (!r.ok) return r.json().then(function(e){ throw new Error(e.detail || '请求失败') });
    return r.json();
  });
}

var _MODE_LABEL = { sequential: '顺序逐个', parallel: '并行处理', manager: 'PM 拆解分派' };
var _MODE_ICON  = { sequential: '🔁', parallel: '⚡', manager: '🧭' };
var _STEP_ICON  = { 'manager-pm': '🧠', 'manager-worker': '🛠', sequential: '🔁', parallel: '⚡' };
var _STATUS_ICON= { pending:'⏳', running:'🔄', done:'✅', failed:'❌', timeout:'⏱' };

function _teamStatusIcon(s) { return _STATUS_ICON[s] || '⚪'; }

// ── 加载 ────────────────────────────────────────────────
function loadTeamsPanel() {
  var statusEl = document.getElementById('teamsStatus');
  var listEl = document.getElementById('teamsList');
  if (!listEl) return;
  listEl.innerHTML = '<div class="agent-loading"><div class="agent-loading__spinner"></div><span>加载团队...</span></div>';
  if (statusEl) statusEl.textContent = '';

  // 并行拉 agents + teams
  Promise.all([
    _teamsApi('/api/ui/agents').then(function(d){ _agentsCache = d.agents || []; }).catch(function(){ _agentsCache = []; }),
    _teamsApi('/api/ui/teams').then(function(d){ _teamsCache = d.teams || []; }).catch(function(){ _teamsCache = []; })
  ]).then(function(){
    _renderTeamsList();
  }).catch(function(err){
    listEl.innerHTML = '<div class="teams__error">加载失败: ' + escHtml(err.message) + '</div>'
      + '<button class="btn btn--ghost btn--sm" onclick="loadTeamsPanel()">重试</button>';
  });
}

// ── 列表渲染 ────────────────────────────────────────────
function _renderTeamsList() {
  var listEl = document.getElementById('teamsList');
  if (!listEl) return;
  if (_teamsCache.length === 0) {
    listEl.innerHTML = '<div class="teams__empty">还没有团队。点击「+ 新建团队」创建第一个协作团队。</div>';
    return;
  }
  listEl.innerHTML = _teamsCache.map(function(t){
    var mode = t.mode || 'sequential';
    var members = (t.members || []).map(function(m){
      var id = typeof m === 'string' ? m : (m && (m.id || m.agent_id || m.role)) || '';
      var role = (typeof m === 'object' && m) ? (m.role_prompt || m.system_prompt || '') : '';
      var roleBadge = role ? '<span class="team-member-role-badge" title="' + escAttr(role) + '">' + escHtml(role.slice(0, 18) + (role.length > 18 ? '…' : '')) + '</span>' : '';
      return '<span class="team-member-tag">' + escHtml(id) + roleBadge + '</span>';
    }).join('');
    var pm = t.manager_id ? '<span class="teams__pm">PM: ' + escHtml(t.manager_id) + '</span>' : '';
    return '<div class="team-card" data-team-id="' + escAttr(t.id) + '">'
      + '<div class="team-card__head">'
      + '<div class="team-card__title">' + _MODE_ICON[mode] + ' ' + escHtml(t.name || t.id) + '</div>'
      + '<div class="team-card__actions">'
      + '<button class="btn btn--primary btn--sm" onclick="openTeamRun(\'' + escAttr(t.id) + '\')">▶ 运行</button>'
      + '<button class="btn btn--ghost btn--sm" onclick="openTeamEdit(\'' + escAttr(t.id) + '\')">编辑</button>'
      + '<button class="btn btn--ghost btn--sm" onclick="toggleTeamDetail(\'' + escAttr(t.id) + '\')">详情</button>'
      + '<button class="btn btn--ghost btn--sm team-del-btn" onclick="deleteTeam(\'' + escAttr(t.id) + '\')">🗑</button>'
      + '</div></div>'
      + '<div class="team-card__meta">'
      + '<span class="team-mode-badge">' + escHtml(_MODE_LABEL[mode] || mode) + '</span>'
      + pm
      + '<span class="team-card__desc">' + escHtml(t.description || '') + '</span>'
      + '</div>'
      + '<div class="team-card__members">' + members + '</div>'
      + '<div class="team-card__detail" id="teamDetail-' + escAttr(t.id) + '" style="display:none;"></div>'
      + '</div>';
  }).join('');
}

function toggleTeamDetail(teamId) {
  var el = document.getElementById('teamDetail-' + teamId);
  if (!el) return;
  if (el.style.display !== 'none') { el.style.display = 'none'; return; }
  var t = _teamsCache.find(function(x){ return x.id === teamId; });
  if (!t) return;
  el.style.display = 'block';
  el.innerHTML = '<div class="team-detail">'
    + '<div class="team-detail__row"><span class="team-detail__label">ID</span>' + escHtml(t.id) + '</div>'
    + '<div class="team-detail__row"><span class="team-detail__label">模式</span>' + escHtml(_MODE_LABEL[t.mode] || t.mode) + '</div>'
    + '<div class="team-detail__row"><span class="team-detail__label">成员</span>' + escHtml((t.members||[]).join(', ')) + '</div>'
    + '<div class="team-detail__row"><span class="team-detail__label">PM</span>' + escHtml(t.manager_id || '(第一个成员)') + '</div>'
    + '<div class="team-detail__row"><span class="team-detail__label">错误策略</span>' + escHtml(t.error_policy || 'stop') + '</div>'
    + '<div class="team-detail__row"><span class="team-detail__label">超时</span>' + escHtml(String(t.timeout_seconds || 300)) + 's</div>'
    + '</div>';
}

// ── 删除 ────────────────────────────────────────────────
function deleteTeam(teamId) {
  if (!confirm('确定删除团队「' + teamId + '」？')) return;
  _teamsApi('/api/ui/teams/' + encodeURIComponent(teamId), { method: 'DELETE' })
    .then(function(){ setTeamsStatus('已删除团队 ' + teamId, 'ok'); loadTeamsPanel(); })
    .catch(function(err){ setTeamsStatus('删除失败: ' + err.message, 'err'); });
}

function setTeamsStatus(msg, kind) {
  var el = document.getElementById('teamsStatus');
  if (el) { el.textContent = msg; el.className = 'status-line ' + (kind === 'err' ? 'status-line--err' : (kind === 'ok' ? 'status-line--ok' : '')); }
}

// ── 新建 / 编辑 ─────────────────────────────────────────
function openTeamNew() {
  _renderTeamForm(null);
}

function openTeamEdit(teamId) {
  var t = _teamsCache.find(function(x){ return x.id === teamId; });
  if (!t) return;
  _renderTeamForm(t);
}

function _memberRoleOf(m) {
  if (typeof m === 'object' && m) return (m.role_prompt || m.system_prompt || '').trim();
  return '';
}

function _renderTeamForm(team) {
  var listEl = document.getElementById('teamsList');
  if (!listEl) return;
  var agents = _agentsCache;
  var agentOpts = agents.length
    ? agents.map(function(a){ return '<option value="' + escAttr(a.id) + '">' + escHtml(a.id) + '</option>'; }).join('')
    : '<option value="default">default</option>';
  var isEdit = !!team;
  var existing = (team && team.members) || [];
  // 已选成员 id -> role 映射（编辑时预填）
  var selRoles = {};
  existing.forEach(function(m){
    var id = typeof m === 'string' ? m : (m && (m.id || m.agent_id || m.role)) || '';
    selRoles[id] = _memberRoleOf(m);
  });
  var memberRows = agents.map(function(a){
    var checked = selRoles[a.id] !== undefined ? ' checked' : '';
    var roleVal = selRoles[a.id] !== undefined ? selRoles[a.id] : '';
    var disabled = selRoles[a.id] !== undefined ? '' : ' disabled';
    return '<div class="team-member-row">'
      + '<label class="team-member-check"><input type="checkbox" class="tfMember" value="' + escAttr(a.id) + '"' + checked + ' onchange="toggleMemberRole(this)" /> '
      + '<span class="team-member-check__id">' + escHtml(a.id) + '</span></label>'
      + '<input type="text" class="input team-member-role" id="tfRole-' + escAttr(a.id) + '" value="' + escAttr(roleVal) + '" placeholder="角色提示词（可选）"' + disabled + ' />'
      + '</div>';
  }).join('');

  listEl.innerHTML = '<div class="team-form" id="teamForm">'
    + '<div class="team-form__title">' + (isEdit ? '编辑团队「' + escHtml(team.id) + '」' : '新建团队') + '</div>'
    + (isEdit ? '' : '<div class="team-form__row"><label>团队 ID</label><input class="input" id="tfId" placeholder="如 dev-team" /></div>')
    + '<div class="team-form__row"><label>名称</label><input class="input" id="tfName" value="' + (isEdit ? escAttr(team.name || '') : '') + '" placeholder="如 开发团队" /></div>'
    + '<div class="team-form__row"><label>模式</label>'
    + '<select class="input" id="tfMode">'
    + '<option value="sequential"' + (isEdit && team.mode === 'sequential' ? ' selected' : '') + '>顺序逐个（前一步产出传给下一步）</option>'
    + '<option value="parallel"' + (isEdit && team.mode === 'parallel' ? ' selected' : '') + '>并行处理（所有成员同输入）</option>'
    + '<option value="manager"' + (isEdit && team.mode === 'manager' ? ' selected' : '') + '>PM 拆解分派（首个成员当 PM）</option>'
    + '</select></div>'
    + '<div class="team-form__row" style="align-items:flex-start;"><label>成员 + 角色</label>'
    + '<div class="team-form__members">'
    + '<div class="team-form__members-hint">勾选成员并填写其角色提示词（如"你是前端工程师"），决定该成员以何种身份工作。留空则用默认身份。</div>'
    + memberRows
    + '</div></div>'
    + '<div class="team-form__row"><label>PM（manager 模式）</label>'
    + '<select class="input" id="tfManager"><option value="">(第一个成员)</option>'
    + agents.map(function(a){
        var sel = (isEdit && team.manager_id === a.id) ? ' selected' : '';
        return '<option value="' + escAttr(a.id) + '"' + sel + '>' + escHtml(a.id) + '</option>';
      }).join('')
    + '</select></div>'
    + '<div class="team-form__row"><label>错误策略</label>'
    + '<select class="input" id="tfErr">'
    + '<option value="stop"' + (isEdit && team.error_policy === 'continue' ? '' : ' selected') + '>stop（成员失败即中止）</option>'
    + '<option value="continue"' + (isEdit && team.error_policy === 'continue' ? ' selected' : '') + '>continue（跳过继续）</option>'
    + '</select></div>'
    + '<div class="team-form__row"><label>描述</label><input class="input" id="tfDesc" value="' + (isEdit ? escAttr(team.description || '') : '') + '" placeholder="可选" /></div>'
    + '<div class="team-form__actions">'
    + (isEdit
        ? '<button class="btn btn--primary btn--sm" onclick="submitTeamEdit(\'' + escAttr(team.id) + '\')">保存修改</button>'
        : '<button class="btn btn--primary btn--sm" onclick="submitTeamNew()">创建</button>')
    + '<button class="btn btn--ghost btn--sm" onclick="loadTeamsPanel()">取消</button>'
    + '</div></div>';
}

function _collectTeamForm() {
  var members = Array.prototype.slice.call(document.querySelectorAll('.tfMember:checked'))
    .map(function(cb){
      var roleEl = document.getElementById('tfRole-' + cb.value);
      var role = roleEl ? (roleEl.value || '').trim() : '';
      return role ? { id: cb.value, role_prompt: role } : cb.value;
    });
  return {
    name: (document.getElementById('tfName').value || '').trim(),
    description: (document.getElementById('tfDesc').value || '').trim(),
    members: members,
    mode: document.getElementById('tfMode').value,
    manager_id: document.getElementById('tfManager').value,
    error_policy: document.getElementById('tfErr').value,
    timeout_seconds: 300
  };
}

function toggleMemberRole(cb) {
  var role = document.getElementById('tfRole-' + cb.value);
  if (role) role.disabled = !cb.checked;
}

function submitTeamNew() {
  var id = (document.getElementById('tfId').value || '').trim();
  if (!id) { setTeamsStatus('团队 ID 必填', 'err'); return; }
  var f = _collectTeamForm();
  if (f.members.length === 0) { setTeamsStatus('至少选 1 个成员', 'err'); return; }
  var body = { id: id, name: f.name || id };
  Object.keys(f).forEach(function(k){ if (k !== 'name') body[k] = f[k]; });
  _teamsApi('/api/ui/teams', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(function(){
    setTeamsStatus('团队「' + id + '」已创建', 'ok');
    loadTeamsPanel();
  }).catch(function(err){ setTeamsStatus('创建失败: ' + err.message, 'err'); });
}

function submitTeamEdit(teamId) {
  var f = _collectTeamForm();
  if (f.members.length === 0) { setTeamsStatus('至少选 1 个成员', 'err'); return; }
  _teamsApi('/api/ui/teams/' + encodeURIComponent(teamId), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(f)
  }).then(function(){
    setTeamsStatus('团队「' + teamId + '」已更新', 'ok');
    loadTeamsPanel();
  }).catch(function(err){ setTeamsStatus('更新失败: ' + err.message, 'err'); });
}

// ── 运行 + 实时轮询 ─────────────────────────────────────
function openTeamRun(teamId) {
  var detailEl = document.getElementById('teamRunDetail');
  if (!detailEl) return;
  detailEl.innerHTML = '<div class="team-run-box">'
    + '<div class="team-run-box__title">▶ 运行团队「' + escHtml(teamId) + '」</div>'
    + '<textarea id="trInput" class="team-run-box__input" rows="3" placeholder="输入要团队完成的任务..."></textarea>'
    + '<div class="team-run-box__actions">'
    + '<button class="btn btn--primary btn--sm" onclick="submitTeamRun(\'' + escAttr(teamId) + '\')">开始运行</button>'
    + '<button class="btn btn--ghost btn--sm" onclick="closeTeamRun()">取消</button>'
    + '</div></div>';
  detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeTeamRun() {
  var el = document.getElementById('teamRunDetail');
  if (el) el.innerHTML = '';
}

function submitTeamRun(teamId) {
  var input = (document.getElementById('trInput').value || '').trim();
  if (!input) { setTeamsStatus('请输入任务', 'err'); return; }
  var detailEl = document.getElementById('teamRunDetail');
  detailEl.innerHTML = '<div class="team-run-box"><div class="team-run-box__title">🚀 运行中...</div>'
    + '<div class="team-run-box__hint">任务已提交，正在启动后台成员执行。步骤产出会实时刷新。</div>'
    + '<div id="trLive"></div></div>';
  _teamsApi('/api/ui/teams/' + encodeURIComponent(teamId) + '/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input: input })
  }).then(function(data){
    var run = data.run || data;
    var runId = run.id;
    if (!runId) { setTeamsStatus('运行失败：未返回 run_id', 'err'); return; }
    // 立即渲染一次，然后轮询
    _renderTeamRun(run);
    _startTeamPoll(runId);
  }).catch(function(err){
    detailEl.innerHTML = '<div class="team-run-box"><div class="team-run-box__err">启动失败: ' + escHtml(err.message) + '</div></div>';
  });
}

function _startTeamPoll(runId) {
  if (_teamPollTimers[runId]) return;
  _teamPollTimers[runId] = setInterval(function(){
    _teamsApi('/api/ui/runs/' + encodeURIComponent(runId))
      .then(function(data){
        var run = data.run || data;
        _renderTeamRun(run);
        if (run.status === 'done' || run.status === 'failed' || run.status === 'timeout') {
          _stopTeamPoll(runId);
        }
      })
      .catch(function(){ _stopTeamPoll(runId); }); // run 可能被清理
  }, 2000);
}

function _stopTeamPoll(runId) {
  var t = _teamPollTimers[runId];
  if (t) { clearInterval(t); delete _teamPollTimers[runId]; }
}

function _renderTeamRun(run) {
  var el = document.getElementById('trLive');
  if (!el) return;
  el.innerHTML = _runHeadHtml(run) + '<div class="team-steps">' + _stepsHtml(run) + '</div>';
}

function _runHeadHtml(run) {
  return '<div class="team-run-status">' + _teamStatusIcon(run.status) + ' ' + escHtml(run.status)
    + (run.error ? ' <span class="team-run-error">' + escHtml(run.error) + '</span>' : '')
    + '</div>';
}

function _stepsHtml(run) {
  var steps = run.steps || [];
  if (steps.length === 0) return '<div class="team-run-hint">（无步骤）</div>';
  return steps.map(function(s){
    var icon = _STEP_ICON[s.type] || '•';
    var out = s.output || '';
    var outHtml = out
      ? '<div class="team-step__output"><pre>' + escHtml(out) + '</pre></div>'
      : '<div class="team-step__output team-step__output--empty">（该步骤暂无输出）</div>';
    var inp = s.input ? '<div class="team-step__input"><span class="team-step__lbl">输入</span>' + escHtml(String(s.input).slice(0, 200)) + '</div>' : '';
    return '<div class="team-step team-step--' + escAttr(s.status) + '">'
      + '<div class="team-step__head">'
      + '<span class="team-step__icon">' + icon + '</span>'
      + '<span class="team-step__agent">' + escHtml(s.agent_id || '?') + '</span>'
      + '<span class="team-step__type">' + escHtml(s.type || '') + '</span>'
      + '<span class="team-step__status">' + _teamStatusIcon(s.status) + ' ' + escHtml(s.status) + '</span>'
      + '</div>'
      + inp
      + outHtml
      + '</div>';
  }).join('');
}

// ── 运行历史 ────────────────────────────────────────────
function openTeamHistory() {
  var panel = document.getElementById('teamHistoryPanel');
  if (!panel) return;
  panel.style.display = 'block';
  panel.innerHTML = '<div class="team-history"><div class="team-history__head">'
    + '<span class="team-history__title">🕘 运行历史</span>'
    + '<button class="btn btn--ghost btn--sm" onclick="closeTeamHistory()">关闭</button>'
    + '</div><div class="team-history__hint">加载中...</div></div>';
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  _loadTeamHistory();
}

function closeTeamHistory() {
  var panel = document.getElementById('teamHistoryPanel');
  if (panel) panel.style.display = 'none';
}

function _loadTeamHistory() {
  _teamsApi('/api/ui/runs')
    .then(function(data){
      var runs = (data.runs || []).slice(0, 30);
      _renderTeamHistory(runs);
    })
    .catch(function(err){
      var panel = document.getElementById('teamHistoryPanel');
      if (panel) panel.querySelector('.team-history__hint').textContent = '加载失败: ' + err.message;
    });
}

function _renderTeamHistory(runs) {
  var hintEl = document.querySelector('#teamHistoryPanel .team-history__hint');
  if (!hintEl) return;
  if (runs.length === 0) {
    hintEl.textContent = '还没有运行记录。运行一个团队后，这里会展示历史。';
    return;
  }
  var rows = runs.map(function(r){
    var teamName = (_teamsCache.find(function(t){ return t.id === r.team_id; }) || {}).name || r.team_id || '?';
    var when = r.created_at ? new Date(r.created_at * 1000).toLocaleString() : '';
    var recoverBtn = (r.status === 'failed' || r.status === 'timeout')
      ? '<button class="btn btn--ghost btn--sm team-history__recover" onclick="recoverTeamRun(\'' + escAttr(r.id) + '\')">恢复重跑</button>'
      : '';
    var cancelBtn = (r.status === 'running')
      ? '<button class="btn btn--ghost btn--sm team-history__cancel" onclick="cancelTeamRun(\'' + escAttr(r.id) + '\')">停止</button>'
      : '';
    return '<div class="team-history__row">'
      + '<div class="team-history__row-main">'
      + '<div class="team-history__row-top">'
      + '<span class="team-history__team">' + escHtml(teamName) + '</span>'
      + '<span class="team-history__status">' + _teamStatusIcon(r.status) + ' ' + escHtml(r.status) + '</span>'
      + '</div>'
      + '<div class="team-history__meta">' + escHtml(when) + ' · ' + (r.steps ? r.steps.length : 0) + ' 个步骤'
      + (r.user_input ? ' · ' + escHtml(String(r.user_input).slice(0, 60)) : '') + '</div>'
      + '</div>'
      + '<div class="team-history__row-actions">'
      + '<button class="btn btn--ghost btn--sm" onclick="viewTeamRun(\'' + escAttr(r.id) + '\')">查看</button>'
      + cancelBtn
      + recoverBtn
      + '</div>'
      + '</div>';
  }).join('');
  var wrap = document.querySelector('#teamHistoryPanel .team-history');
  if (wrap) {
    var box = document.createElement('div');
    box.className = 'team-history__list';
    box.innerHTML = rows;
    hintEl.replaceWith(box);
  }
}

function viewTeamRun(runId) {
  _teamsApi('/api/ui/runs/' + encodeURIComponent(runId))
    .then(function(data){
      var run = data.run || data;
      var box = document.querySelector('#teamHistoryPanel .team-history');
      if (!box) return;
      box.innerHTML = '<div class="team-history__head">'
        + '<span class="team-history__title">🕘 运行详情 ' + escHtml(run.id) + '</span>'
        + '<button class="btn btn--ghost btn--sm" onclick="openTeamHistory()">← 返回列表</button>'
        + '</div>'
        + _runHeadHtml(run)
        + '<div class="team-steps">' + _stepsHtml(run) + '</div>';
    })
    .catch(function(err){ setTeamsStatus('加载运行失败: ' + err.message, 'err'); });
}

function recoverTeamRun(runId) {
  _teamsApi('/api/ui/runs/' + encodeURIComponent(runId) + '/recover', { method: 'POST' })
    .then(function(){
      setTeamsStatus('运行 ' + runId + ' 已标记为可恢复，正在重新执行', 'ok');
      // 重新轮询该 run 直到结束
      _startTeamPoll(runId);
      viewTeamRun(runId);
    })
    .catch(function(err){ setTeamsStatus('恢复失败: ' + err.message, 'err'); });
}

function cancelTeamRun(runId) {
  if (!window.confirm('确定停止运行 ' + runId + ' 吗？后台线程若卡死无法打断，将标记为超时。')) return;
  _teamsApi('/api/ui/runs/' + encodeURIComponent(runId) + '/cancel', { method: 'POST' })
    .then(function(){
      setTeamsStatus('运行 ' + runId + ' 已停止', 'ok');
      _stopTeamPoll(runId);
      viewTeamRun(runId);
    })
    .catch(function(err){ setTeamsStatus('停止失败: ' + err.message, 'err'); });
}

// ── 初始化（随 Agent 页加载） ────────────────────────────
function initTeamsPanel() {
  // 首次进入 agent 页时加载；之后每次切回 agent 页也可手动点刷新
  var hb = document.getElementById('btnTeamHistory');
  if (hb && !hb.getAttribute('data-bound')) {
    hb.setAttribute('data-bound', '1');
    hb.onclick = function(){ openTeamHistory(); };
  }
  loadTeamsPanel();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function(){ initTeamsPanel(); });
} else {
  initTeamsPanel();
}
