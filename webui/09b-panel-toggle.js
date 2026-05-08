  function gitIsVisible() {
    var panel = $('gitPanel');
    return panel && panel.style.display === 'flex';
  }

  function toggleGitPanel() {
    var opening = !gitIsVisible();
    var panel = $('gitPanel');
    var btn = $('btnToggleGit');
    if (!panel) return;

    panel.style.display = opening ? 'flex' : 'none';
    if (btn) btn.classList.toggle('is-active', opening);
    try { localStorage.setItem('oa_git_panel_open', opening ? '1' : '0'); } catch (_) {}

    // 互斥：打开 Git 时关闭 Plan 和 Todo
    if (opening) {
      _closeOtherPanels();
      _refreshAll();
    }
  }

  function _closeOtherPanels() {
    var planP = $('planPanel');
    var planB = $('btnTogglePlans');
    if (planP && planP.style.display !== 'none') {
      planP.style.display = 'none';
      if (planB) planB.classList.remove('is-active');
      try { localStorage.setItem('oa_plan_panel_open', '0'); } catch (_) {}
    }
    var todoP = $('todoPanel');
    var todoB = $('btnToggleTodos');
    if (todoP && todoP.style.display !== 'none') {
      todoP.style.display = 'none';
      if (todoB) todoB.classList.remove('is-active');
      try { localStorage.setItem('oa_todo_panel_open', '0'); } catch (_) {}
    }
  }

  // 外部监听：如果 Plan/Todo 打开了，自动关闭 Git
  document.addEventListener('click', function(e) {
    var planBtn = e.target.closest('#btnTogglePlans');
    var todoBtn = e.target.closest('#btnToggleTodos');
    if (planBtn || todoBtn) {
      var panel = $('gitPanel');
      var btn = $('btnToggleGit');
      if (panel && panel.style.display === 'flex') {
        panel.style.display = 'none';
        if (btn) btn.classList.remove('is-active');
        try { localStorage.setItem('oa_git_panel_open', '0'); } catch (_) {}
      }
    }
  }, true);

  // 恢复上次打开状态
  try {
    if (localStorage.getItem('oa_git_panel_open') === '1') {
      var planP = $('planPanel');
      var todoP = $('todoPanel');
      if ((planP && planP.style.display === 'flex') || (todoP && todoP.style.display === 'flex')) {
        // 对面已开，不覆盖
      } else {
        var panel = $('gitPanel');
        var btn = $('btnToggleGit');
        if (panel) panel.style.display = 'flex';
        if (btn) btn.classList.add('is-active');
        setTimeout(_refreshAll, 150);
      }
    }
  } catch (_) {}

  /* =============================================
   * Git API
   * ============================================= */
  function _gitApi(command, args, message) {
    _projectId = (typeof projectId !== 'undefined') ? projectId : _projectId;
    var body = { command: command, args: args || '', message: message || '' };
    if (_projectId) body.project_id = _projectId;
    return fetch('/api/ui/git', {
      method: 'POST',
