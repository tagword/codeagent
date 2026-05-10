        var body = { agent_id: agentId, name: name };
        if (path) body.path = path;
        if (source) body.source = source;
        if (cloneUrl) body.clone_url = cloneUrl;
        if (template) body.template = template;
        if (remoteInfo) body.remote = remoteInfo;

        // 启动心跳 + 计时器
        var heartbeatMsgs = [
          '正在连接远程仓库...',
          '克隆进行中，请耐心等待...',
          '网络较慢，仍在努力...',
          '对方服务器响应中...',
        ];
        var heartbeatIdx = 0;
        var startTime = Date.now();
        var heartbeatTimer = null;
        if (source === 'clone') {
          heartbeatTimer = setInterval(function() {
            var elapsed = Math.round((Date.now() - startTime) / 1000);
            var timeStr = elapsed < 60 ? elapsed + '秒' : Math.floor(elapsed/60) + '分' + (elapsed%60) + '秒';
            _updateProjectProgress(heartbeatMsgs[heartbeatIdx % heartbeatMsgs.length] + ' (' + timeStr + ')');
            heartbeatIdx++;
          }, 3000);
        }

        var r = await fetch('/api/ui/projects', {
          method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        if (heartbeatTimer) clearInterval(heartbeatTimer);

        // 更新进度：正在处理
        _updateProjectProgress('📦 正在初始化项目...');
        var j = await r.json().catch(function() { return {}; });
        if (!r.ok) {
          _hideProjectProgress();
          throw new Error(j.detail || r.statusText);
        }
        // 显示后端返回的消息（如推送结果等）
        if (j.message) {
          _updateProjectProgress('✅ ' + j.message.split('\n').pop());
          setTimeout(_hideProjectProgress, 2000);
        } else {
          _hideProjectProgress();
        }
        if (j.project && j.project.id) {
          projectId = j.project.id; saveProjectIdForAgent(agentId, projectId);
          sessionId = loadSessionIdForAgent(agentId, projectId);
          if (treeProjectsCache && treeProjectsCache.aid === agentId) {
            treeProjectsCache.projects.push(j.project);
          }
          treeExpanded[treePid(j.project.id)] = true;
          appendProjectTreeNode(j.project);            resetAgentReplyDedupe(); log.innerHTML = ''; reconnectWsForSession();
            if (webuiSessionsEnabled) {
              await refreshSessionList(); updateMainHeaderForSession(sessionId);
              await loadTranscriptIntoLog(true);
            }
            try { document.dispatchEvent(new CustomEvent('project-changed')); } catch (_) {}
          }
        } catch (e) {
          if (heartbeatTimer) clearInterval(heartbeatTimer);
          _hideProjectProgress();
          systemMsg('err', '创建项目失败：' + String(e)); }
    }

    // ---- 进度提示控制 ---- //
    function _showProjectProgress(show, source, cloneUrl) {
      var overlay = document.getElementById('projectProgressOverlay');
      if (!overlay) return;
      if (show) {
        overlay.style.display = 'flex';
        var text = document.getElementById('projectProgressText');
        var detail = document.getElementById('projectProgressDetail');
        var bar = document.getElementById('projectProgressBar');
        if (text) text.textContent = '正在创建项目...';
        if (detail) {
          if (source === 'clone') {
            detail.textContent = '正在从远程仓库克隆代码，这可能需要一些时间...';
          } else if (source === 'template') {
            detail.textContent = '正在从模板生成项目骨架...';
          } else {
            detail.textContent = '正在初始化项目...';
          }
        }
        if (bar) bar.style.width = '30%';
      } else {
        overlay.style.display = 'none';
      }
    }

    function _updateProjectProgress(text, detail) {
      var el = document.getElementById('projectProgressText');
      var detailEl = document.getElementById('projectProgressDetail');
      var bar = document.getElementById('projectProgressBar');
      if (el) el.textContent = text || '处理中...';
      if (detailEl && detail) detailEl.textContent = detail;
      if (bar) {
        var w = parseInt(bar.style.width) || 30;
        bar.style.width = Math.min(w + 20, 80) + '%';
      }
    }

    function _hideProjectProgress() {
      var overlay = document.getElementById('projectProgressOverlay');
      var bar = document.getElementById('projectProgressBar');
      if (bar) bar.style.width = '100%';
      // 延迟关闭对话框，让进度条动画走完
      setTimeout(function() {
        if (overlay) overlay.style.display = 'none';
        var dialog = document.getElementById('newProjectDialog');
        if (dialog) dialog.style.display = 'none';
      }, 600);
    }
    await refreshProjects();
    const btnSessNew = document.getElementById('btnNewSession');
    if (btnSessNew && btnSessNew.dataset.bound !== '1') {
      btnSessNew.dataset.bound = '1';
      btnSessNew.addEventListener('click', async () => {
      sessionId = oaRandomUUID();
      localStorage.setItem(_sidStorageKey(agentId, projectId), sessionId);
      updateComposerButtons(); updateMainHeaderForSession(sessionId);
      await refreshSessionList(); reconnectWsForSession(); resetAgentReplyDedupe(); log.innerHTML = '';
      await loadTranscriptIntoLog(true);
      if (typeof refreshSessionsUnderProject === 'function') refreshSessionsUnderProject(projectId);
      if (typeof activatePage === 'function') activatePage('chat');
    });
    }
    await refreshSessionList();
    updateMainHeaderForSession(sessionId);
    await loadTranscriptIntoLog(true);
    // 单窗口下不再定时轮询会话子树；新建/删会话、切项目等路径会主动 refreshSessionsUnderProject / refreshSessionList。
  } catch (_) { if (sidebar) sidebar.style.display = 'none'; }
}
initWebUiSessions();
// Load LLM preset list for model selector
refreshModelSelect().catch(function() {});
