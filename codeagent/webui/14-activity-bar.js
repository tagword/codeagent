var _activeMode = null;

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

  if (!mode || mode === _activeMode) return;
  _activeMode = mode;

  document.querySelectorAll('.activity-btn').forEach(function(b) {
    if (b.id === 'btnLogout') return;
    b.classList.toggle('active', b.getAttribute('data-mode') === mode);
  });

  var chatSidebar = document.getElementById('chatSidebar');
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
    if (chatSidebar) chatSidebar.style.display = 'none';
    if (statsSection) statsSection.style.display = 'flex';
    if (typeof activatePage === 'function') activatePage('chat');
    if (typeof loadStats === 'function') loadStats();
  } else if (mode === 'files') {
    hideSidebarModes();
    if (chatSidebar) chatSidebar.style.display = 'none';
    if (filesSection) filesSection.style.display = 'flex';
    if (typeof activatePage === 'function') activatePage('files');
    setTimeout(function() {
      if (typeof window.webuiRefreshFileTreeIfVisible === 'function') {
        window.webuiRefreshFileTreeIfVisible();
      }
    }, 0);
  } else {
    hideSidebarModes();
    if (chatSidebar) {
      if (typeof webuiSessionsEnabled !== 'undefined' && webuiSessionsEnabled) {
        chatSidebar.style.display = 'flex';
      } else {
        chatSidebar.style.display = 'none';
      }
    }
    if (typeof activatePage === 'function') activatePage(mode);
  }

  if (mode === 'chat') {
    if (typeof refreshProjects === 'function') setTimeout(function() { refreshProjects(false); }, 100);
  }
  try { localStorage.setItem('oa_activity_mode', mode); } catch (_) {}
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
    var saved = localStorage.getItem('oa_activity_mode');
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
