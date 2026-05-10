
const THINK_KEY = 'oa_enable_thinking';
function getThinkState() {
  try {
    const v = localStorage.getItem(THINK_KEY);
    if (v === null) return true;
    return v === '1';
  } catch (_) { return true; }
}
function setThinkState(on) {
  try { localStorage.setItem(THINK_KEY, on ? '1' : '0'); } catch (_) {}
  if (thinkToggle) {
    thinkToggle.setAttribute('aria-pressed', on ? 'true' : 'false');
    thinkToggle.title = on
      ? '思考：已开启。模型会先思考再回答（慢但更准）。点击关闭。'
      : '思考：已关闭。模型直接回答（更快）。点击开启。';
  }
}
if (thinkToggle) {
  setThinkState(getThinkState());
  thinkToggle.addEventListener('click', () => setThinkState(!getThinkState()));
}

// ---------------- Session/agent identity ----------------

const READ_KEY = 'oa_sess_last_read_v2';
let lastSessionsCache = [];
let webuiSessionsEnabled = false;
let agentId = 'default';

/** RFC4122 v4；在 HTTP 或非 Chromium 旧版等环境下 crypto.randomUUID 可能不存在。 */
function oaRandomUUID() {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch (_) {}
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    var r = (Math.random() * 16) | 0;
    var v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function projectStorageKey(aid) {
  return 'oa_proj_id_' + String(aid || 'default');
}
function loadProjectIdForAgent(aid) {
  try { return localStorage.getItem(projectStorageKey(aid)) || ''; } catch (_) { return ''; }
}
function saveProjectIdForAgent(aid, pid) {
  try { localStorage.setItem(projectStorageKey(aid), String(pid || '').trim()); } catch (_) {}
}

let projectId = loadProjectIdForAgent(agentId);

// Transcript paging state
let transcriptFirstBlockIndex = null;
let transcriptHasMoreOlder = false;
let transcriptLoadingOlder = false;
let transcriptScrollTimer = null;
let transcriptPagingBound = false;

function _sidStorageKey(aid, pid) {
  const p = String(pid || '').trim();
  const tail = p ? '_p_' + p : '_g';
  return 'oa_sid_v5_' + String(aid || 'default') + tail;
}
function loadSessionIdForAgent(aid, pid) {
  const p = String(pid || '').trim();
  const key = _sidStorageKey(aid, p);
  let sid = localStorage.getItem(key) || '';
  if (!sid && !p) {
    const legacy = localStorage.getItem('oa_sid_' + String(aid || 'default')) || '';
    if (legacy) { sid = legacy; localStorage.setItem(key, sid); }
  }
  if (!sid) { sid = oaRandomUUID(); localStorage.setItem(key, sid); }
  return sid;
}
function saveSessionIdForAgent(aid, pid, sid) {
  try {
    localStorage.setItem(_sidStorageKey(aid, pid), String(sid || '').trim());
  } catch (_) {}
}

function projectQuerySuffix() {
  return '&project_id=' + encodeURIComponent(projectId || '');
}

var treeExpanded = {};
var treeProjectActiveId = '';
var treeProjectRenderGen = 0;
/** 最近一次拉取的项目列表；展开/折叠等仅本地重绘时复用，避免重复 GET /api/ui/projects */
var treeProjectsCache = null;
/** 每个项目下列表请求的代数，丢弃过期回调（不等同于整棵树重建） */
var treeSessionsGenByPid = Object.create(null);

function treePid(id) {
  return String(id == null ? '' : id);
}
function treeIsExpanded(id) {
  return treeExpanded[treePid(id)] === true;
}

function bumpSessionsGen(pid) {
  var k = treePid(pid);
  treeSessionsGenByPid[k] = (treeSessionsGenByPid[k] || 0) + 1;
  return treeSessionsGenByPid[k];
}
function sessionsFetchStale(pid, gen) {
  return treeSessionsGenByPid[treePid(pid)] !== gen;
}

function findProjDiv(pid) {
  var k = treePid(pid);
  var sel = '.tree-project[data-project-id="' + k.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"]';
  try {
    if (typeof CSS !== 'undefined' && CSS.escape) {
      sel = '.tree-project[data-project-id="' + CSS.escape(k) + '"]';
    }
  } catch (_) {}
  return document.querySelector(sel);
}

function syncTreeProjectActiveHighlight() {
  document.querySelectorAll('.tree-project').forEach(function(projDiv) {
    var pid = treePid(projDiv.dataset.projectId);
    var row = projDiv.querySelector('.tree-project__row');
    if (!row) return;
    var isActive = pid === treePid(projectId) || pid === treePid(treeProjectActiveId);
    row.classList.toggle('tree-project__row--active', isActive);
    row.querySelectorAll('.tree-project__active-bar').forEach(function(b) { b.remove(); });
    if (isActive) {
      var bar = document.createElement('div');
      bar.className = 'tree-project__active-bar';
      row.appendChild(bar);
    }
  });
}

function syncTreeSessionActiveHighlight() {
  document.querySelectorAll('.tree-session__row').forEach(function(sRow) {
    var sid = sRow.getAttribute('data-session-id');
    if (!sid) return;
    sRow.classList.toggle('tree-session__row--active', sid === sessionId);
  });
}

function fillSessionsList(childrenEl, pid, sessions) {
  var k = treePid(pid);
  childrenEl.innerHTML = '';
  if (!sessions || sessions.length === 0) {
    var empty = document.createElement('div');
    empty.className = 'tree-session__empty';
    empty.textContent = '暂无会话';
    childrenEl.appendChild(empty);
    return;
  }
  sessions.forEach(function(s) {
    var sDiv = document.createElement('div');
    sDiv.className = 'tree-session';
    sDiv.setAttribute('data-session-id', s.session_id);
    // 检查运行态
    if (typeof chatInflightBySid !== 'undefined' && (chatInflightBySid[s.session_id] || 0) > 0) {
      sDiv.classList.add('is-running');
    }
    var sRow = document.createElement('div');
    sRow.className = 'tree-session__row' + (s.session_id === sessionId ? ' tree-session__row--active' : '');
    if (s.unread) sRow.classList.add('tree-session__row--unread');
    sRow.setAttribute('data-session-id', s.session_id);

    var ind = document.createElement('span');
    ind.className = 'tree-session__indicator';
    sRow.appendChild(ind);

    var sTitle = document.createElement('span');
    sTitle.className = 'tree-session__title';
    sTitle.textContent = s.display_title || s.session_id || '会话';
    sRow.appendChild(sTitle);

    var sMenu = document.createElement('button');
    sMenu.type = 'button'; sMenu.className = 'tree-session__menu';
    sMenu.textContent = '⋮';
    sMenu.addEventListener('click', function(e) {
      e.stopPropagation();
      showSessionContextMenu(e, s.session_id, k);
    });
    sRow.appendChild(sMenu);

    sRow.addEventListener('click', function() {
      if (s.session_id === sessionId) return;
      if (k !== treePid(projectId)) {
        projectId = k; treeProjectActiveId = k; window.dispatchEvent(new CustomEvent('project-changed', {detail: {projectId: k}}));
        saveProjectIdForAgent(agentId, projectId);
      }
      sessionId = s.session_id;
      saveSessionIdForAgent(agentId, projectId, sessionId);
      window.dispatchEvent(new CustomEvent('session-changed', {detail: {sessionId: sessionId, projectId: projectId}}));
      updateComposerButtons();
      log.innerHTML = '';
      try { reconnectWsForSession(); } catch (_) {}
      loadTranscriptIntoLog(true);
      syncTreeProjectActiveHighlight();
      syncTreeSessionActiveHighlight();
    });
    sDiv.appendChild(sRow);
    childrenEl.appendChild(sDiv);
  });

}

function loadSessionsIntoContainer(childrenEl, pid) {
  var k = treePid(pid);
  var sg = bumpSessionsGen(k);
  fetchSessionsForProject(k).then(function(sessions) {
    if (sessionsFetchStale(k, sg)) return;
    if (!treeIsExpanded(k)) return;
    if (!childrenEl.isConnected) return;
    // 当前会话属于此项目但尚未落盘（新创建）→ 加占位条目
    if (treePid(pid) === treePid(projectId) && sessionId &&
        !sessions.some(function(s) { return s.session_id === sessionId; })) {
      sessions = [{ session_id: sessionId, message_count: 0, display_title: '新对话', channel: 'Web 聊天', preview: '' }].concat(sessions);
    }
    fillSessionsList(childrenEl, k, sessions);
    syncTreeSessionActiveHighlight();
  });
}

function applyProjectExpandStateToDom(pid) {
  var k = treePid(pid);
  var projDiv = findProjDiv(k);
  if (!projDiv) return;
  var expanded = treeIsExpanded(k);
  var toggle = projDiv.querySelector('.tree-project__toggle');
  if (toggle) {
    toggle.classList.toggle('tree-project__toggle--expanded', expanded);
    toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }
  var existing = projDiv.querySelector(':scope > .tree-sessions');
  var inlineNew = projDiv.querySelector(':scope > .tree-session__new');

  if (expanded) {
    if (inlineNew) inlineNew.remove();
    if (!existing) {
      var children = document.createElement('div');
      children.className = 'tree-sessions';
      children.dataset.projectId = k;
      projDiv.appendChild(children);
      loadSessionsIntoContainer(children, k);
    }
  } else {
    if (existing) existing.remove();

  }
}

function toggleTreeProjectExpanded(pid) {
  var k = treePid(pid);
  treeExpanded[k] = !treeIsExpanded(k);
  applyProjectExpandStateToDom(k);
}

function handleProjectRowClick(pid) {
  var k = treePid(pid);
  if (k === treePid(projectId)) {
    toggleTreeProjectExpanded(k);
    return;
  }
  treeProjectActiveId = k;
  projectId = k;
  window.dispatchEvent(new CustomEvent('project-changed', {detail: {projectId: k}}));
  treeExpanded[k] = true;
  saveProjectIdForAgent(agentId, projectId);

  function finishProjectSwitch(targetSid) {
    sessionId = targetSid;
    saveSessionIdForAgent(agentId, projectId, sessionId);
    try {
      window.dispatchEvent(new CustomEvent('session-changed', {detail: {sessionId: sessionId, projectId: k}}));
    } catch (_) {}
    updateComposerButtons();
    log.innerHTML = '';
    try { reconnectWsForSession(); } catch (_) {}
    applyProjectExpandStateToDom(k);
    syncTreeProjectActiveHighlight();
    syncTreeSessionActiveHighlight();
    if (typeof refreshSessionList === 'function') refreshSessionList().catch(function() {});
    if (typeof loadTranscriptIntoLog === 'function') loadTranscriptIntoLog(true).catch(function() {});
    var inp = document.getElementById('treeSearchInput');
    if (inp) inp.value = '';
  }

  fetchSessionsForProject(k).then(function(sessions) {
    var list = sessions || [];
    if (list.length > 0) {
      finishProjectSwitch(list[0].session_id);
    } else {
      finishProjectSwitch(loadSessionIdForAgent(agentId, projectId));
    }
  }).catch(function() {
    finishProjectSwitch(loadSessionIdForAgent(agentId, projectId));
  });
}

function createProjectNode(pr) {
  var pid = treePid(pr.id);
  var displayName = pr.name || pr.id;
  var expanded = treeIsExpanded(pid);
  var isActive = pid === treePid(treeProjectActiveId) || pid === treePid(projectId);

  var projDiv = document.createElement('div');
  projDiv.className = 'tree-project';
  projDiv.dataset.projectId = pid;

  var row = document.createElement('div');
  row.className = 'tree-project__row' + (isActive ? ' tree-project__row--active' : '');

  var toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'tree-project__toggle' + (expanded ? ' tree-project__toggle--expanded' : '');
  toggle.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  toggle.addEventListener('click', function(e) {
    e.stopPropagation();
    toggleTreeProjectExpanded(pid);
  });
  row.appendChild(toggle);

  var icon = document.createElement('span');
  icon.className = 'tree-project__icon';
  if (pid === '__unassigned__') {
    icon.innerHTML = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M2 3h12v10H2V3zm1 1v5h3l1 2h2l1-2h3V4H3z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/></svg>';
  } else {
    icon.innerHTML = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3 6.5h3L6.5 5H12a1 1 0 011 1v7a1 1 0 01-1 1H4a1 1 0 01-1-1v-6.5z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/><path d="M3 6.5V5.5a1 1 0 011-1h2.5L8 5" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/></svg>';
  }
  row.appendChild(icon);

  var name = document.createElement('span');
  name.className = 'tree-project__name';
  name.textContent = displayName;
  row.appendChild(name);

  var addBtn = document.createElement('button');
  addBtn.type = 'button'; addBtn.className = 'tree-project__add-session';
  addBtn.textContent = '+';
  addBtn.setAttribute('aria-label', '新建会话');
  addBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    // 切换到该项目，然后创建新会话
    if (pid !== treePid(projectId)) {
      projectId = pid; treeProjectActiveId = pid;
      window.dispatchEvent(new CustomEvent('project-changed', {detail: {projectId: pid}}));
      saveProjectIdForAgent(agentId, projectId);
    }
    document.getElementById('btnNewSession').click();
  });
  row.appendChild(addBtn);

  var menu = document.createElement('button');
  menu.type = 'button'; menu.className = 'tree-project__menu';
  menu.textContent = '⋮';
  menu.addEventListener('click', function(e) {
    e.stopPropagation();
    showProjectContextMenu(e, pid, name.textContent || displayName);
  });
  row.appendChild(menu);

  if (isActive) {
    var bar = document.createElement('div');
    bar.className = 'tree-project__active-bar';
    row.appendChild(bar);
  }

  row.addEventListener('click', function() {
    handleProjectRowClick(pid);
  });
  projDiv.appendChild(row);

  if (expanded) {
    var children = document.createElement('div');
    children.className = 'tree-sessions';
    children.dataset.projectId = pid;
    projDiv.appendChild(children);
    loadSessionsIntoContainer(children, pid);
  }

  return projDiv;
}

