/* ================================================================
 * 13c-skills-panel.js — 项目技能面板 (📚)
 *   - 顶部栏 📚 按钮打开/关闭
 *   - 列出当前项目的项目级技能（project scope）
 *   - 支持新增/编辑/删除/启停
 *   - 监听 project-changed 事件自动刷新
 * ================================================================ */

(function() {

var btnToggle = document.getElementById('btnToggleSkills');
var skillPanel = document.getElementById('skillPanel');
var skillList = document.getElementById('skillPanelList');
var skillStatus = document.getElementById('skillPanelStatus');
var btnRefresh = document.getElementById('btnSkillPanelRefresh');
var btnAdd = document.getElementById('btnSkillPanelAdd');

if (!btnToggle || !skillPanel || !skillList) return;

// 只在有项目时显示 📚 按钮
function updateButtonVisibility() {
  var pid = typeof projectId !== 'undefined' ? (projectId || '') : '';
  btnToggle.style.display = pid ? '' : 'none';
  // 如果项目已切换且面板还开着，刷新
  if (pid && skillPanel.style.display !== 'none') {
    refreshSkills();
  }
  // 如果项目没了但面板还开着，关闭
  if (!pid && skillPanel.style.display !== 'none') {
    skillPanel.style.display = 'none';
    btnToggle.classList.remove('is-active');
  }
}

function skillPanelIsVisible() {
  return skillPanel.style.display === 'flex';
}

// Toggle
btnToggle.addEventListener('click', function() {
  var opening = !skillPanelIsVisible();
  skillPanel.style.display = opening ? 'flex' : 'none';
  btnToggle.classList.toggle('is-active', opening);
  if (opening) {
    // 如果在文件模式，先切回聊天
    if (typeof _activeMode !== 'undefined' && _activeMode === 'files' && typeof switchActivityMode === 'function') {
      switchActivityMode('chat');
    }
    _closeOtherPanels();
    refreshSkills();
  }
});

// 互斥：打开技能面板时关闭其他面板
function _closeOtherPanels() {
  var ids = [
    { panel: 'planPanel',   btn: 'btnTogglePlans',   key: 'PLAN_PANEL_OPEN' },
    { panel: 'todoPanel',   btn: 'btnToggleTodos',    key: 'TODO_PANEL_OPEN' },
    { panel: 'gitPanel',    btn: 'btnToggleGit',      key: 'GIT_PANEL_OPEN' },
  ];
  ids.forEach(function(item) {
    var p = document.getElementById(item.panel);
    var b = document.getElementById(item.btn);
    if (p && p.style.display !== 'none') {
      p.style.display = 'none';
      if (b) b.classList.remove('is-active');
      if (typeof trySetLS === 'function' && STORAGE_KEYS && STORAGE_KEYS[item.key]) {
        trySetLS(STORAGE_KEYS[item.key], '0');
      }
    }
  });
}

if (btnRefresh) {
  btnRefresh.addEventListener('click', refreshSkills);
}

if (btnAdd) {
  btnAdd.addEventListener('click', function() {
    openSkillEditor(null);
  });
}

// 监听项目切换
document.addEventListener('project-changed', function() {
  updateButtonVisibility();
});

// 初始化
updateButtonVisibility();

// ---- API ----

function getProjectId() {
  return typeof projectId !== 'undefined' ? (projectId || '') : '';
}

async function fetchSkills() {
  var pid = getProjectId();
  if (!pid) return [];
  var aid = typeof agentId !== 'undefined' ? (agentId || 'default') : 'default';
  try {
    var url = '/api/ui/skills?agent_id=' + encodeURIComponent(aid) + '&project_id=' + encodeURIComponent(pid);
    var r = await fetch(url);
    if (!r.ok) return [];
    var j = await r.json();
    // 只返回 project scope 的技能
    return (j.skills || []).filter(function(s) { return s.scope === 'project'; });
  } catch (_) { return []; }
}

async function saveSkill(name, content, enabled) {
  var aid = typeof agentId !== 'undefined' ? (agentId || 'default') : 'default';
  var pid = getProjectId();
  try {
    var url = '/api/ui/skills?agent_id=' + encodeURIComponent(aid) + '&project_id=' + encodeURIComponent(pid);
    var body = { action: 'save', name: name, content: content };
    if (enabled !== undefined) body.enabled = enabled;
    var r = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    var j = await r.json().catch(function() { return {}; });
    if (!r.ok) throw new Error(j.detail || r.statusText);
    return j;
  } catch (e) { throw e; }
}

async function deleteSkill(name) {
  var aid = typeof agentId !== 'undefined' ? (agentId || 'default') : 'default';
  var pid = getProjectId();
  try {
    var url = '/api/ui/skills?agent_id=' + encodeURIComponent(aid) + '&project_id=' + encodeURIComponent(pid);
    var r = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'delete', name: name })
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  } catch (e) { throw e; }
}

