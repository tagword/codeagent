var _activeMode = null;
var _FULL_WIDTH_MODES = ['config', 'tasks', 'agent'];

function _applySidebarForMode(mode) {
  var chatSidebar = document.getElementById('chatSidebar');
  var fileSidebar = document.getElementById('sidebarFiles');
  var gitSidebar = document.getElementById('sidebarGit');
  var outerSidebar = document.querySelector('.app > aside.sidebar');
  if (outerSidebar) outerSidebar.style.removeProperty('display');

  // 先清空所有 sidebar-mode 的 visible 状态
  [fileSidebar, gitSidebar].forEach(function(el) {
    if (el) el.classList.remove('is-visible');
  });

  if (_FULL_WIDTH_MODES.indexOf(mode) >= 0) {
    if (chatSidebar) chatSidebar.style.display = 'none';
    return;
  }

  if (mode === 'files') {
    if (chatSidebar) chatSidebar.style.display = 'none';
    if (fileSidebar) fileSidebar.classList.add('is-visible');
    return;
  }

  // Default: chat mode
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
  fileBtn.classList.toggle('is-active', _activeMode === 'files');
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

  _applySidebarForMode(mode);
  var pageId = mode;
  _syncWorkspacePages(pageId);
  if (typeof switchToPage === 'function') switchToPage(pageId);
  if (typeof activatePage === 'function') activatePage(pageId);

  if (mode === 'chat') {
    if (typeof refreshProjects === 'function') setTimeout(function() { refreshProjects(false); }, 100);
  }
  if (mode === 'files') {
    // Refresh file tree on next tick
    setTimeout(function() {
      if (typeof window.webuiRefreshFileTreeIfVisible === 'function') {
        window.webuiRefreshFileTreeIfVisible();
      }
    }, 0);
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
    if (saved && ['chat', 'files', 'tasks', 'agent', 'config'].indexOf(saved) >= 0) {
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
    btn.addEventListener('touchstart', function(e) {
      var isMobile = window.matchMedia('(max-width: 768px)').matches;
      if (!isMobile) return;
      var mode = this.getAttribute('data-mode');
      if (!mode) return;
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

  // ======== 文件按钮（topbar 切换）= 模式切换 ========
  var fileBtn = document.getElementById('btnToggleFiles');
  if (fileBtn) {
    fileBtn.addEventListener('click', function() {
      if (_activeMode === 'files') {
        switchActivityMode('chat');
      } else {
        switchActivityMode('files');
      }
      _syncFileBtnState();
    });
  }
})();