function refreshSessionsUnderProject(pid) {
  var k = treePid(pid || projectId);
  var projDiv = findProjDiv(k);
  if (!projDiv) return;
  var box = projDiv.querySelector(':scope > .tree-sessions');
  if (!box) return;
  box.innerHTML = '';
  loadSessionsIntoContainer(box, k);
}

function appendProjectTreeNode(pr) {
  var treeEl = document.getElementById('projectTree');
  if (!treeEl) return;
  var empty = treeEl.querySelector('.project-tree__empty');
  if (empty) empty.remove();
  treeEl.appendChild(createProjectNode(pr));
  syncTreeProjectActiveHighlight();
  syncTreeSessionActiveHighlight();
}

/**
 * @param {boolean} [forceFetch] 为 true 时始终向服务端拉项目列表；默认 false（有缓存且 agent 未变则只用缓存）。
 * 仅在此处整棵树替换 DOM；展开/折叠走 applyProjectExpandStateToDom，不重绘兄弟节点。
 */
async function refreshProjects(forceFetch) {
  if (forceFetch === undefined) forceFetch = false;
  var treeEl = document.getElementById('projectTree');
  if (!treeEl) return;
  var renderGen = ++treeProjectRenderGen;
  try {
    var projects;
    var cacheOk = !forceFetch && treeProjectsCache && treeProjectsCache.aid === agentId &&
      Array.isArray(treeProjectsCache.projects);
    if (cacheOk) {
      projects = treeProjectsCache.projects.slice();
      if (renderGen !== treeProjectRenderGen) return;
    } else {
      var r = await fetch('/api/ui/projects?agent_id=' + encodeURIComponent(agentId));
      if (renderGen !== treeProjectRenderGen) return;
      if (!r.ok) return;
      var j = await r.json();
      if (renderGen !== treeProjectRenderGen) return;
      projects = j.projects || [];
      treeProjectsCache = { aid: agentId, projects: projects };
    }
    treeEl.innerHTML = '';
    if (projects.length === 0) {
      treeEl.innerHTML = '<div class="project-tree__empty">暂无项目，点击下方按钮新建</div>';
      return;
    }
    var curPk = treePid(projectId);
    if (curPk && treeExpanded[curPk] === undefined) {
      treeExpanded[curPk] = true;
    }
    projects.forEach(function(pr) {
      treeEl.appendChild(createProjectNode(pr));
    });
  } catch (_) {}
}

