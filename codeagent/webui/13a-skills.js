/* ================================================================
 * 13-agent.js
 *   - Agent page: skill (Agents/<agent_id>/skills/) management,
 *     tool (integrated plugins) management,
 *     system prompt MD file editor.
 *
 * Depends on (from earlier files): agentId, refreshChatModelSelect
 * ================================================================ */

// ---------------- Skill management ----------------

async function loadSkills() {
  const list = document.getElementById('skillList');
  const status = document.getElementById('skillStatus');
  if (!list) return;
  if (status) status.classList.remove('is-err');
  try {
    const r = await fetch('/api/ui/skills?agent_id=' + encodeURIComponent(agentId));
    if (!r.ok) throw new Error(r.statusText);
    const j = await r.json();
    const skills = j.skills || [];
    list.innerHTML = '';
    if (skills.length === 0) {
      list.innerHTML = '<div class="cron-empty">暂无技能文件，点击"+ 新增"添加。</div>';
      return;
    }
    skills.forEach(function(s) { list.appendChild(buildSkillCard(s)); });
    if (status) status.textContent = '共 ' + skills.length + ' 个技能文件';
  } catch (e) {
    if (status) { status.classList.add('is-err'); status.textContent = '加载失败：' + String(e); }
  }
}

function buildSkillCard(s) {
  var wrap = document.createElement('div'); wrap.className = 'cron-card-wrap';
  var header = document.createElement('div'); header.className = 'cron-card';
  var info = document.createElement('div'); info.className = 'cron-card__info';

  var nameRow = document.createElement('div'); nameRow.className = 'cron-card__name';
  nameRow.textContent = s.name;
  var badge = document.createElement('span');
  badge.className = 'cron-card__badge' + (s.enabled !== false ? '' : ' cron-card__badge-off');
  badge.textContent = (s.enabled !== false) ? '启用' : '停用';
  nameRow.appendChild(badge);
  info.appendChild(nameRow);

  var detail = document.createElement('div'); detail.className = 'cron-card__detail';
  detail.textContent = s.path || '';
  info.appendChild(detail);

  var actions = document.createElement('div'); actions.className = 'cron-card__actions';
  var btnToggle = document.createElement('button');
  btnToggle.type = 'button'; btnToggle.className = 'btn btn--ghost btn--xs';
  btnToggle.textContent = (s.enabled !== false) ? '停用' : '启用';
  btnToggle.addEventListener('click', function(ev) {
    ev.stopPropagation();
    s.enabled = !(s.enabled !== false);
    toggleSkillEnabled(s);
  });
  actions.appendChild(btnToggle);

  var btnDel = document.createElement('button');
  btnDel.type = 'button'; btnDel.className = 'btn btn--ghost btn--xs cron-del'; btnDel.textContent = '删除';
  btnDel.addEventListener('click', function(ev) {
    ev.stopPropagation();
    if (!confirm('确定删除技能「' + s.name + '」？')) return;
    deleteSkill(s.name);
  });
  actions.appendChild(btnDel);

  header.appendChild(info); header.appendChild(actions);

  var editWrap = document.createElement('div'); editWrap.className = 'cron-edit-wrap'; editWrap.style.display = 'none';
  var editStatus = document.createElement('div'); editStatus.className = 'status-line';
  editWrap.innerHTML = '<label class="form-label">文件名</label>'
    + '<input class="skill-fld-name" type="text" value="' + escAttr(s.name) + '" placeholder="my-skill.md"/>'
    + '<label class="form-label">内容（Markdown）</label>'
    + '<textarea class="skill-fld-body" spellcheck="false" style="height:200px;font-family:var(--font-mono);font-size:13px;width:100%;padding:var(--sp-2);border:1px solid var(--border);border-radius:var(--r-sm);background:var(--bg);color:var(--text);resize:vertical;">' + escAttr(s.content || '') + '</textarea>'
    + '<div class="row-actions" style="margin-top:var(--sp-2);">'
    + '<button type="button" class="btn btn--primary btn--sm skill-save-btn">保存</button>'
    + '<button type="button" class="btn btn--subtle btn--sm skill-cancel-btn">取消</button>'
    + '</div>';
  editWrap.appendChild(editStatus);

  var toggleEdit = function(show) { editWrap.style.display = show ? 'block' : 'none'; editStatus.textContent = ''; editStatus.classList.remove('is-err'); };

  // Toggle edit on header click
  header.style.cursor = 'pointer';
  header.addEventListener('click', function(e) {
    if (e.target.closest('.btn') || e.target.closest('.cron-card__actions')) return;
    toggleEdit(editWrap.style.display !== 'block');
  });

  editWrap.querySelector('.skill-cancel-btn').addEventListener('click', function() { toggleEdit(false); });
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
      editStatus.textContent = j.hint || '已保存。';
      toggleEdit(false);
      await loadSkills();
    } catch (e) { editStatus.classList.add('is-err'); editStatus.textContent = String(e); }
  });

  wrap.appendChild(header); wrap.appendChild(editWrap);
  return wrap;
}

async function toggleSkillEnabled(s) {
  try {
    var r = await fetch('/api/ui/skills?agent_id=' + encodeURIComponent(agentId), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'save', name: s.name, content: s.content || '', enabled: s.enabled })
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    await loadSkills();
  } catch (e) {
    const st = document.getElementById('skillStatus');
    if (st) { st.classList.add('is-err'); st.textContent = String(e); }
  }
}

async function deleteSkill(name) {
  try {
    var r = await fetch('/api/ui/skills?agent_id=' + encodeURIComponent(agentId), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'delete', name: name })
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    await loadSkills();
  } catch (e) {
    const st = document.getElementById('skillStatus');
    if (st) { st.classList.add('is-err'); st.textContent = String(e); }
  }
}
