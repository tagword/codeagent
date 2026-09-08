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
      return '<span class="team-member-tag">' + escHtml(id) + '</span>';
    }).join('');
    var pm = t.manager_id ? '<span class="teams__pm">PM: ' + escHtml(t.manager_id) + '</span>' : '';
    return '<div class="team-card" data-team-id="' + escAttr(t.id) + '">'
      + '<div class="team-card__head">'
      + '<div class="team-card__title">' + _MODE_ICON[mode] + ' ' + escHtml(t.name || t.id) + '</div>'
      + '<div class="team-card__actions">'
      + '<button class="btn btn--primary btn--sm" onclick="openTeamRun(\'' + escAttr(t.id) + '\')">▶ 运行</button>'
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

// ── 新建 ────────────────────────────────────────────────
function openTeamNew() {
  var listEl = document.getElementById('teamsList');
  if (!listEl) return;
  var agents = _agentsCache;
  var agentOpts = agents.length
    ? agents.map(function(a){ return '<option value="' + escAttr(a.id) + '">' + escHtml(a.id) + '</option>'; }).join('')
    : '<option value="default">default</option>';
  listEl.innerHTML = '<div class="team-form" id="teamForm">'
    + '<div class="team-form__title">新建团队</div>'
    + '<div class="team-form__row"><label>团队 ID</label><input class="input" id="tfId" placeholder="如 dev-team" /></div>'
    + '<div class="team-form__row"><label>名称</label><input class="input" id="tfName" placeholder="如 开发团队" /></div>'
    + '<div class="team-form__row"><label>模式</label>'
    + '<select class="input" id="tfMode">'
    + '<option value="sequential">顺序逐个（前一步产出传给下一步）</option>'
    + '<option value="parallel">并行处理（所有成员同输入）</option>'
    + '<option value="manager">PM 拆解分派（首个成员当 PM）</option>'
    + '</select></div>'
    + '<div class="team-form__row"><label>成员（多选）</label><div class="team-form__members">'
    + agents.map(function(a){
        return '<label class="team-member-check"><input type="checkbox" class="tfMember" value="' + escAttr(a.id) + '" /> ' + escHtml(a.id) + '</label>';
      }).join('')
    + '</div></div>'
    + '<div class="team-form__row"><label>PM（manager 模式）</label>'
    + '<select class="input" id="tfManager"><option value="">(第一个成员)</option>' + agentOpts + '</select></div>'
    + '<div class="team-form__row"><label>错误策略</label>'
    + '<select class="input" id="tfErr"><option value="stop">stop（成员失败即中止）</option><option value="continue">continue（跳过继续）</option></select></div>'
    + '<div class="team-form__row"><label>描述</label><input class="input" id="tfDesc" placeholder="可选" /></div>'
    + '<div class="team-form__actions">'
    + '<button class="btn btn--primary btn--sm" onclick="submitTeamNew()">创建</button>'
    + '<button class="btn btn--ghost btn--sm" onclick="loadTeamsPanel()">取消</button>'
    + '</div></div>';
}

function submitTeamNew() {
  var id = (document.getElementById('tfId').value || '').trim();
  if (!id) { setTeamsStatus('团队 ID 必填', 'err'); return; }
  var members = Array.prototype.slice.call(document.querySelectorAll('.tfMember:checked'))
    .map(function(cb){ return cb.value; });
  if (members.length === 0) { setTeamsStatus('至少选 1 个成员', 'err'); return; }
  var mode = document.getElementById('tfMode').value;
  var body = {
    id: id,
    name: (document.getElementById('tfName').value || '').trim() || id,
    description: (document.getElementById('tfDesc').value || '').trim(),
    members: members,
    mode: mode,
    manager_id: document.getElementById('tfManager').value,
    error_policy: document.getElementById('tfErr').value,
    timeout_seconds: 300
  };
  _teamsApi('/api/ui/teams', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(function(){
    setTeamsStatus('团队「' + id + '」已创建', 'ok');
    loadTeamsPanel();
  }).catch(function(err){ setTeamsStatus('创建失败: ' + err.message, 'err'); });
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
  var steps = run.steps || [];
  var head = '<div class="team-run-status">' + _teamStatusIcon(run.status) + ' ' + escHtml(run.status)
    + (run.error ? ' <span class="team-run-error">' + escHtml(run.error) + '</span>' : '')
    + '</div>';
  var stepsHtml = steps.length === 0
    ? '<div class="team-run-hint">等待成员启动...</div>'
    : steps.map(function(s, i){
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
  el.innerHTML = head + '<div class="team-steps">' + stepsHtml + '</div>';
}

// ── 初始化（随 Agent 页加载） ────────────────────────────
function initTeamsPanel() {
  // 首次进入 agent 页时加载；之后每次切回 agent 页也可手动点刷新
  loadTeamsPanel();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function(){ initTeamsPanel(); });
} else {
  initTeamsPanel();
}