async function fetchSessionsForProject(pid) {
  try {
    var r = await fetch('/api/ui/sessions?agent_id=' + encodeURIComponent(agentId) + '&project_id=' + encodeURIComponent(pid));
    if (!r.ok) return [];
    var j = await r.json();
    return j.sessions || [];
  } catch(_) { return []; }
}

function getTreeProjectPath(pid) {
  var k = treePid(pid);
  if (!k || typeof treeProjectsCache === 'undefined' || !treeProjectsCache || treeProjectsCache.aid !== agentId) return '';
  for (var i = 0; i < treeProjectsCache.projects.length; i++) {
    var p = treeProjectsCache.projects[i];
    if (treePid(p.id) === k && p.path) return String(p.path);
  }
  return '';
}

function closeProjectDirectoryDialog() {
  var el = document.getElementById('projectDirDialog');
  if (el) el.remove();
}

/** 侧栏项目 ⋮ 菜单：设置/查看关联的源代码目录 */
function showProjectDirectoryDialog(pid) {
  closeProjectDirectoryDialog();
  var k = treePid(pid);
  var curPath = getTreeProjectPath(k);

  var root = document.createElement('div');
  root.id = 'projectDirDialog';
  root.className = 'modal-overlay';
  root.style.display = 'flex';

  var dlg = document.createElement('div');
  dlg.className = 'modal-dialog';
  dlg.addEventListener('click', function(ev) { ev.stopPropagation(); });

  var header = document.createElement('div');
  header.className = 'modal-dialog__header';
  var title = document.createElement('span');
  title.className = 'modal-dialog__title';
  title.textContent = '项目目录';
  var btnClose = document.createElement('button');
  btnClose.type = 'button';
  btnClose.className = 'modal-dialog__close';
  btnClose.innerHTML = '&times;';
  btnClose.setAttribute('aria-label', '关闭');
  header.appendChild(title);
  header.appendChild(btnClose);

  var body = document.createElement('div');
  body.className = 'modal-dialog__body';
  var field = document.createElement('div');
  field.className = 'modal-field';
  var lab = document.createElement('label');
  lab.className = 'modal-field__label';
  lab.setAttribute('for', 'inpProjectDirPath');
  lab.textContent = '文件系统路径';
  var row = document.createElement('div');
  row.className = 'modal-field__input-row';
  var inp = document.createElement('input');
  inp.type = 'text';
  inp.id = 'inpProjectDirPath';
  inp.className = 'modal-field__input';
  inp.placeholder = '例如：/Users/kun/my-project';
  inp.value = curPath;
  var btnBrowse = document.createElement('button');
  btnBrowse.type = 'button';
  btnBrowse.className = 'modal-btn modal-btn--browse';
  btnBrowse.title = '浏览选择目录';
  btnBrowse.textContent = '📁 浏览';
  row.appendChild(inp);
  row.appendChild(btnBrowse);
  var hint = document.createElement('p');
  hint.className = 'modal-field__hint';
  hint.textContent = '关联源代码目录后，文件树和 Git 面板可直接操作项目文件';
  field.appendChild(lab);
  field.appendChild(row);
  field.appendChild(hint);
  body.appendChild(field);

  var footer = document.createElement('div');
  footer.className = 'modal-dialog__footer';
  var btnCancel = document.createElement('button');
  btnCancel.type = 'button';
  btnCancel.className = 'modal-btn modal-btn--cancel';
  btnCancel.textContent = '取消';
  var btnSave = document.createElement('button');
  btnSave.type = 'button';
  btnSave.className = 'modal-btn modal-btn--confirm';
  btnSave.textContent = '保存';
  footer.appendChild(btnCancel);
  footer.appendChild(btnSave);

  dlg.appendChild(header);
  dlg.appendChild(body);
  dlg.appendChild(footer);
  root.appendChild(dlg);

  function doClose() { closeProjectDirectoryDialog(); }

  btnBrowse.addEventListener('click', function() {
    btnBrowse.textContent = '⏳ 选择中…';
    btnBrowse.disabled = true;
    fetch('/api/ui/pick-directory', { method: 'POST', credentials: 'same-origin' })
      .then(function(r) { return r.json(); })
      .then(function(j) {
        if (j.path) inp.value = j.path;
        else if (j.detail) console.warn('pick-directory:', j.detail);
      })
      .catch(function(err) { console.error('pick-directory error:', err); })
      .finally(function() {
        btnBrowse.textContent = '📁 浏览';
        btnBrowse.disabled = false;
      });
  });

  btnClose.addEventListener('click', doClose);
  btnCancel.addEventListener('click', doClose);
  root.addEventListener('click', function(ev) {
    if (ev.target === root) doClose();
  });

  btnSave.addEventListener('click', function() {
    var p = inp.value.trim();
    if (!p) {
      alert('请填写目录路径，或使用「浏览」选择');
      inp.focus();
      return;
    }
    btnSave.disabled = true;
    fetch('/api/ui/projects/path', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ agent_id: agentId, project_id: k, path: p })
    }).then(function(r) {
      if (!r.ok) {
        alert('保存失败');
        return;
      }
      if (treeProjectsCache && treeProjectsCache.aid === agentId) {
        treeProjectsCache.projects.forEach(function(proj) {
          if (treePid(proj.id) === k) proj.path = p;
        });
      }
      doClose();
      try { document.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: k } })); } catch (_) {}
    }).catch(function() { alert('保存失败'); })
      .finally(function() { btnSave.disabled = false; });
  });

  document.body.appendChild(root);
  setTimeout(function() { inp.focus(); inp.select(); }, 80);
}