// ---- 渲染 ----

async function refreshSkills() {
  var skills = await fetchSkills();
  if (!skillList) return;
  skillList.innerHTML = '';

  if (!skills || skills.length === 0) {
    skillList.innerHTML = '<div class="plan-empty">当前项目暂无项目级技能。<br/>项目技能仅在该项目中生效，覆盖 Agent 级同名技能。</div>';
    if (skillStatus) skillStatus.textContent = '';
    return;
  }

  if (skillStatus) skillStatus.textContent = skills.length + ' 个技能';

  skills.forEach(function(s) {
    skillList.appendChild(buildSkillCard(s));
  });
}

function buildSkillCard(s) {
  var wrap = document.createElement('div');
  wrap.className = 'cron-card-wrap';

  var header = document.createElement('div');
  header.className = 'cron-card';

  var info = document.createElement('div');
  info.className = 'cron-card__info';

  var nameRow = document.createElement('div');
  nameRow.className = 'cron-card__name';
  nameRow.textContent = s.name;

  var badge = document.createElement('span');
  badge.className = 'cron-card__badge' + (s.enabled !== false ? '' : ' cron-card__badge-off');
  badge.textContent = (s.enabled !== false) ? '启用' : '停用';
  nameRow.appendChild(badge);
  info.appendChild(nameRow);

  var detail = document.createElement('div');
  detail.className = 'cron-card__detail';
  detail.textContent = s.path || '';
  info.appendChild(detail);

  var actions = document.createElement('div');
  actions.className = 'cron-card__actions';

  var btnToggle = document.createElement('button');
  btnToggle.type = 'button'; btnToggle.className = 'btn btn--ghost btn--xs';
  btnToggle.textContent = (s.enabled !== false) ? '停用' : '启用';
  btnToggle.addEventListener('click', function(ev) {
    ev.stopPropagation();
    s.enabled = !(s.enabled !== false);
    toggleSkillEnabled(s);
  });
  actions.appendChild(btnToggle);

  var btnEdit = document.createElement('button');
  btnEdit.type = 'button'; btnEdit.className = 'btn btn--ghost btn--xs';
  btnEdit.textContent = '编辑';
  btnEdit.addEventListener('click', function(ev) {
    ev.stopPropagation();
    openSkillEditor(s);
  });
  actions.appendChild(btnEdit);

  var btnDel = document.createElement('button');
  btnDel.type = 'button'; btnDel.className = 'btn btn--ghost btn--xs cron-del';
  btnDel.textContent = '删除';
  btnDel.addEventListener('click', function(ev) {
    ev.stopPropagation();
    if (!confirm('确定删除技能「' + s.name + '」？')) return;
    doDeleteSkill(s.name);
  });
  actions.appendChild(btnDel);

  header.appendChild(info);
  header.appendChild(actions);
  wrap.appendChild(header);
  return wrap;
}

// ---- CRUD ----

async function toggleSkillEnabled(s) {
  try {
    await saveSkill(s.name, s.content || '', s.enabled);
    await refreshSkills();
  } catch (e) {
    if (skillStatus) { skillStatus.classList.add('is-err'); skillStatus.textContent = String(e); }
  }
}

