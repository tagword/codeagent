      if (btn) { btn.disabled = false; btn.textContent = command === 'push' ? '↑ 推送' : '↓ 拉取'; }
    });
  }

  /* =============================================
   * 通知 / 工具
   * ============================================= */
  function _showNotification(msg) {
    var hint = $('gitPanelHint');
    if (!hint) return;
    hint.textContent = msg.substring(0, 200);
    hint.style.color = msg.indexOf('❌') >= 0 ? 'var(--danger,#e06c75)' : 'var(--success,#98c379)';
    if (window._gitNotifTimer) clearTimeout(window._gitNotifTimer);
    window._gitNotifTimer = setTimeout(function() { hint.textContent = ''; hint.style.color = ''; }, 5000);
  }

  /* =============================================
   * 远程仓库（只读显示）
   * ============================================= */

  function _refreshRemote() {
    _gitApi('remote').then(function(r) {
      var infoBar = $('gitRemoteInfoBar');
      var emptyBar = $('gitRemoteEmptyBar');
      var display = $('gitRemoteDisplay');
      if (!infoBar || !emptyBar || !display) return;
      
      if (r.result && r.result.indexOf('未配置') < 0) {
        var lines = r.result.split('\n');
        var remotes = [];
        lines.forEach(function(l) {
          var m = l.match(/(\S+)\s+(\S+)\s+\((fetch|push)\)/);
          if (m && m[3] === 'fetch') remotes.push({ name: m[1], url: m[2] });
        });
        if (remotes.length > 0) {
          display.innerHTML = '🔗 <span title="' + escHtmlAttr(remotes[0].url) + '">' + escHtml(remotes[0].name) + ' → ' + escHtml(_shortUrl(remotes[0].url)) + '</span>';
          infoBar.style.display = 'flex';
          emptyBar.style.display = 'none';
          return;
        }
      }
      infoBar.style.display = 'none';
      emptyBar.style.display = 'flex';
    });
  }

  function _shortUrl(url) {
    if (!url) return '';
    // 简短显示 URL: github.com/user/repo
    var m = url.replace(/^git@/, '').replace(/^https?:\/\//, '').replace(/\.git$/, '');
    return m.length > 45 ? m.substring(0, 42) + '...' : m;
  }

  function _testRemote(remoteName) {
    var name = remoteName || 'origin';
    _showNotification('🔌 测试连接中...');
    _gitApi('test-remote', name).then(function(r) {
      _showNotification(r.result || r.error || '测试完成');
    }).catch(function(err) {
      _showNotification('❌ ' + err.message);
    });
  }

  function _statusIcon(c) {
    var icons = { 'M': '📝', 'A': '➕', 'D': '🗑️', 'R': '🔀', '?': '❓', '!': '⚠️', 'C': '📋' };
    return icons[c] || '📄';
  }
  function _statusClass(c) {
    var classes = { 'M': 'git-status--M', 'A': 'git-status--A', 'D': 'git-status--D', 'R': 'git-status--R', '?': 'git-status--U' };
    return classes[c] || '';
  }
  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div'); div.textContent = str; return div.innerHTML;
  }
  function escapeHtmlAttr(str) {
    return (str || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /* =============================================
   * 对外暴露
   * ============================================= */
  window._gitRefresh = _refreshAll;

  /* =============================================
   * 启动
   * ============================================= */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
})();
