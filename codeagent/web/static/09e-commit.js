    _gitApi('log', '--oneline --graph --decorate -30').then(function(r) {
      if (r.result) {
        container.innerHTML = '<pre class="git-diff-pre">' + escapeHtml(r.result) + '</pre>';
      } else if (r.error) {
        container.innerHTML = '<div style="color:var(--danger,#e06c75);padding:8px 12px;">❌ ' + escapeHtml(r.error) + '</div>';
      } else {
        container.innerHTML = '<div style="color:var(--text-muted,#888);padding:12px;text-align:center;">暂无提交记录</div>';
      }
    }).catch(function(err) {
      container.innerHTML = '<div style="color:var(--danger,#e06c75);padding:8px 12px;">❌ ' + escapeHtml(err.message) + '</div>';
    });
  }

  function _loadDiff(container) {
    container.innerHTML = '<div class="git-panel__loading">加载差异中...</div>';
    _gitApi('diff').then(function(r) {
      if (r.result) {
        container.innerHTML = '<pre class="git-diff-pre">' + escapeHtml(r.result) + '</pre>';
      } else if (r.error) {
        container.innerHTML = '<div style="color:var(--danger,#e06c75);padding:8px 12px;">❌ ' + escapeHtml(r.error) + '</div>';
      } else {
        container.innerHTML = '<div style="color:var(--text-muted,#888);padding:12px;text-align:center;">无差异内容</div>';
      }
    }).catch(function(err) {
      container.innerHTML = '<div style="color:var(--danger,#e06c75);padding:8px 12px;">❌ ' + escapeHtml(err.message) + '</div>';
    });
  }

  function _showFileDiff(filepath) {
    _gitApi('diff', filepath).then(function(r) {
      var content = $('gitPanelContent');
      if (content && r.result) {
        content.innerHTML = '<pre class="git-diff-pre">' + escapeHtml(r.result) + '</pre>';
        _setActiveTab('diff');
      }
    });
  }

  function _setActiveTab(view) {
    _currentView = view;
    document.querySelectorAll('.git-slide-panel__tab').forEach(function(t) {
      t.classList.toggle('is-active', t.getAttribute('data-view') === view);
    });
  }

  /* =============================================
   * 提交
   * ============================================= */
  function _doCommit() {
    var msgEl = $('gitPanelCommitMsg');
    if (!msgEl) return;
    var msg = msgEl.value.trim();
    if (!msg) {
      msgEl.focus();
      msgEl.style.borderColor = 'var(--danger,#e06c75)';
      setTimeout(function() { msgEl.style.borderColor = ''; }, 2000);
      return;
    }
    var btn = $('gitPanelCommit');
    if (btn) { btn.disabled = true; btn.textContent = '提交中...'; }
    _gitApi('commit', '', msg).then(function(r) {
      if (r.result) { msgEl.value = ''; _showNotification(r.result); _refreshAll(); }
      else if (r.error) _showNotification('❌ ' + r.error);
      if (btn) { btn.disabled = false; btn.textContent = '提交'; }
    }).catch(function(err) {
      _showNotification('❌ ' + err.message);
      if (btn) { btn.disabled = false; btn.textContent = '提交'; }
    });
  }

  function _doGit(command) {
    var btnId = command === 'push' ? 'gitPanelPush' : 'gitPanelPull';
    var btn = $(btnId);
    if (btn) { btn.disabled = true; btn.textContent = command === 'push' ? '推送中...' : '拉取中...'; }
    _gitApi(command).then(function(r) {
      _showNotification(r.result || r.error || '完成');
      _refreshAll();
      if (btn) { btn.disabled = false; btn.textContent = command === 'push' ? '↑ 推送' : '↓ 拉取'; }
    }).catch(function(err) {
      _showNotification('❌ ' + err.message);
