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
  if (typeof switchToPage === 'function') switchToPage('team');
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
    var pmName = (t.mode === 'manager' && t.manager_id)
      ? t.manager_id
      : (t.mode === 'manager' && t.members && t.members.length > 0
        ? (typeof t.members[0] === 'string' ? t.members[0] : (t.members[0].name || t.members[0].id || ''))
        : '');
    html += '<div class="team-card" data-team-id="' + escAttr(t.id) + '">'
      + '<div class="team-card__body">'
      + '<div class="team-card__name">' + escHtml(name) + '</div>'
      + '<div class="team-card__desc">' + escHtml(desc || '无描述') + '</div>'
      + '<div class="team-card__meta">'
      + '<span class="team-card__mode">' + escHtml(mode) + '</span>'
      + '<span class="team-card__members">' + members + ' 成员</span>'
      + (pmName ? '<span class="team-card__pm">管家：' + escHtml(pmName) + '</span>' : '')
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

// ── Team 详情（直接可编辑）──

function _showTeamDetail(teamId) {
  _teamApi('/api/ui/teams/' + encodeURIComponent(teamId)).then(function(data){
    var t = data.team;
    document.getElementById('fieldsetTeamDetail').style.display = '';
    document.getElementById('fieldsetTeamRuns').style.display = '';
    document.getElementById('teamDetailTitle').textContent = 'Team: ' + (t.name || t.id);
    document.getElementById('btnTeamSaveDetail').style.display = '';

    // 加载成员列表
    _teamApi('/api/ui/agents').then(function(agentsData){
      var agents = agentsData.agents || [];

      var modes = [
        { value: 'sequential', label: '顺序模式' },
        { value: 'parallel', label: '并行模式' },
        { value: 'manager', label: '管家模式' },
      ];

      var html = '<div class="team-detail team-detail--edit">';

      // ID (只读)
      html += '<div class="team-detail__field">'
        + '<label class="team-detail__label">ID</label>'
        + '<input type="text" class="input" id="detailTeamId" value="' + escAttr(t.id) + '" disabled />'
        + '</div>';

      // 名称
      html += '<div class="team-detail__field">'
        + '<label class="team-detail__label">名称</label>'
        + '<input type="text" class="input" id="detailTeamName" value="' + escAttr(t.name || '') + '" />'
        + '</div>';

      // 描述
      html += '<div class="team-detail__field">'
        + '<label class="team-detail__label">描述</label>'
        + '<textarea class="input textarea" id="detailTeamDesc" rows="2">' + escHtml(t.description || '') + '</textarea>'
        + '</div>';

      // 模式
      html += '<div class="team-detail__field">'
        + '<label class="team-detail__label">工作模式</label>'
        + '<select class="input" id="detailTeamMode">';
      modes.forEach(function(m){
        html += '<option value="' + m.value + '"' + (t.mode === m.value ? ' selected' : '') + '>' + m.label + '</option>';
      });
      html += '</select></div>';

      // 超时 + 错误策略（一行两列）
      html += '<div class="team-detail__field-row">'
        + '<div class="team-detail__field team-detail__field--half">'
        + '<label class="team-detail__label">超时（秒）</label>'
        + '<input type="number" class="input" id="detailTeamTimeout" value="' + (t.timeout_seconds || 300) + '" min="30" />'
        + '</div>'
        + '<div class="team-detail__field team-detail__field--half">'
        + '<label class="team-detail__label">错误策略</label>'
        + '<select class="input" id="detailTeamErrorPolicy">'
        + '<option value="stop"' + (t.error_policy === 'stop' ? ' selected' : '') + '>出错即停</option>'
        + '<option value="skip"' + (t.error_policy === 'skip' ? ' selected' : '') + '>跳过继续</option>'
        + '</select></div></div>';

      // 成员 — 复选框
      html += '<div class="team-detail__field">'
        + '<label class="team-detail__label">成员</label>'
        + '<div class="checkbox-group" id="detailTeamMembers">';
      agents.forEach(function(a){
        var checked = t.members && t.members.indexOf(a.id) >= 0;
        html += '<label class="checkbox-label"><input type="checkbox" class="detail-member-cb" value="' + escAttr(a.id) + '"' + (checked ? ' checked' : '') + '> ' + escHtml(a.name || a.id) + '</label>';
      });
      html += '</div></div>';

      // 管家（模式切换时显示/隐藏）
      var showManager = t.mode === 'manager';
      html += '<div class="team-detail__field" id="detailFieldManager"' + (showManager ? '' : ' style="display:none"') + '>'
        + '<label class="team-detail__label">管家（PM）</label>'
        + '<select class="input" id="detailTeamManager">'
        + '<option value="">— 请选择管家 —</option>'
        + '</select><p class="modal-field__hint">管家负责拆解任务并分派给其他成员</p></div>';

      html += '</div>'; // .team-detail

      document.getElementById('teamDetailContent').innerHTML = html;

      // ── 初始化管家下拉（仅显示已勾选成员）──
      _rebuildDetailManagerSelect();
      // 如果已有指定管家，恢复选中
      if (t.manager_id) {
        document.getElementById('detailTeamManager').value = t.manager_id;
      }

      // 模式切换 → 显示/隐藏管家选择
      document.getElementById('detailTeamMode').addEventListener('change', function(){
        var field = document.getElementById('detailFieldManager');
        if (field) field.style.display = this.value === 'manager' ? '' : 'none';
      });

      // 成员复选框变化 → 刷新管家下拉选项
      document.querySelectorAll('.detail-member-cb').forEach(function(cb){
        cb.addEventListener('change', _rebuildDetailManagerSelect);
      });

      // 按钮
      document.getElementById('btnTeamRun').onclick = function(){ _runTeam(t.id); };
      document.getElementById('btnTeamSaveDetail').onclick = function(){ _saveTeamDetail(t.id); };
      document.getElementById('btnTeamDeleteDetail').onclick = function(){ _deleteTeam(t.id); };
    });

    _loadTeamRuns(t.id);
  }).catch(function(err){ _teamStatus('error', err.message); });
}

