/* ================================================================
 * 01c-session-tree-menus.js
 *   项目树右键菜单 + 目录关联对话框 + 项目/会话重命名/删除：
 *     - showProjectContextMenu / showSessionContextMenu / closeContextMenu
 *     - closeProjectDirectoryDialog / showProjectDirectoryDialog
 *     - copyToClipboard / renameProject / deleteProject / deleteSession
 *
 *   依赖 01c-session-tree.js 的：
 *     treePid / findProjDiv / refreshSessionsUnderProject / syncTreeProjectActiveHighlight
 *     / syncTreeSessionActiveHighlight / refreshProjects
 *   依赖 01c-session-identity.js 的：
 *     agentId / projectId / sessionId / saveProjectIdForAgent / _sidStorageKey
 *     / oaRandomUUID
 *
 *   按字母序：'01c-session-tree-menus.js' 中字符 '-' (0x2D) < '01c-session-tree.js'
 *   字符 '.' (0x2E)，所以 menus 文件实际在 tree 文件**之后**加载；
 *   function hoisting 保证本文件函数可被 tree 内部引用。
 * ================================================================ */

function closeProjectDirectoryDialog() {
  var el = document.getElementById('projectDirDialog');
  if (el) el.remove();
}

/** 侧栏项目 ⋮ 菜单：设置/查看工作目录 */
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
  hint.textContent = '设置工作目录后，文件树和 Git 面板可直接操作项目文件';
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
  document.body.appendChild(root);

  function close() { closeProjectDirectoryDialog(); }
  btnClose.addEventListener('click', close);
  btnCancel.addEventListener('click', close);
  root.addEventListener('click', function(ev) {
    if (ev.target === root) close();
  });
  btnSave.addEventListener('click', async function() {
    var newPath = inp.value.trim();
    btnSave.disabled = true;
    try {
      var r = await fetch('/api/ui/projects/path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ agent_id: agentId, project_id: k, path: newPath }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      var resp = await r.json();
      var resolvedPath = resp.project ? resp.project.path : newPath;
      if (treeProjectsCache && treeProjectsCache.aid === agentId) {
        for (var i = 0; i < treeProjectsCache.projects.length; i++) {
          if (treePid(treeProjectsCache.projects[i].id) === k) {
            treeProjectsCache.projects[i].path = resolvedPath;
            break;
          }
        }
      }
      close();
      window.dispatchEvent(new CustomEvent('project-changed', {detail: {projectId: k}}));
    } catch (e) {
      alert('保存失败：' + String(e.message || e));
      btnSave.disabled = false;
    }
  });
  if (typeof btnBrowse === 'object' && btnBrowse) {
    btnBrowse.addEventListener('click', function() {
      btnBrowse.textContent = '⏳ 选择中…';
      btnBrowse.disabled = true;
      fetch('/api/ui/pick-directory', { method: 'POST', credentials: 'same-origin' })
        .then(function(r) { return r.json(); })
        .then(function(j) {
          if (j.path) inp.value = j.path;
          else if (j.hint) console.warn('pick-directory:', j.hint);
          else if (j.detail) console.warn('pick-directory:', j.detail);
        })
        .catch(function(e) { console.error('pick-directory error:', e); })
        .finally(function() {
          btnBrowse.textContent = '📁 浏览';
          btnBrowse.disabled = false;
        });
    });
  }
}

function showProjectContextMenu(e, pid, name) {
  closeContextMenu();
  var menu = document.createElement('div');
  menu.className = 'tree-context-menu';
  menu.setAttribute('data-menu', 'project');
  var items = [
    { label: '工作目录', act: 'dir' },
    { label: '重命名', act: 'rename' },
    { label: '删除项目', act: 'delete', danger: true },
  ];
  items.forEach(function(it) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tree-context-menu__item' + (it.danger ? ' tree-context-menu__item--danger' : '');
    btn.textContent = it.label;
    btn.addEventListener('click', function(ev) {
      ev.stopPropagation();
      closeContextMenu();
      if (it.act === 'dir') showProjectDirectoryDialog(pid);
      else if (it.act === 'rename') renameProject(pid, name);
      else if (it.act === 'delete') deleteProject(pid);
    });
    menu.appendChild(btn);
  });
  var x = (e && e.clientX) || 80;
  var y = (e && e.clientY) || 80;
  menu.style.left = Math.min(x, window.innerWidth - 200) + 'px';
  menu.style.top = Math.min(y, window.innerHeight - 200) + 'px';
  document.body.appendChild(menu);

  var overlay = document.createElement('div');
  overlay.className = 'tree-overlay';
  overlay.addEventListener('click', closeContextMenu);
  document.body.appendChild(overlay);
  menu.dataset.overlay = '1';
}

