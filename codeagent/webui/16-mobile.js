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
    function onViewportResize() {
      if (!isMobile()) {
        document.documentElement.style.removeProperty('--vv-offset');
        return;
      }
      var vv = window.visualViewport;
      var offset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      document.documentElement.style.setProperty('--vv-offset', offset + 'px');
      if (!composeEl) composeEl = document.querySelector('.compose');
      if (composeEl && document.activeElement && document.activeElement.id === 'msg') {
        composeEl.style.transform = offset > 0 ? 'translateY(-' + offset + 'px)' : '';
      } else if (composeEl) {
        composeEl.style.transform = '';
      }
    }
    window.visualViewport.addEventListener('resize', onViewportResize);
    window.visualViewport.addEventListener('scroll', onViewportResize);
    var msgInput = document.getElementById('msg');
    if (msgInput) {
      msgInput.addEventListener('blur', function() {
        if (composeEl) composeEl.style.transform = '';
        document.documentElement.style.removeProperty('--vv-offset');
      });
    }
  }

  // Initial mode attribute
  try {
    var saved = localStorage.getItem('oa_activity_mode') || 'chat';
    document.body.setAttribute('data-activity-mode', saved);
  } catch (_) {
    document.body.setAttribute('data-activity-mode', 'chat');
  }

  // ---- Compose compact mode on mobile ----
  function toggleComposeCompact() {
    var box = document.querySelector('.compose__box');
    if (!box) return;
    if (isMobile()) {
      box.classList.add('compose--compact');
    } else {
      box.classList.remove('compose--compact');
    }
  }
  toggleComposeCompact();
  MQ.addEventListener('change', toggleComposeCompact);
})();
