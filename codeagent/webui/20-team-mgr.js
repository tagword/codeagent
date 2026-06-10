// Team 管理面板
// 依赖: 00-utils.js (apiUrl, escHtml, escAttr)

function _teamApi(path, opts) {
  return fetch(apiUrl(path), opts || {}).then(function(r){
    if (!r.ok) return r.json().then(function(e){ throw new Error(e.detail || '请求失败') });
    return r.json();
  });
}

var _currentTeams = [];
var _currentAgentsForTeam = [];

// ── 页面切换 ──

function switchToTeamPage() {
  if (typeof switchToPage === 'function') switchToPage('page-team');
}

// ── Team 列表 ──

function _renderTeams(teams) {
  var el = document.getElementById('teamList');
  if (!teams || teams.length === 0) {
    el.innerHTML = '<div class="team-list__empty">暂无 Team</div>';
    return;
  }
  var html = '';
  teams.forEach(function(t){
    var name = t.name || t.id;
    var desc = t.description || '';
    var members = (t.members || []).length;
    var modeLabels = { sequential: '顺序', parallel: '并行', manager: '管家' };
    var mode = modeLabels[t.mode] || t.mode;
    html += '<div class="team-card" data-team-id="' + escAttr(t.id) + '">'
      + '<div class="team-card__body">'
      + '<div class="team-card__name">' + escHtml(name) + '</div>'
      + '<div class="team-card__desc">' + escHtml(desc || '无描述') + '</div>'
      + '<div class="team-card__meta">'
      + '<span class="team-card__mode">' + escHtml(mode) + '</span>'
      + '<span class="team-card__members">' + members + ' 成员</span>'
      + '</div></div></div>';
  });
  el.innerHTML = html;
  el.querySelectorAll('.team-card').forEach(function(card){
    card.addEventListener('click', function(){ _showTeamDetail(this.dataset.teamId); });
  });
}

function _loadTeams() {
  _teamApi('/api/ui/teams').then(function(data){
    _currentTeams = data.teams || [];
    _renderTeams(_currentTeams);
  }).catch(function(err){ _teamStatus('error', err.message); });
}

function _teamStatus(type, msg) {
  var el = document.getElementById('teamStatus');
  if (!el) return;
  el.textContent = msg;
  el.className = 'status-line status-line--' + type;
  if (type === 'ok') setTimeout(function(){ el.textContent = ''; el.className = 'status-line'; }, 3000);
}

// ── Team 详情 ──

function _showTeamDetail(teamId) {
  _teamApi('/api/ui/teams/' + encodeURIComponent(teamId)).then(function(data){
    var t = data.team;
    document.getElementById('fieldsetTeamDetail').style.display = '';
    document.getElementById('fieldsetTeamRuns').style.display = '';
    document.getElementById('teamDetailTitle').textContent = 'Team: ' + (t.name || t.id);
    var modeLabels = { sequential: '顺序模式', parallel: '并行模式', manager: '管家模式' };
    var html = '<div class="team-detail">'
      + '<div class="team-detail__row"><strong>ID:</strong> ' + escHtml(t.id) + '</div>'
      + '<div class="team-detail__row"><strong>模式:</strong> ' + (modeLabels[t.mode] || t.mode) + '</div>'
      + '<div class="team-detail__row"><strong>描述:</strong> ' + escHtml(t.description || '(空)') + '</div>'
      + '<div class="team-detail__row"><strong>超时:</strong> ' + (t.timeout_seconds || 300) + 's</div>'
      + '<div class="team-detail__row"><strong>错误策略:</strong> ' + (t.error_policy === 'skip' ? '跳过继续' : '出错即停') + '</div>'
      + '<div class="team-detail__row"><strong>成员:</strong></div>'
      + '<div class="team-detail__members">';
    (t.members || []).forEach(function(m){
      var mid = typeof m === 'string' ? m : (m.id || m);
      html += '<span class="team-detail__member-tag">' + escHtml(mid) + '</span>';
    });
    if (!t.members || t.members.length === 0) html += '<span class="text-dim">无成员</span>';
    html += '</div></div>';
    document.getElementById('teamDetailContent').innerHTML = html;

    document.getElementById('btnTeamRun').onclick = function(){ _runTeam(t.id); };
    document.getElementById('btnTeamEditDetail').onclick = function(){ _openTeamModal(t.id); };
    document.getElementById('btnTeamDeleteDetail').onclick = function(){ _deleteTeam(t.id); };

    _loadTeamRuns(t.id);
  }).catch(function(err){ _teamStatus('error', err.message); });
}

function _deleteTeam(teamId) {
  if (!confirm('确认删除 Team "' + teamId + '"？')) return;
  _teamApi('/api/ui/teams/' + encodeURIComponent(teamId), { method: 'DELETE' }).then(function(){
    _teamStatus('ok', '已删除');
    _loadTeams();
    document.getElementById('fieldsetTeamDetail').style.display = 'none';
    document.getElementById('fieldsetTeamRuns').style.display = 'none';
  }).catch(function(err){ _teamStatus('error', err.message); });
}

// ── Run ──

function _runTeam(teamId) {
  var input = prompt('输入任务描述：');
  if (!input) return;
  _teamApi('/api/ui/teams/' + encodeURIComponent(teamId) + '/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input: input }),
  }).then(function(data){
    _teamStatus('ok', '运行已完成');
    _loadTeamRuns(teamId);
  }).catch(function(err){ _teamStatus('error', err.message); });
}