function _rebuildDetailManagerSelect() {
  var sel = document.getElementById('detailTeamManager');
  if (!sel) return;
  var currentVal = sel.value;
  sel.innerHTML = '<option value="">— 请选择管家 —</option>';
  document.querySelectorAll('.detail-member-cb:checked').forEach(function(cb){
    var opt = document.createElement('option');
    opt.value = cb.value;
    opt.textContent = cb.value;
    sel.appendChild(opt);
  });
  if (currentVal && sel.querySelector('option[value="' + currentVal.replace(/"/g, '&quot;') + '"]')) {
    sel.value = currentVal;
  }
}

function _saveTeamDetail(teamId) {
  var members = [];
  document.querySelectorAll('.detail-member-cb:checked').forEach(function(cb){ members.push(cb.value); });
  var mode = document.getElementById('detailTeamMode').value;
  var manager_id = mode === 'manager' ? document.getElementById('detailTeamManager').value : '';
  if (mode === 'manager' && !manager_id) {
    _teamStatus('error', '管家模式需要指定一名管家');
    return;
  }
  var body = {
    name: document.getElementById('detailTeamName').value.trim(),
    description: document.getElementById('detailTeamDesc').value.trim(),
    mode: mode,
    timeout_seconds: parseInt(document.getElementById('detailTeamTimeout').value) || 300,
    error_policy: document.getElementById('detailTeamErrorPolicy').value,
    members: members,
    manager_id: manager_id,
  };
  _teamApi('/api/ui/teams/' + encodeURIComponent(teamId), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(function(){
    _teamStatus('ok', '已保存');
    _loadTeams();
    _showTeamDetail(teamId);
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

function _rebuildManagerSelect() {
  var sel = document.getElementById('selTeamManager');
  if (!sel) return;
  var currentVal = sel.value;
  sel.innerHTML = '<option value="">— 请选择管家 —</option>';
  document.querySelectorAll('.team-member-cb:checked').forEach(function(cb){
    var opt = document.createElement('option');
    opt.value = cb.value;
    opt.textContent = cb.value;
    sel.appendChild(opt);
  });
  // 恢复之前选中的值（如果还在成员列表中）
  if (currentVal && sel.querySelector('option[value="' + currentVal.replace(/"/g, '&quot;') + '"]')) {
    sel.value = currentVal;
  }
}

function _toggleManagerField() {
  var mode = document.getElementById('selTeamMode').value;
  var field = document.getElementById('fieldManagerSelect');
  if (field) {
    field.style.display = mode === 'manager' ? '' : 'none';
  }
  if (mode === 'manager') _rebuildManagerSelect();
}

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
    // 监听 checkbox 变化，刷新管家下拉
    document.querySelectorAll('.team-member-cb').forEach(function(cb){
      cb.addEventListener('change', _rebuildManagerSelect);
    });
    _rebuildManagerSelect();
  });

  // 监听模式切换
  document.getElementById('selTeamMode').addEventListener('change', _toggleManagerField);

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
      // 设置管家
      _toggleManagerField();
      if (t.manager_id) {
        document.getElementById('selTeamManager').value = t.manager_id;
      }
    });
  } else {
    document.getElementById('inpTeamId').value = '';
    document.getElementById('inpTeamName').value = '';
    document.getElementById('inpTeamDesc').value = '';
    document.getElementById('selTeamMode').value = 'sequential';
    document.getElementById('inpTeamTimeout').value = '300';
    document.getElementById('selTeamErrorPolicy').value = 'stop';
    _toggleManagerField();
  }
}

function _saveTeam() {
  var teamId = document.getElementById('inpTeamId').value.trim();
  if (!teamId) { _teamStatus('error', 'Team ID 不能为空'); return; }
  var isEdit = document.getElementById('inpTeamId').disabled;
  var members = [];
  document.querySelectorAll('.team-member-cb:checked').forEach(function(cb){ members.push(cb.value); });
  var mode = document.getElementById('selTeamMode').value;
  var manager_id = mode === 'manager' ? document.getElementById('selTeamManager').value : '';
  if (mode === 'manager' && !manager_id) {
    _teamStatus('error', '管家模式需要指定一名管家');
    return;
  }
  var body = {
    id: teamId,
    name: document.getElementById('inpTeamName').value.trim(),
    description: document.getElementById('inpTeamDesc').value.trim(),
    mode: mode,
    timeout_seconds: parseInt(document.getElementById('inpTeamTimeout').value) || 300,
    error_policy: document.getElementById('selTeamErrorPolicy').value,
    members: members,
    manager_id: manager_id,
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
    if (typeof switchActivityMode === 'function') {
      switchActivityMode('team');
    } else {
      document.querySelectorAll('.activity-btn').forEach(function(b){ b.classList.remove('active'); });
      teamBtn.classList.add('active');
    }
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
