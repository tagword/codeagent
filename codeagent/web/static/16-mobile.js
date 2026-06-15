;(function initMobileUi() {
  var MQ = window.matchMedia('(max-width: 768px)');

  function isMobile() {
    return MQ.matches;
  }

  function closeSidebar() {
    document.body.classList.remove('sidebar-open');
    var btn = document.getElementById('btnToggleSidebar');
    if (btn) btn.classList.remove('is-active');
    var backdrop = document.getElementById('sidebarBackdrop');
    if (backdrop) backdrop.setAttribute('aria-hidden', 'true');
  }

  function openSidebar() {
    if (!isMobile()) return;
    var mode = document.body.getAttribute('data-activity-mode');
    if (mode && mode !== 'chat') return;
    document.body.classList.add('sidebar-open');
    var btn = document.getElementById('btnToggleSidebar');
    if (btn) btn.classList.add('is-active');
    var backdrop = document.getElementById('sidebarBackdrop');
    if (backdrop) backdrop.setAttribute('aria-hidden', 'false');
  }

  function toggleSidebar() {
    if (document.body.classList.contains('sidebar-open')) closeSidebar();
    else openSidebar();
  }

  function syncActivityModeAttr(mode) {
    if (mode) document.body.setAttribute('data-activity-mode', mode);
    if (isMobile()) closeSidebar();
  }

  // Expose for activity-bar.js
  window.webuiMobileCloseSidebar = closeSidebar;
  window.webuiMobileSyncMode = syncActivityModeAttr;

  var sidebarBtn = document.getElementById('btnToggleSidebar');
  if (sidebarBtn) {
    sidebarBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      toggleSidebar();
    });
  }

  var backdrop = document.getElementById('sidebarBackdrop');
  if (backdrop) {
    backdrop.addEventListener('click', closeSidebar);
  }

  // Close drawer after picking a session
  window.addEventListener('session-changed', function() {
    if (isMobile()) closeSidebar();
  });

  // Close drawer when switching project
  window.addEventListener('project-changed', function() {
    if (isMobile()) closeSidebar();
  });

  // Resize Monaco editor on orientation change
  MQ.addEventListener('change', function() {
    closeSidebar();
    window.dispatchEvent(new Event('resize'));
  });

  // iOS keyboard: keep compose visible
  if (window.visualViewport) {
    var composeEl = null;
    var pageEl = null;
    var activityBarEl = null;
    function onViewportResize() {
      if (!isMobile()) {
        document.documentElement.style.removeProperty('--vv-offset');
        return;
      }
      var vv = window.visualViewport;
      var offset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      document.documentElement.style.setProperty('--vv-offset', offset + 'px');
      if (!composeEl) composeEl = document.querySelector('.compose');
      if (!pageEl) pageEl = document.getElementById('page-chat');
      if (!activityBarEl) activityBarEl = document.getElementById('activityBar');
      var keyboardOpen = offset > 0;
      if (composeEl && document.activeElement && document.activeElement.id === 'msg') {
        composeEl.style.transform = keyboardOpen ? 'translateY(-' + offset + 'px)' : '';
      } else if (composeEl) {
        composeEl.style.transform = '';
      }
      // 键盘弹出时：iOS 上 fixed 和 absolute 坐标系统不一致，
      // activity-bar（fixed, z-index:120）会拦截 compose dock 的触摸事件。
      // 临时降低 activity-bar 层级到 page（z-index:1）之下。
      if (activityBarEl) {
        activityBarEl.style.zIndex = keyboardOpen ? '0' : '';
      }
    }
    window.visualViewport.addEventListener('resize', onViewportResize);
    window.visualViewport.addEventListener('scroll', onViewportResize);
    var msgInput = document.getElementById('msg');
    if (msgInput) {
      msgInput.addEventListener('blur', function() {
        if (composeEl) composeEl.style.transform = '';
        if (activityBarEl) activityBarEl.style.zIndex = '';
        document.documentElement.style.removeProperty('--vv-offset');
      });
    }
  }

  // 手机视图 + 键盘弹出时：compose dock 按钮（思考/加号/发送等）在 touchstart 阶段
  // 立即 blur 输入框 + 主动触发对应操作，避免键盘收起 → viewport resize → 按钮位移 → 事件丢失
  function initComposeDockTouchFix() {
    if (!isMobile()) return;
    var dock = document.querySelector('.compose__dock');
    if (!dock) return;
    dock.addEventListener('touchstart', function(e) {
      var targetBtn = e.target.closest('.compose__tool-btn, .compose__chip, .btn--send, .compose__attach-option');
      if (!targetBtn) return;
      if (!(document.activeElement && document.activeElement.id === 'msg')) return;
      // 键盘弹出时：先 blur 让键盘收起
      // blur 是同步操作，此时 compose 的 transform 还没被 visualViewport.resize 重置，
      // 按钮坐标没变。同步触发 click 能命中正确位置。
      document.activeElement.blur();
      e.preventDefault();
      // 同步触发 click（blur 在同一 task 中，resize 事件尚未触发）
      targetBtn.click();
    }, { passive: false });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initComposeDockTouchFix);
  } else {
    initComposeDockTouchFix();
  }

  // Initial mode attribute + page visibility (after activity bar init in 14-*.js)
  try {
    var saved = tryGetLS(STORAGE_KEYS.SESS_ACTIVITY_MODE) || 'chat';
    document.body.setAttribute('data-activity-mode', saved);
    if (typeof switchToPage === 'function') switchToPage(saved);
  } catch (_) {
    document.body.setAttribute('data-activity-mode', 'chat');
    if (typeof switchToPage === 'function') switchToPage('chat');
  }

  // ======== 面板关闭按钮（所有尺寸通用）：点击 ✕ 关闭 Plan/Todo/Git 面板 ========
  document.addEventListener('click', function(e) {
    var closeBtn = e.target.closest('.panel-close-btn');
    if (!closeBtn) return;
    var panelId = closeBtn.getAttribute('data-panel');
    if (!panelId) return;
    var panel = document.getElementById(panelId);
    if (!panel) return;
    // 隐藏面板
    panel.style.display = 'none';
    // 清除对应 toggle 按钮的 is-active
    var btnMap = {
      todoPanel: 'btnToggleTodos',
      planPanel: 'btnTogglePlans',
      gitPanel: 'btnToggleGit'
    };
    var btnId = btnMap[panelId];
    if (btnId) {
      var btn = document.getElementById(btnId);
      if (btn) btn.classList.remove('is-active');
    }
    // 清除 localStorage 标志
    var lsMap = {
      todoPanel: 'oa_todo_panel_open',
      planPanel: 'oa_plan_panel_open',
      gitPanel: 'oa_git_panel_open'
    };
    var lsKey = lsMap[panelId];
    if (lsKey) {
      try { localStorage.setItem(lsKey, '0'); } catch (_) {}
    }
  });
})();