function _loadTeamRuns(teamId) {
  _teamApi('/api/ui/runs?team_id=' + encodeURIComponent(teamId)).then(function(data){
    var el = document.getElementById('teamRunsList');
    var runs = data.runs || [];
    if (runs.length === 0) {
      el.innerHTML = '<div class="text-dim" style="padding:var(--sp-2) 0;">暂无运行记录</div>';
      return;
    }
    var html = '';
    runs.forEach(function(r){
      var time = r.created_at ? new Date(r.created_at * 1000).toLocaleString() : '';
      var steps = (r.steps || []).length;
      var statusClass = r.status === 'done' ? 'run-status--ok' : (r.status === 'failed' ? 'run-status--err' : '');
      html += '<div class="run-card ' + statusClass + '">'
        + '<div class="run-card__header"><strong>' + escHtml(r.id) + '</strong>'
        + ' <span class="run-card__status">' + escHtml(r.status) + '</span></div>'
        + '<div class="run-card__input">' + escHtml((r.user_input || '').substring(0, 80)) + '</div>'
        + '<div class="run-card__meta">' + steps + ' 步 · ' + escHtml(time) + '</div>'
        + '</div>';
    });
    el.innerHTML = html;
  }).catch(function(){});
}

// ── Modal ──

function _openTeamModal(teamId) {
  var isEdit = !!teamId;
  document.getElementById('teamModalTitle').textContent = isEdit ? '编辑 Team' : '新建 Team';
  document.getElementById('teamModal').style.display = '';

  document.getElementById('inpTeamId').disabled = isEdit;

  // Load agents for member checkbox
  _teamApi('/api/ui/agents').then(function(data){
    _currentAgentsForTeam = data.agents || [];
    var html = '';
    _currentAgentsForTeam.forEach(function(a){
      html += '<label class="checkbox-label"><input type="checkbox" class="team-member-cb" value="' + escAttr(a.id) + '"> ' + escHtml(a.name || a.id) + '</label>';
    });
    document.getElementById('teamMemberCheckboxList').innerHTML = html;
  });

  if (isEdit) {
    _teamApi('/api/ui/teams/' + encodeURIComponent(teamId)).then(function(data){
      var t = data.team;
      document.getElementById('inpTeamId').value = t.id;
      document.getElementById('inpTeamName').value = t.name || '';
      document.getElementById('inpTeamDesc').value = t.description || '';
      document.getElementById('selTeamMode').value = t.mode || 'sequential';
      document.getElementById('inpTeamTimeout').value = t.timeout_seconds || 300;
      document.getElementById('selTeamErrorPolicy').value = t.error_policy || 'stop';
      if (t.members) {
        document.querySelectorAll('.team-member-cb').forEach(function(cb){
          cb.checked = t.members.indexOf(cb.value) >= 0;
        });
      }
    });
  } else {
    document.getElementById('inpTeamId').value = '';
    document.getElementById('inpTeamName').value = '';
    document.getElementById('inpTeamDesc').value = '';
    document.getElementById('selTeamMode').value = 'sequential';
    document.getElementById('inpTeamTimeout').value = '300';
    document.getElementById('selTeamErrorPolicy').value = 'stop';
  }
}

function _saveTeam() {
  var teamId = document.getElementById('inpTeamId').value.trim();
  if (!teamId) { _teamStatus('error', 'Team ID 不能为空'); return; }
  var isEdit = document.getElementById('inpTeamId').disabled;
  var members = [];
  document.querySelectorAll('.team-member-cb:checked').forEach(function(cb){ members.push(cb.value); });
  var body = {
    id: teamId,
    name: document.getElementById('inpTeamName').value.trim(),
    description: document.getElementById('inpTeamDesc').value.trim(),
    mode: document.getElementById('selTeamMode').value,
    timeout_seconds: parseInt(document.getElementById('inpTeamTimeout').value) || 300,
    error_policy: document.getElementById('selTeamErrorPolicy').value,
    members: members,
  };
  var url = '/api/ui/teams';
  var method = 'POST';
  if (isEdit) { url += '/' + encodeURIComponent(teamId); method = 'PUT'; }
  _teamApi(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then(function(){
      _teamStatus('ok', isEdit ? '已更新' : '已创建');
      document.getElementById('teamModal').style.display = 'none';
      _loadTeams();
      if (isEdit) _showTeamDetail(teamId);
    })
    .catch(function(err){ _teamStatus('error', err.message); });
}

// ── 活动栏激活 ──

function _activateTeamButton() {
  var btn = document.querySelector('.activity-btn[data-mode="team"]');
  if (btn) return; // already exists
  var configBtn = document.querySelector('.activity-btn[data-mode="config"]');
  if (!configBtn) return;
  var teamBtn = document.createElement('button');
  teamBtn.type = 'button';
  teamBtn.className = 'activity-btn';
  teamBtn.dataset.mode = 'team';
  teamBtn.title = 'Team';
  teamBtn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/><circle cx="9" cy="7" r="4" fill="none" stroke="currentColor" stroke-width="1.75"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>';
  configBtn.parentNode.insertBefore(teamBtn, configBtn);
  teamBtn.addEventListener('click', function(){
    document.querySelectorAll('.activity-btn').forEach(function(b){ b.classList.remove('active'); });
    teamBtn.classList.add('active');
    switchToTeamPage();
    _loadTeams();
  });
}

// ── 初始化 ──

function initTeamMgr() {
  _activateTeamButton();

  document.getElementById('btnTeamCreate').addEventListener('click', function(){ _openTeamModal(); });
  document.getElementById('btnTeamRefresh').addEventListener('click', _loadTeams);
  document.getElementById('btnTeamModalClose').addEventListener('click', function(){ document.getElementById('teamModal').style.display = 'none'; });
  document.getElementById('btnTeamModalCancel').addEventListener('click', function(){ document.getElementById('teamModal').style.display = 'none'; });
  document.getElementById('btnTeamModalSave').addEventListener('click', _saveTeam);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initTeamMgr);
} else {
  initTeamMgr();
}
