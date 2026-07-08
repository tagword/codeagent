/* ================================================================
 * 01c-session-tree.js
 *   项目树（侧栏 tree）核心渲染：
 *     - 状态: treeExpanded / treeProjectActiveId / treeProjectsCache / treeSessionsGenByPid
 *     - 工具: treePid / treeIsExpanded / bumpSessionsGen / sessionsFetchStale / findProjDiv
 *     - 高亮: syncTreeProjectActiveHighlight / syncTreeSessionActiveHighlight
 *     - 列表: fillSessionsList / loadSessionsIntoContainer / refreshSessionsUnderProject
 *             / appendProjectTreeNode / refreshProjects / fetchSessionsForProject
 *     - 节点: createProjectNode / applyProjectExpandStateToDom / toggleTreeProjectExpanded
 *             / handleProjectRowClick / getTreeProjectPath
 *
 *   右键菜单/对话框/重命名/删除在 01c-session-tree-menus.js。
 *   按字母序：'01c-session-tree-menus.js' 中字符 '-' (0x2D) < '01c-session-tree.js'
 *   字符 '.' (0x2E)，所以 menus 文件实际在 tree 文件**之前**加载；
 *   function hoisting 保证两边可互相引用。
 *
 *   依赖 01c-session-identity.js 的：
 *     agentId / projectId / sessionId / saveProjectIdForAgent / loadSessionIdForAgent
 *   依赖全局 DOM：log, projectTree, btnNewSession
 *   依赖全局函数：reconnectWsForSession, refreshSessionList, loadSessionHistoryIntoLog
 * ================================================================ */

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
      if (typeof saveMsgDraft === 'function') saveMsgDraft();
      if (k !== treePid(projectId)) {
        projectId = k; treeProjectActiveId = k; window.dispatchEvent(new CustomEvent('project-changed', {detail: {projectId: k}}));
        saveProjectIdForAgent(agentId, projectId);
      }
      sessionId = s.session_id;
      saveSessionIdForAgent(agentId, projectId, sessionId);
      window.dispatchEvent(new CustomEvent('session-changed', {detail: {sessionId: sessionId, projectId: projectId}}));
      updateComposerButtons();
      if (typeof restoreMsgDraft === 'function') restoreMsgDraft(sessionId);
      log.innerHTML = '';
      try { reconnectWsForSession(); } catch (_) {}
      loadSessionHistoryIntoLog(true);
      syncTreeProjectActiveHighlight();
      syncTreeSessionActiveHighlight();
      // 切换会话后同步 completed 状态（清除当前会话的绿色 + 全量重算）
      if (typeof clearSessionCompleted === 'function') clearSessionCompleted(s.session_id);
      if (typeof applyAllSessionCompletedStates === 'function') applyAllSessionCompletedStates();
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
    // 异步加载完成后重新应用搜索过滤
    var inp = document.getElementById('treeSearchInput');
    if (inp && inp.value.trim()) _treeSearchFilter(inp.value);
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
  if (typeof saveMsgDraft === 'function') saveMsgDraft();
  window.dispatchEvent(new CustomEvent('project-changed', {detail: {projectId: k}}));
  treeExpanded[k] = true;
  saveProjectIdForAgent(agentId, projectId);

  function finishProjectSwitch(targetSid) {
    sessionId = targetSid;
    saveSessionIdForAgent(agentId, projectId, sessionId);
    if (typeof restoreMsgDraft === 'function') restoreMsgDraft(sessionId);
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
    if (typeof loadSessionHistoryIntoLog === 'function') loadSessionHistoryIntoLog(true).catch(function() {});
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
  // 保留滚动位置：重建 DOM 期间子树会被销毁，渲染后恢复
  var savedScrollTop = treeEl.scrollTop;
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
    // 渲染完成后恢复滚动位置（避免全量重建跳到顶部）
    if (savedScrollTop > 0) treeEl.scrollTop = savedScrollTop;
    // 重建后重新应用搜索过滤（如有）
    var inp = document.getElementById('treeSearchInput');
    if (inp && inp.value.trim()) _treeSearchFilter(inp.value);
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

// ================================================================
//  Project tree search (filter by project name / session title)
// ================================================================

function _treeSearchFilter(q) {
  q = q.trim().toLowerCase();
  var treeEl = document.getElementById('projectTree');
  if (!treeEl) return;
  var projDivs = treeEl.querySelectorAll(':scope > .tree-project');
  var anyVisible = false;
  projDivs.forEach(function(projDiv) {
    var nameEl = projDiv.querySelector('.tree-project__name');
    var pName = nameEl ? (nameEl.textContent || '').toLowerCase() : '';
    var sessionRows = projDiv.querySelectorAll(':scope > .tree-sessions > .tree-session');
    var pMatch = q === '' || pName.indexOf(q) !== -1;
    var sMatch = false;
    sessionRows.forEach(function(sRow) {
      var titleEl = sRow.querySelector('.tree-session__title');
      var sTitle = titleEl ? (titleEl.textContent || '').toLowerCase() : '';
      var match = q === '' || pMatch || sTitle.indexOf(q) !== -1;
      sRow.style.display = match ? '' : 'none';
      if (match) sMatch = true;
    });
    // 项目整体隐藏：无匹配且无匹配的会话
    var hide = q !== '' && !pMatch && !sMatch;
    projDiv.style.display = hide ? 'none' : '';
    if (!hide) anyVisible = true;
    // 有搜索词时自动展开项目（如果有匹配的子会话或项目名匹配）
    if (q !== '' && !hide) {
      var k = treePid(projDiv.dataset.projectId);
      if (!treeIsExpanded(k)) {
        treeExpanded[k] = true;
        var toggle = projDiv.querySelector('.tree-project__toggle');
        if (toggle) toggle.classList.add('tree-project__toggle--expanded');
      }
      var existing = projDiv.querySelector(':scope > .tree-sessions');
      if (!existing) {
        var children = document.createElement('div');
        children.className = 'tree-sessions';
        children.dataset.projectId = k;
        projDiv.appendChild(children);
        loadSessionsIntoContainer(children, k);
      }
    }
  });
  // 空状态
  var empty = treeEl.querySelector('.project-tree__empty');
  if (q !== '' && !anyVisible) {
    if (!empty || !empty.classList.contains('tree-search__empty')) {
      var ne = document.createElement('div');
      ne.className = 'project-tree__empty tree-search__empty';
      ne.textContent = '没有找到匹配的项目或会话';
      if (empty) empty.remove();
      treeEl.appendChild(ne);
    }
  } else {
    if (empty && empty.classList.contains('tree-search__empty')) empty.remove();
  }
}

var _treeSearchTimer = null;

function bindTreeSearch() {
  var inp = document.getElementById('treeSearchInput');
  var clearBtn = document.getElementById('treeSearchClear');
  if (!inp) return;

  // 输入过滤
  inp.addEventListener('input', function() {
    if (_treeSearchTimer) clearTimeout(_treeSearchTimer);
    _treeSearchTimer = setTimeout(function() {
      _treeSearchFilter(inp.value);
      if (clearBtn) clearBtn.style.display = inp.value.trim() ? '' : 'none';
    }, 150);
  });

  // 清除按钮
  if (clearBtn) {
    clearBtn.addEventListener('click', function() {
      inp.value = '';
      _treeSearchFilter('');
      clearBtn.style.display = 'none';
      inp.focus();
    });
  }

  // Escape 清除
  inp.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      inp.value = '';
      _treeSearchFilter('');
      if (clearBtn) clearBtn.style.display = 'none';
      inp.blur();
    }
  });

  // Ctrl+K / Cmd+K 全局快捷键聚焦搜索
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      inp.focus();
      inp.select();
    }
  });
}

// 在 DOM 就绪后绑定搜索
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bindTreeSearch);
} else {
  bindTreeSearch();
}