function showProjectContextMenu(e, pid, name) {
  e.preventDefault();
  var existing = document.querySelector('.tree-overlay');
  if (existing) existing.remove();
  var menu = document.createElement('div');
  menu.className = 'tree-context-menu';
  menu.style.left = e.clientX + 'px';
  menu.style.top = e.clientY + 'px';
  var isUnassigned = pid === '__unassigned__';
  var items = [];
  if (!isUnassigned) {
    items.push({label: '重命名', action: function() { renameProject(pid, name); }});
    items.push({label: '项目目录', action: function() { showProjectDirectoryDialog(pid); }});
  }
  items.push({label: '复制 ID', action: function() { copyToClipboard(pid); }});
  if (!isUnassigned) {
    items.push({label: '删除项目', action: function() { deleteProject(pid); }, dangerous: true});
  }
  items.forEach(function(item) {
    var btn = document.createElement('button');
    btn.className = 'tree-context-menu__item' + (item.dangerous ? ' tree-context-menu__item--danger' : '');
    btn.textContent = item.label;
    btn.addEventListener('click', function() { closeContextMenu(); item.action(); });
    menu.appendChild(btn);
  });
  var overlay = document.createElement('div');
  overlay.className = 'tree-overlay';
  overlay.addEventListener('click', closeContextMenu);
  document.body.appendChild(overlay);
  document.body.appendChild(menu);
}

