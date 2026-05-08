/**
 * Git 面板 — Web UI 源代码管理（滑出面板版）
 * 依赖: 09-git.css
 *
 * 点击 topbar 的 Git 按钮 (btnToggleGit) 或 activity bar 的 Git 图标，
 * 滑出面板，与 Plan/Todo 面板互斥。
 * 暴露 window._gitRefresh() 供外部调用。
 */

(function() {
  'use strict';

  /* =============================================
   * 状态
   * ============================================= */
  var _initialized = false;
  var _projectId = '';
  var _currentView = 'status';

  /* =============================================
   * DOM 快捷引用
   * ============================================= */
  var $ = function(id) { return document.getElementById(id); };

  /* =============================================
   * 初始化
   * ============================================= */
  function _init() {
    if (_initialized) return;
    _initialized = true;

    // 1. topbar Git 按钮 — 切换面板
    var topbarBtn = $('btnToggleGit');
    if (topbarBtn) {
      topbarBtn.addEventListener('click', toggleGitPanel);
    }

    // 2. activity bar git 图标 — 同样切换面板
    document.addEventListener('click', function(e) {
      var btn = e.target.closest('[data-mode="git"]');
      if (btn) {
        // 拦截 activity bar 的 git 点击，改为切换面板
        e.preventDefault();
        e.stopPropagation();
        toggleGitPanel();
      }
    });

    // 3. 面板内按钮
    bindClick('gitPanelRefresh', _refreshAll);
    bindClick('gitPanelCommit', _doCommit);
    bindClick('gitPanelPush', function() { _doGit('push'); });
    bindClick('gitPanelPull', function() { _doGit('pull'); });

    // 4. Tab 切换
    var tabs = document.querySelectorAll('.git-slide-panel__tab');
    tabs.forEach(function(tab) {
      tab.addEventListener('click', function() {
        tabs.forEach(function(t) { t.classList.remove('is-active'); });
        this.classList.add('is-active');
        _currentView = this.getAttribute('data-view') || 'status';
        _refreshContent(_currentView);
      });
    });

    // 5. 快捷键: Ctrl+Enter 提交
    document.addEventListener('keydown', function(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        var input = $('gitPanelCommitMsg');
        if (input && document.activeElement === input) {
          e.preventDefault();
          _doCommit();
        }
      }
    });

    // 6. 监听项目切换
    window.addEventListener('project-changed', function(e) {
      _projectId = e.detail.projectId || '';
      if (gitIsVisible()) _refreshAll();
    });

    // 7. 远程仓库 — 只读显示，跳转到配置页编辑
    bindClick('gitRemoteTestBtn', function() { _testRemote(); });
    // 配置页跳转链接
    var configLinks = document.querySelectorAll('#gitRemoteConfigLink, #gitRemoteConfigLinkEmpty');
    configLinks.forEach(function(link) {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        // 切换到配置页
        if (typeof activatePage === 'function') activatePage('config');
        // 关闭 Git 面板
        var panel = $('gitPanel');
        var btn = $('btnToggleGit');
        if (panel) panel.style.display = 'none';
        if (btn) btn.classList.remove('is-active');
      });
    });
    if (typeof projectId !== 'undefined') _projectId = projectId;
  }

  /** 安全绑定点击 */
  function bindClick(id, fn) {
    var el = $(id);
    if (el) el.addEventListener('click', fn);
  }

  /* =============================================
   * 面板切换（与 Plan/Todo 互斥）
   * ============================================= */