async function doDeleteSkill(name) {
  try {
    await deleteSkill(name);
    await refreshSkills();
  } catch (e) {
    if (skillStatus) { skillStatus.classList.add('is-err'); skillStatus.textContent = String(e); }
  }
}

function openSkillEditor(existing) {
  // 简单的弹窗编辑器
  var name = existing ? existing.name : '';
  var content = existing ? (existing.content || '') : '';
  var isNew = !existing;

  // 检查之前创建的 dialog 是否已存在，避免多个
  var oldOverlay = document.getElementById('skillEditorOverlay');
  if (oldOverlay) oldOverlay.remove();

  var overlay = document.createElement('div');
  overlay.id = 'skillEditorOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;';

  var dialog = document.createElement('div');
  dialog.style.cssText = 'background:var(--bg);border:1px solid var(--border);border-radius:var(--r-md);padding:var(--sp-4);width:560px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,0.2);';

  var title = document.createElement('div');
  title.style.cssText = 'font-weight:600;font-size:15px;margin-bottom:var(--sp-3);';
  title.innerHTML = isNew ? '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="vertical-align:-3px;margin-right:4px;"><path d="M8 1l2 5.5h5.5l-4.5 3L12 15 8 11.5 4 15l1-5.5-4.5-3H6z"/></svg> 新建项目技能' : '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="vertical-align:-3px;margin-right:4px;"><path d="M8 1l2 5.5h5.5l-4.5 3L12 15 8 11.5 4 15l1-5.5-4.5-3H6z"/></svg> 编辑项目技能';
  dialog.appendChild(title);

  var fldName = document.createElement('input');
  fldName.type = 'text';
  fldName.placeholder = '技能名称.skill.md（如 my-skill.md）';
  fldName.value = name;
  fldName.style.cssText = 'width:100%;padding:var(--sp-2);border:1px solid var(--border);border-radius:var(--r-sm);background:var(--bg);color:var(--text);font-size:13px;margin-bottom:var(--sp-2);box-sizing:border-box;';
  dialog.appendChild(fldName);

  var fldBody = document.createElement('textarea');
  fldBody.placeholder = 'Markdown 内容...';
  fldBody.value = content;
  fldBody.style.cssText = 'width:100%;min-height:200px;padding:var(--sp-2);border:1px solid var(--border);border-radius:var(--r-sm);background:var(--bg);color:var(--text);font-size:13px;font-family:var(--font-mono);resize:vertical;box-sizing:border-box;margin-bottom:var(--sp-2);';
  dialog.appendChild(fldBody);

  var statusLine = document.createElement('div');
  statusLine.style.cssText = 'font-size:12px;color:var(--text-muted);margin-bottom:var(--sp-2);';
  dialog.appendChild(statusLine);

  var rowActions = document.createElement('div');
  rowActions.style.cssText = 'display:flex;gap:var(--sp-2);justify-content:flex-end;';

  var btnCancel = document.createElement('button');
  btnCancel.type = 'button';
  btnCancel.className = 'btn btn--subtle btn--sm';
  btnCancel.textContent = '取消';
  btnCancel.addEventListener('click', function() { overlay.remove(); });
  rowActions.appendChild(btnCancel);

  var btnSave = document.createElement('button');
  btnSave.type = 'button';
  btnSave.className = 'btn btn--primary btn--sm';
  btnSave.textContent = '保存';
  btnSave.addEventListener('click', async function() {
    var n = fldName.value.trim();
    var c = fldBody.value;
    if (!n) { statusLine.textContent = '文件名不能为空'; statusLine.style.color = 'var(--err)'; return; }
    statusLine.textContent = '保存中...';
    statusLine.style.color = 'var(--text-muted)';
    try {
      await saveSkill(n, c);
      overlay.remove();
      await refreshSkills();
    } catch (e) {
      statusLine.textContent = String(e);
      statusLine.style.color = 'var(--err)';
    }
  });
  rowActions.appendChild(btnSave);

  dialog.appendChild(rowActions);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  // Focus name field
  setTimeout(function() { fldName.focus(); }, 50);

  // Close on backdrop click
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) overlay.remove();
  });
}

})();
