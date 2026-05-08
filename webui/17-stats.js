/* ================================================================
 * 17-stats.js — 侧栏「统计」视图（依赖全局 agentId）
 * ================================================================ */

async function loadStats() {
  var elP = document.getElementById('statProjects');
  var elS = document.getElementById('statSessions');
  var elM = document.getElementById('statMessages');
  var elT = document.getElementById('statTodos');
  var updated = document.getElementById('statsLastUpdated');
  var recentP = document.getElementById('statsRecentProjects');
  var recentS = document.getElementById('statsRecentSessions');

  function empty(el, text) {
    if (!el) return;
    el.innerHTML = '<div class="config-tool-list__empty">' + (text || '—') + '</div>';
  }

  try {
    var rp = await fetch('/api/ui/projects?agent_id=' + encodeURIComponent(agentId), { credentials: 'same-origin' });
    if (!rp.ok) throw new Error('projects');
    var jp = await rp.json();
    var projects = jp.projects || [];
    if (elP) elP.textContent = String(projects.length);

    var rs = await fetch('/api/ui/sessions?agent_id=' + encodeURIComponent(agentId) + '&limit=500', { credentials: 'same-origin' });
    if (!rs.ok) throw new Error('sessions');
    var js = await rs.json();
    var sessions = js.sessions || [];
    if (elS) elS.textContent = String(sessions.length);
    var msgSum = 0;
    sessions.forEach(function(s) { msgSum += (s.message_count || 0); });
    if (elM) elM.textContent = String(msgSum);

    var todoSum = 0;
    for (var i = 0; i < projects.length; i++) {
      var pid = projects[i].id;
      var rt = await fetch(
        '/api/ui/projects/todos?agent_id=' + encodeURIComponent(agentId) + '&project_id=' + encodeURIComponent(pid),
        { credentials: 'same-origin' }
      );
      if (!rt.ok) continue;
      var jt = await rt.json();
      todoSum += (jt.todos || []).length;
    }
    if (elT) elT.textContent = String(todoSum);

    if (updated) {
      updated.textContent = '更新于 ' + new Date().toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
      });
    }

    if (recentP) {
      recentP.innerHTML = '';
      var prSlice = projects.slice(0, 8);
      if (!prSlice.length) empty(recentP, '暂无项目');
      else prSlice.forEach(function(pr) {
        var row = document.createElement('div');
        row.className = 'stats-recent__row';
        row.innerHTML = '<span class="stats-recent__name">' + escapeHtml(pr.name || pr.id) + '</span>' +
          '<span class="stats-recent__meta">' + escapeHtml(pr.id) + '</span>';
        recentP.appendChild(row);
      });
    }

    if (recentS) {
      recentS.innerHTML = '';
      var sSlice = sessions.slice(0, 10);
      if (!sSlice.length) empty(recentS, '暂无会话');
      else sSlice.forEach(function(s) {
        var row = document.createElement('div');
        row.className = 'stats-recent__row';
        var title = s.display_title || s.session_id || '会话';
        row.innerHTML = '<span class="stats-recent__name">' + escapeHtml(title) + '</span>' +
          '<span class="stats-recent__meta">' + (s.message_count != null ? (s.message_count + ' 条') : '') + '</span>';
        recentS.appendChild(row);
      });
    }
  } catch (e) {
    if (updated) updated.textContent = '加载失败';
    empty(recentP, '加载失败');
    empty(recentS, '加载失败');
  }
}
