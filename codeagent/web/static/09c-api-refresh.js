      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(function(r) { return r.json(); });
  }

  /* =============================================
   * 刷新
   * ============================================= */
  function _refreshAll() {
    // 检查当前项目是否有关联路径
    var pid = _projectId || (typeof projectId !== 'undefined' ? projectId : '');
    var projPath = _getProjectPath(pid);
    if (pid && !projPath) {
      var content = $('gitPanelContent');
      if (content) {
        content.innerHTML = '<div class="git-panel__notice" id="gitPanelNoPath">' +
          '<div style="padding:24px;text-align:center;color:var(--text-muted,#888);">' +
          '<div style="font-size:32px;margin-bottom:10px;">📂</div>' +
          '<div style="font-weight:600;margin-bottom:6px;color:var(--text,#1a1a2e);">未设置项目目录</div>' +
          '<div style="font-size:13px;margin-bottom:16px;line-height:1.5;">设置工作目录后，Git 和文件树才能操作项目文件</div>' +
          '<button class="btn btn--primary btn--sm" id="btnSetProjectPath">设置目录</button>' +
          '</div></div>';
        // 绑定设置目录按钮
        var setBtn = document.getElementById('btnSetProjectPath');
        if (setBtn) {
          setBtn.addEventListener('click', function() {
            // 优先用已有项目目录对话框（与侧栏 ⋮ → 工作目录 统一），fallback 到 prompt
            if (typeof showProjectDirectoryDialog === 'function') {
              showProjectDirectoryDialog(pid);
            } else {
              var p = prompt(
                '请输入工作目录路径：\n（支持 ~ 和 $HOME 等环境变量扩展，也支持 Windows %USERPROFILE%）',
                _getProjectPath(pid) || ''
              );
              if (!p || !p.trim()) return;
              fetch('/api/ui/projects/path', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'same-origin',
                body: JSON.stringify({agent_id: agentId, project_id: pid, path: p.trim()})
              }).then(function(r) { return r.json(); }).then(function(resp) {
                if (resp.detail) { alert('设置失败：' + resp.detail); return; }
                var resolvedPath = resp.project ? resp.project.path : p.trim();
                if (treeProjectsCache && treeProjectsCache.aid === agentId) {
                  treeProjectsCache.projects.forEach(function(x) {
                    if (x.id === pid) x.path = resolvedPath;
                  });
                }
                window.dispatchEvent(new CustomEvent('project-changed', {detail: {projectId: pid}}));
                _refreshAll();
              }).catch(function() { alert('设置失败'); });
            }
          });
        }
      }
      return;
    }
    _refreshBranch();
    _refreshContent(_currentView);
    _refreshRemote();
  }

  function _getProjectPath(pid) {
    if (!pid || typeof treeProjectsCache === 'undefined' || !treeProjectsCache) return '';
    if (treeProjectsCache.aid !== agentId) return '';
    for (var i = 0; i < treeProjectsCache.projects.length; i++) {
      if (treeProjectsCache.projects[i].id === pid && treeProjectsCache.projects[i].path) {
        return treeProjectsCache.projects[i].path;
      }
    }
    return '';
  }

  function _refreshBranch() {
    _gitApi('branch').then(function(r) {
      var el = $('gitPanelBranch');
      if (!el) return;
      if (r.result) {
        var match = r.result.match(/\S+$/);
        var name = match ? match[0] : 'main';
        el.textContent = '🌿 ' + name;
      } else {
        el.textContent = '';
      }
    });
  }

  function _refreshContent(view) {
    var content = $('gitPanelContent');
    if (!content) return;
    if (view === 'status') _loadStatus(content);
    else if (view === 'log') _loadLog(content);
    else if (view === 'diff') _loadDiff(content);
  }

  /* =============================================
   * 状态视图
   * ============================================= */
  function _loadStatus(container) {
    container.innerHTML = '<div class="git-panel__loading">加载状态中...</div>';
