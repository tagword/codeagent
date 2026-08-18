  const toggle = document.getElementById('cronGlobalToggle');
  const list = document.getElementById('cronJobList');
  if (!toggle) return;
  toggle.classList.remove('is-err');
  try {
    const r = await fetch('/api/ui/flags?agent_id=' + encodeURIComponent(agentId));
    if (!r.ok) throw new Error(String(r.status));
    const f = await r.json();
    const c = f.cron;
    if (!c || c.error) {
      // 状态接口失败：给用户可见提示，而不是静默白屏
      const st = document.getElementById('cronUiStatus');
      if (st) {
        st.classList.add('is-err');
        st.textContent = 'cron 状态获取失败' + (c && c.error ? '：' + c.error : '');
      }
      return;
    }

    // 调度器未启动/启动失败：明确告警（配置启用但 scheduler 没跑 = 任务不会执行）
    const st = document.getElementById('cronUiStatus');
    const warn = c.startup_error || (c.config_enabled && !c.env_disabled && !c.scheduler_running
      ? '调度器未运行（scheduler not running），定时任务不会执行；请检查服务日志'
      : '');
    if (st) {
      st.classList.toggle('is-err', !!warn);
      st.textContent = warn;
    }

    // Global enabled state
    cronGlobalEnabled = c.config_enabled && !c.env_disabled;
    toggle.classList.toggle('on', cronGlobalEnabled);

    // Render job cards
    list.innerHTML = '';
    const jobs = c.jobs_config || [];
    if (jobs.length === 0) {
      list.innerHTML = '<div class="cron-empty">暂无定时任务，点击"+ 新增"添加。</div>';
    } else {
      jobs.forEach(function(j) { list.appendChild(buildCronJobCard(j)); });
    }
  } catch (e) {
    const st = document.getElementById('cronUiStatus');
    if (st) { st.classList.add('is-err'); st.textContent = 'cron 面板加载失败：' + String(e); }
  }
}

// ---- Global toggle ----
document.getElementById('cronGlobalToggle') && document.getElementById('cronGlobalToggle').addEventListener('click', async function() {
  const toggle = this;
  const newVal = !cronGlobalEnabled;
  toggle.classList.add('is-err');
  try {
    const r = await fetch('/api/ui/cron/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: newVal })
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    cronGlobalEnabled = newVal;
    toggle.classList.toggle('on', newVal);
    await loadCronPanel();
  } catch (e) {
    toggle.classList.add('is-err');
    const st = document.getElementById('cronUiStatus');
    if (st) { st.classList.add('is-err'); st.textContent = String(e); }
  }
  toggle.classList.remove('is-err');
});

// ---- Build a cron job card ----
function buildCronJobCard(j) {
  var wrap = document.createElement('div'); wrap.className = 'cron-card-wrap';
  var header = document.createElement('div'); header.className = 'cron-card';
  var info = document.createElement('div'); info.className = 'cron-card__info';
  var nameRow = document.createElement('div'); nameRow.className = 'cron-card__name';
  var dot = document.createElement('span'); dot.className = 'cron-card__status-dot' + (j.enabled ? ' on' : ' off');
  nameRow.appendChild(dot);
  nameRow.appendChild(document.createTextNode(j.title || j.id || '未命名任务'));
  var badge = document.createElement('span');
  badge.className = 'cron-card__badge' + (j.enabled ? '' : ' cron-card__badge-off');
  badge.textContent = j.enabled ? '启用' : '停用';
  nameRow.appendChild(badge);
  info.appendChild(nameRow);
  var detail = document.createElement('div'); detail.className = 'cron-card__detail';
  detail.textContent = describeCron(j.cron) + ' — agent: ' + (j.agent_id || 'default');
  if (j.timezone) detail.textContent += ' (TZ: ' + j.timezone + ')';
  info.appendChild(detail);
  var actions = document.createElement('div'); actions.className = 'cron-card__actions';
  var btnToggle = document.createElement('button');
  btnToggle.type = 'button'; btnToggle.className = 'btn btn--ghost btn--xs';
  btnToggle.textContent = j.enabled ? '停用' : '启用';
  btnToggle.addEventListener('click', async function(ev) {
    ev.stopPropagation();
    try {
      var newJob = JSON.parse(JSON.stringify(j));
      newJob.enabled = !j.enabled;
      var r = await fetch('/api/ui/cron/job', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(newJob) });
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      await loadCronPanel();
    } catch (e) { showCronError(String(e)); }
  });
  actions.appendChild(btnToggle);
  var btnDel = document.createElement('button');
  btnDel.type = 'button'; btnDel.className = 'btn btn--ghost btn--xs cron-del'; btnDel.textContent = '删除';
  btnDel.addEventListener('click', async function(ev) {
    ev.stopPropagation();
    if (!confirm('确定删除定时任务「' + (j.title || j.id || '') + '」？')) return;
    try {
      var r = await fetch('/api/ui/cron/job/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job_id: j.id }) });
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      await loadCronPanel();
    } catch (e) { showCronError(String(e)); }
  });
  actions.appendChild(btnDel);
  header.appendChild(info); header.appendChild(actions);
  var editWrap = document.createElement('div'); editWrap.className = 'cron-edit-wrap'; editWrap.style.display = 'none';
  var editStatus = document.createElement('div'); editStatus.className = 'status-line';