function showSessionContextMenu(e, sid, pid) {
  closeContextMenu();
  var menu = document.createElement('div');
  menu.className = 'tree-context-menu';
  menu.setAttribute('data-menu', 'session');
  var items = [
    { label: '复制会话 ID', act: 'copy-id' },
    { label: '归档', act: 'archive' },
    { label: '删除', act: 'delete', danger: true },
  ];
  items.forEach(function(it) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tree-context-menu__item' + (it.danger ? ' tree-context-menu__item--danger' : '');
    btn.textContent = it.label;
    btn.addEventListener('click', function(ev) {
      ev.stopPropagation();
      closeContextMenu();
      if (it.act === 'copy-id') {
        try { navigator.clipboard.writeText(sid); }
        catch (_) {
          var ta = document.createElement('textarea');
          ta.value = sid; ta.style.position = 'fixed'; ta.style.opacity = '0';
          document.body.appendChild(ta); ta.select(); document.execCommand('copy');
          document.body.removeChild(ta);
        }
        if (typeof systemMsg === 'function') systemMsg('info', '已复制会话 ID：' + sid);
      } else if (it.act === 'archive') {
        if (!confirm('确定归档此会话？文件将移到 sessions/archived/。')) return;
        fetch('/api/ui/session/archive', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
          body: JSON.stringify({ session_id: sid, agent_id: agentId, project_id: pid || '' })
        }).then(function(r) {
          if (!r.ok) alert('归档失败');
          else if (typeof refreshSessionsUnderProject === 'function') refreshSessionsUnderProject(pid);
        }).catch(function() { alert('归档失败'); });
      } else if (it.act === 'delete') {
        deleteSession(sid, pid);
      }
    });
    menu.appendChild(btn);
  });
  var x = (e && e.clientX) || 80;
  var y = (e && e.clientY) || 80;
  menu.style.left = Math.min(x, window.innerWidth - 200) + 'px';
  menu.style.top = Math.min(y, window.innerHeight - 200) + 'px';
  document.body.appendChild(menu);

  var overlay = document.createElement('div');
  overlay.className = 'tree-overlay';
  overlay.addEventListener('click', closeContextMenu);
  document.body.appendChild(overlay);
  menu.dataset.overlay = '1';
}

function closeContextMenu() {
  document.querySelectorAll('.tree-context-menu').forEach(function(m) { m.remove(); });
  document.querySelectorAll('.tree-overlay').forEach(function(o) { o.remove(); });
}

function copyToClipboard(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text);
    return;
  }
  var ta = document.createElement('textarea');
  ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.appendChild(ta); ta.select(); document.execCommand('copy');
  document.body.removeChild(ta);
}

function renameProject(pid, currentName) {
  var newName = prompt('重命名项目：', currentName || '');
  if (newName == null) return;
  newName = String(newName).trim();
  if (!newName || newName === currentName) return;
  fetch('/api/ui/projects/rename', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ agent_id: agentId, project_id: pid, name: newName })
  }).then(function(r) {
    if (r.ok) {
      if (treeProjectsCache && treeProjectsCache.aid === agentId) {
        for (var i = 0; i < treeProjectsCache.projects.length; i++) {
          if (treePid(treeProjectsCache.projects[i].id) === treePid(pid)) {
            treeProjectsCache.projects[i].name = newName;
            break;
          }
        }
      }
      var projDiv = findProjDiv(pid);
      if (projDiv) {
        var name = projDiv.querySelector('.tree-project__name');
        if (name) name.textContent = newName;
      }
    } else alert('重命名失败');
  }).catch(function() { alert('重命名失败'); });
}

function deleteProject(pid) {
  if (!confirm('确定删除项目及其下所有会话？此操作不可恢复。')) return;
  fetch('/api/ui/projects/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
    body: JSON.stringify({ session_id: sid, agent_id: agentId, project_id: pid || '' })
  }).then(function(r) {
    if (r.ok) {
      if (sessionId === sid) {
        if (typeof saveMsgDraft === 'function') saveMsgDraft();
        sessionId = oaRandomUUID();
        localStorage.setItem(_sidStorageKey(agentId, pid || projectId), sessionId);
        if (typeof msg !== 'undefined' && msg) msg.value = '';
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
