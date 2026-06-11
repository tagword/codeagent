var _activeMode = null;
var _FULL_WIDTH_MODES = ['config', 'tasks', 'agent', 'team', 'hub'];

function _applySidebarForMode(mode) {
  var chatSidebar = document.getElementById('chatSidebar');
  var outerSidebar = document.querySelector('.app > aside.sidebar');
  if (outerSidebar) outerSidebar.style.removeProperty('display');

  if (mode === 'stats' || mode === 'files') {
    if (chatSidebar) chatSidebar.style.display = 'none';
    return;
  }
  if (_FULL_WIDTH_MODES.indexOf(mode) >= 0) {
    if (chatSidebar) chatSidebar.style.display = 'none';
    return;
  }
  if (chatSidebar) {
    if (typeof webuiSessionsEnabled !== 'undefined' && webuiSessionsEnabled) {
      chatSidebar.style.display = 'flex';
    } else {
      chatSidebar.style.display = 'none';
    }
  }
}

function _syncWorkspacePages(pageId) {
  if (typeof switchToPage === 'function') switchToPage(pageId);
}

function _syncFileBtnState() {
  var fileBtn = document.getElementById('btnToggleFiles');
  if (!fileBtn) return;
  if (_activeMode === 'files') {
    fileBtn.classList.add('is-active');
  } else {
    fileBtn.classList.remove('is-active');
  }
}

function switchActivityMode(mode) {
  // git 模式不走页面切换，由 09-git.js 的点击拦截处理
  if (mode === 'git') return;

  if (!mode) return;
  if (mode === _activeMode) {
    try { document.body.setAttribute('data-activity-mode', mode); } catch (_) {}
    _syncWorkspacePages(mode);
    return;
  }
  _activeMode = mode;
  try { document.body.setAttribute('data-activity-mode', mode); } catch (_) {}

  document.querySelectorAll('.activity-btn').forEach(function(b) {
    if (b.id === 'btnLogout') return;
    b.classList.toggle('active', b.getAttribute('data-mode') === mode);
  });

  var statsSection = document.getElementById('sidebarStats');
  var filesSection = document.getElementById('sidebarFiles');
  var gitSidebarSection = document.getElementById('sidebarGit');

  function hideSidebarModes() {
    if (statsSection) statsSection.style.display = 'none';
    if (filesSection) filesSection.style.display = 'none';
    if (gitSidebarSection) gitSidebarSection.style.display = 'none';
  }

  if (mode === 'stats') {
    hideSidebarModes();
    if (statsSection) statsSection.style.display = 'flex';
    _applySidebarForMode(mode);
    if (typeof switchToPage === 'function') switchToPage('chat');
    else _syncWorkspacePages('chat');
    if (typeof activatePage === 'function') activatePage('chat');
    if (typeof loadStats === 'function') loadStats();
  } else if (mode === 'files') {
    hideSidebarModes();
    if (filesSection) filesSection.style.display = 'flex';
    _applySidebarForMode(mode);
    if (typeof switchToPage === 'function') switchToPage('files');
    else _syncWorkspacePages('files');
    if (typeof activatePage === 'function') activatePage('files');
    setTimeout(function() {
      if (typeof window.webuiRefreshFileTreeIfVisible === 'function') {
        window.webuiRefreshFileTreeIfVisible();
      }
    }, 0);
  } else {
    hideSidebarModes();
    _applySidebarForMode(mode);
    var pageId = mode;
    _syncWorkspacePages(pageId);
    if (typeof switchToPage === 'function') switchToPage(pageId);
    if (typeof activatePage === 'function') activatePage(pageId);
  }

  if (mode === 'chat') {
    if (typeof refreshProjects === 'function') setTimeout(function() { refreshProjects(false); }, 100);
  }
  trySetLS(STORAGE_KEYS.SESS_ACTIVITY_MODE, mode);
  if (typeof window.webuiMobileSyncMode === 'function') window.webuiMobileSyncMode(mode);
  syncTopbarChatShortcutUi();
  _syncFileBtnState();
}

function syncTopbarChatShortcutUi() {
  var grp = document.querySelector('.topbar__title-group');
  if (!grp) return;
  if (_activeMode && _activeMode !== 'chat') {
    grp.style.cursor = 'pointer';
    grp.title = '返回聊天';
  } else {
    grp.style.cursor = '';
    grp.title = '';
  }
}

function restoreActivityMode() {
  try {
    var saved = tryGetLS(STORAGE_KEYS.SESS_ACTIVITY_MODE);
    if (saved && ['chat', 'tasks', 'agent', 'config', 'stats', 'files'].indexOf(saved) >= 0) {
      _activeMode = null;
      switchActivityMode(saved);
      return;
    }
  } catch (_) {}
  _activeMode = null;
  switchActivityMode('chat');
}

;(function initActivityBar() {
  document.querySelectorAll('.activity-btn').forEach(function(btn) {
    // 手机视图下用 touchstart 捕获，避免键盘收起时 viewport 变化吞掉 click
    btn.addEventListener('touchstart', function(e) {
      var isMobile = window.matchMedia('(max-width: 768px)').matches;
      if (!isMobile) return;
      var mode = this.getAttribute('data-mode');
      if (!mode) return;
      // 键盘弹出时：在 touchstart 阶段 blur 并切换，不等 click
      if (document.activeElement && document.activeElement.id === 'msg') {
        document.activeElement.blur();
        switchActivityMode(mode);
        e.preventDefault();
      }
    }, { passive: false });
    btn.addEventListener('click', function() {
      var mode = this.getAttribute('data-mode');
      if (mode) switchActivityMode(mode);
    });
  });
  var titleGrp = document.querySelector('.topbar__title-group');
  if (titleGrp && titleGrp.dataset.chatNavBound !== '1') {
    titleGrp.dataset.chatNavBound = '1';
    titleGrp.addEventListener('click', function() {
      if (_activeMode != null && _activeMode !== 'chat') {
        switchActivityMode('chat');
      }
    });
  }
  restoreActivityMode();

  // ======== 文件按钮（topbar 切换） ========
  var fileBtn = document.getElementById('btnToggleFiles');
  if (fileBtn) {
    _syncFileBtnState();

    fileBtn.addEventListener('click', function() {
      if (_activeMode === 'files') {
        switchActivityMode('chat');
      } else {
        // 关闭顶层面板：Plan/Todo/Git
        ['planPanel','todoPanel','gitPanel'].forEach(function(id) {
          var p = document.getElementById(id);
          if (p && p.style.display !== 'none') {
            p.style.display = 'none';
            try { localStorage.setItem('oa_' + id.replace('Panel','').toLowerCase() + '_panel_open', '0'); } catch (_) {}
          }
        });
        ['btnTogglePlans','btnToggleTodos','btnToggleGit'].forEach(function(id) {
          var b = document.getElementById(id);
          if (b) b.classList.remove('is-active');
        });
        switchActivityMode('files');
      }
    });
  }
})();
