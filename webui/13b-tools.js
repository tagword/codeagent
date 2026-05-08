function showNewSkillForm() {
  var list = document.getElementById('skillList');
  if (!list) return;
  var existing = list.querySelector('.cron-card-wrap.is-new');
  if (existing) existing.remove();

  var wrap = document.createElement('div'); wrap.className = 'cron-card-wrap is-new';
  var editWrap = document.createElement('div'); editWrap.className = 'cron-edit-wrap'; editWrap.style.display = 'block';
  var editStatus = document.createElement('div'); editStatus.className = 'status-line';
  editWrap.innerHTML = '<label class="form-label">文件名</label>'
    + '<input class="skill-fld-name" type="text" placeholder="my-skill.md"/>'
    + '<label class="form-label">内容（Markdown）</label>'
    + '<textarea class="skill-fld-body" spellcheck="false" style="height:200px;font-family:var(--font-mono);font-size:13px;width:100%;padding:var(--sp-2);border:1px solid var(--border);border-radius:var(--r-sm);background:var(--bg);color:var(--text);resize:vertical;"></textarea>'
    + '<div class="row-actions" style="margin-top:var(--sp-2);">'
    + '<button type="button" class="btn btn--primary btn--sm skill-save-btn">保存</button>'
    + '<button type="button" class="btn btn--subtle btn--sm skill-cancel-btn">取消</button>'
    + '</div>';
  editWrap.appendChild(editStatus);

  editWrap.querySelector('.skill-cancel-btn').addEventListener('click', function() { wrap.remove(); });
  editWrap.querySelector('.skill-save-btn').addEventListener('click', async function() {
    var name = editWrap.querySelector('.skill-fld-name').value.trim();
    var body = editWrap.querySelector('.skill-fld-body').value;
    if (!name) { editStatus.textContent = '文件名不能为空'; editStatus.classList.add('is-err'); return; }
    editStatus.textContent = '保存中…';
    editStatus.classList.remove('is-err');
    try {
      var r = await fetch('/api/ui/skills?agent_id=' + encodeURIComponent(agentId), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save', name: name, content: body })
      });
      var j = await r.json().catch(function() { return {}; });
      if (!r.ok) throw new Error(j.detail || r.statusText);
      wrap.remove();
      await loadSkills();
    } catch (e) { editStatus.classList.add('is-err'); editStatus.textContent = String(e); }
  });
  wrap.appendChild(editWrap);
  if (list.firstChild) list.insertBefore(wrap, list.firstChild);
  else list.appendChild(wrap);
}

document.getElementById('btnSkillAdd') && document.getElementById('btnSkillAdd').addEventListener('click', showNewSkillForm);
document.getElementById('btnSkillRefresh') && document.getElementById('btnSkillRefresh').addEventListener('click', function() { loadSkills(); });

// ---------------- Tool (integrated plugins) management ----------------

async function loadTools() {
  const list = document.getElementById('toolList');
  const status = document.getElementById('toolStatus');
  if (!list) return;
  status.textContent = '';
  status.classList.remove('is-err');
  try {
    const r = await fetch('/api/ui/plugins');
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.statusText);
    list.innerHTML = '';

    var tools = j.plugins || {};
    var toolKeys = Object.keys(tools);
    if (toolKeys.length === 0) {
      list.innerHTML = '<div class="cron-empty">暂无可用工具。</div>';
      if (status) status.textContent = '0 个可用工具';
      return;
    }
    toolKeys.forEach(function(tid) {
      var t = tools[tid] || {};
      var wrap = document.createElement('div'); wrap.className = 'tool-card-wrap';
      var card = document.createElement('div'); card.className = 'cron-card';
      var info = document.createElement('div'); info.className = 'cron-card__info';
      var nameRow = document.createElement('div'); nameRow.className = 'cron-card__name';
      nameRow.textContent = tid;
      var badge = document.createElement('span');
      badge.className = 'cron-card__badge' + (t.enabled !== false ? '' : ' cron-card__badge-off');
      badge.textContent = (t.enabled !== false) ? '启用' : '停用';
      nameRow.appendChild(badge);
      info.appendChild(nameRow);
      var detail = document.createElement('div'); detail.className = 'cron-card__detail';
      detail.textContent = t.description || '';
      info.appendChild(detail);
      var actions = document.createElement('div'); actions.className = 'cron-card__actions';
      var btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'btn btn--ghost btn--xs';
      btn.textContent = (t.enabled !== false) ? '停用' : '启用';
      btn.addEventListener('click', function(ev) {
        ev.stopPropagation();
        toggleTool(tid, !(t.enabled !== false));
      });
      actions.appendChild(btn);
      card.appendChild(info); card.appendChild(actions);
      wrap.appendChild(card);
      list.appendChild(wrap);
    });
    if (status) status.textContent = '共 ' + toolKeys.length + ' 个可用工具';
  } catch (e) {
    if (status) { status.classList.add('is-err'); status.textContent = String(e); }
  }
}

async function toggleTool(toolId, enabled) {
  const body = {};
  body[toolId] = { enabled: enabled };
  try {
    const r = await fetch('/api/ui/plugins', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plugins: body }) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.statusText);
    await loadTools();
  } catch (e) {
    const st = document.getElementById('toolStatus');
    if (st) { st.classList.add('is-err'); st.textContent = String(e); }
  }
}

document.getElementById('btnToolRefresh') && document.getElementById('btnToolRefresh').addEventListener('click', function() { loadTools(); });

// ---------------- Agent page load orchestration ----------------

async function loadAgentPage() {
  await loadSkills();
  await loadTools();
  if (typeof loadMdFiles === 'function') {
    await loadMdFiles();
  }
}