function showSessionContextMenu(e, sid, pid) {
  e.preventDefault();
  var existing = document.querySelector('.tree-overlay');
  if (existing) existing.remove();
  var menu = document.createElement('div');
  menu.className = 'tree-context-menu';
  menu.style.left = e.clientX + 'px';
  menu.style.top = e.clientY + 'px';
  var items = [
    {label: '复制 ID', action: function() { copyToClipboard(sid); }},
    {label: '删除会话', action: function() { deleteSession(sid, pid); }, dangerous: true}
  ];
  items.forEach(function(item) {
    var btn = document.createElement('button');
    btn.className = 'tree-context-menu__item' + (item.dangerous ? ' tree-context-menu__item--danger' : '');
    btn.textContent = item.label;
    btn.addEventListener('click', function() { closeContextMenu(); item.action(); });
    menu.appendChild(btn);
  });
  var overlay = document.createElement('div');
  overlay.className = 'tree-overlay';
  overlay.addEventListener('click', closeContextMenu);
  document.body.appendChild(overlay);
  document.body.appendChild(menu);
}

function closeContextMenu() {
  var overlay = document.querySelector('.tree-overlay');
  var menu = document.querySelector('.tree-context-menu');
  if (overlay) overlay.remove();
  if (menu) menu.remove();
}

