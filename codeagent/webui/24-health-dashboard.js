// 健康看板 — Agent 心跳/状态/运行一览

function _healthApi(path) {
  return fetch(apiUrl(path)).then(function(r){
    if (!r.ok) throw new Error('请求失败');
    return r.json();
  });
}

function _loadHealthDashboard() {
  _healthApi('/api/ui/health/status').then(function(data){
    _renderHealthStatus(data);
  }).catch(function(err){
    document.getElementById('healthContent').innerHTML = '<div class="health__error">加载失败: ' + err.message + '</div>';
  });

  _healthApi('/api/ui/runs').then(function(data){
    _renderHealthRuns(data.runs || []);
  }).catch(function(){});
}

function _renderHealthStatus(status) {
  var el = document.getElementById('healthContent');
  var statusBadge = status.status === 'alive' ? '🟢' : (status.status === 'stuck' ? '🔴' : '⚪');
  var html = '<div class="health-section"><h3>Agent 状态</h3>'
    + '<div class="health-grid">'
    + '<div class="health-card"><div class="health-card__label">状态</div><div class="health-card__value">' + statusBadge + ' ' + status.status + '</div></div>'
    + '<div class="health-card"><div class="health-card__label">PID</div><div class="health-card__value">' + (status.process_id || '-') + '</div></div>'
    + '<div class="health-card"><div class="health-card__label">心跳</div><div class="health-card__value">' + (status.elapsed_seconds ? status.elapsed_seconds + 's 前' : '-') + '</div></div>'
    + '</div></div>';
  el.innerHTML = html;
}

function _renderHealthRuns(runs) {
  var html = '<div class="health-section"><h3>运行记录 (' + runs.length + ')</h3><div class="health-runs">';
  if (runs.length === 0) {
    html += '<div class="text-dim">暂无运行记录</div>';
  } else {
    runs.slice(0, 10).forEach(function(r){
      var time = r.created_at ? new Date(r.created_at * 1000).toLocaleString() : '';
      var icon = r.status === 'done' ? '✅' : (r.status === 'failed' ? '❌' : (r.status === 'running' ? '🔄' : '⏳'));
      html += '<div class="health-run"><span class="health-run__icon">' + icon + '</span>'
        + '<span class="health-run__id">' + escHtml(r.id) + '</span>'
        + '<span class="health-run__status">' + escHtml(r.status) + '</span>'
        + '<span class="health-run__time">' + escHtml(time) + '</span></div>';
    });
  }
  html += '</div></div>';
  document.getElementById('healthContent').innerHTML += html;
}

// ── 挂在 stats 页面上 ──
function initHealthDashboard() {
  // 如果 stats 页面已有内容，追加到后面
  var statsContent = document.getElementById('statsContent');
  if (!statsContent) return;
  statsContent.innerHTML = '<div id="healthContent"></div>';
  _loadHealthDashboard();

  // 每 30 秒刷新
  setInterval(_loadHealthDashboard, 30000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initHealthDashboard);
} else {
  initHealthDashboard();
}
