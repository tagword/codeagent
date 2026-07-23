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
    trySetLS(STORAGE_KEYS.GIT_PANEL_OPEN, opening ? '1' : '0');

    // 互斥：打开 Git 时关闭其他面板
    if (opening) {
      if (typeof _activeMode !== 'undefined' && _activeMode === 'files' && typeof switchActivityMode === 'function') {
        switchActivityMode('chat');
      }
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
      trySetLS(STORAGE_KEYS.PLAN_PANEL_OPEN, '0');
    }
    var todoP = $('todoPanel');
    var todoB = $('btnToggleTodos');
    if (todoP && todoP.style.display !== 'none') {
      todoP.style.display = 'none';
      if (todoB) todoB.classList.remove('is-active');
      trySetLS(STORAGE_KEYS.TODO_PANEL_OPEN, '0');
    }
    var skillP = $('skillPanel');
    var skillB = $('btnToggleSkills');
    if (skillP && skillP.style.display !== 'none') {
      skillP.style.display = 'none';
      if (skillB) skillB.classList.remove('is-active');
    }
  }

  // 外部监听：如果 Plan/Todo 打开了，自动关闭 Git
  document.addEventListener('click', function(e) {
    var planBtn = e.target.closest('#btnTogglePlans');
    var todoBtn = e.target.closest('#btnToggleTodos');
    var skillBtn = e.target.closest('#btnToggleSkills');
    if (planBtn || todoBtn || skillBtn) {
      var panel = $('gitPanel');
      var btn = $('btnToggleGit');
      if (panel && panel.style.display === 'flex') {
        panel.style.display = 'none';
        if (btn) btn.classList.remove('is-active');
        trySetLS(STORAGE_KEYS.GIT_PANEL_OPEN, '0');
      }
    }
  }, true);

  // 恢复上次打开状态
  try {
    if (tryGetLS(STORAGE_KEYS.GIT_PANEL_OPEN) === '1') {
      var planP = $('planPanel');
      var todoP = $('todoPanel');
      var skillP = $('skillPanel');
      if ((planP && planP.style.display === 'flex') || (todoP && todoP.style.display === 'flex') || (skillP && skillP.style.display === 'flex')) {
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