function copyToClipboard(text) {
  try {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select(); document.execCommand('copy');
    document.body.removeChild(ta);
  } catch(_) {}
}

function renameProject(pid, currentName) {
  var newName = prompt('请输入新项目名称:', currentName);
  if (!newName || newName === currentName) return;
  fetch('/api/ui/projects/rename', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    credentials: 'same-origin',
    body: JSON.stringify({ agent_id: agentId, project_id: pid, name: newName })
  }).then(function(r) {
    if (r.ok) {
      if (treeProjectsCache && treeProjectsCache.aid === agentId) {
        treeProjectsCache.projects.forEach(function(p) {
          if (treePid(p.id) === treePid(pid)) p.name = newName;
        });
      }
      var rdiv = findProjDiv(pid);
      if (rdiv) {
        var nm = rdiv.querySelector('.tree-project__name');
        if (nm) nm.textContent = newName;
      }
    } else alert('重命名失败');
  }).catch(function() { alert('重命名失败'); });
}

function deleteProject(pid) {
  if (!confirm('确定删除此项目及其所有会话吗？')) return;
  fetch('/api/ui/projects/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    credentials: 'same-origin',
    body: JSON.stringify({ agent_id: agentId, project_id: pid })
  }).then(function(r) {
    if (r.ok) {
      if (treePid(projectId) === treePid(pid)) {
        projectId = ''; treeProjectActiveId = ''; saveProjectIdForAgent(agentId, '');
      }
      delete treeExpanded[treePid(pid)];
      if (treeProjectsCache && treeProjectsCache.aid === agentId) {
        treeProjectsCache.projects = treeProjectsCache.projects.filter(function(p) {
          return treePid(p.id) !== treePid(pid);
        });
      }
      var treeEl = document.getElementById('projectTree');
      var pdiv = findProjDiv(pid);
      if (pdiv) pdiv.remove();
      if (treeEl && !treeEl.querySelector('.tree-project')) {
        treeEl.innerHTML = '<div class="project-tree__empty">暂无项目，点击下方按钮新建</div>';
      }
      syncTreeProjectActiveHighlight();
    } else alert('删除失败');
  }).catch(function() { alert('删除失败'); });
}

function deleteSession(sid, pid) {
  if (!confirm('确定删除此会话吗？')) return;
  fetch('/api/ui/session/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    credentials: 'same-origin',
    body: JSON.stringify({ session_id: sid, agent_id: agentId })
  }).then(function(r) {
    if (r.ok) {
      if (sessionId === sid) {
        sessionId = oaRandomUUID();
        localStorage.setItem(_sidStorageKey(agentId, pid || projectId), sessionId);
        log.innerHTML = '';
        try { reconnectWsForSession(); } catch (_) {}
      }
      refreshSessionsUnderProject(pid || projectId);
      syncTreeSessionActiveHighlight();
      // 未分类会话删除后可能空了，刷新项目列表以移除虚拟项目
      if ((pid || projectId) === '__unassigned__' && typeof refreshProjects === 'function') {
        refreshProjects();
      }
      if (typeof refreshSessionList === 'function') refreshSessionList().catch(function() {});
    } else alert('删除失败');
  }).catch(function() { alert('删除失败'); });
}

let sessionId = loadSessionIdForAgent(agentId, projectId);

// ---------------- Core utility functions ----------------

function escapeHtml(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escAttr(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function normReply(s) {
  return String(s || '').replace(/\r\n/g, '\n').trim();
}
function formatBubbleTime(at) {
  if (at == null || at === '') return '';
  const d = typeof at === 'number' ? new Date(at) : new Date(at);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  });
}

// ---------------- Chat inflight tracking ----------------
