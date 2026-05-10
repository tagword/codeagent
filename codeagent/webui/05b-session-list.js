    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const j = await r.json();
    const cur = sessionId;
    lastSessionsCache = j.sessions || [];
    ensureReadBaseline(lastSessionsCache);
    if (listEl) {
      listEl.innerHTML = '';
      const pin = pinSessionToTopOnce;
      let rows = orderSessionsWithPinFirst(lastSessionsCache, pin);
      if (!rows.some((x) => x.session_id === cur)) {
        rows = [{ session_id: cur, message_count: 0, display_title: '新对话', channel: 'Web 聊天', preview: '' }].concat(rows);
      }
      rows.forEach((row) => listEl.appendChild(buildSessListItem(row)));
      highlightSessList(cur);
    }
    pinSessionToTopOnce = '';
    updateMainHeaderForSession(cur);
  } catch (e) {
  }
}


// ---------------- Session list event binding ----------------

function bindSessListOnce() {
  const listEl = document.getElementById('sessList');
  if (!listEl || listEl.dataset.bound === '1') return;
  listEl.dataset.bound = '1';
  listEl.addEventListener('click', async (ev) => {
    const actBtn = ev.target.closest('[data-sess-act]');
    if (actBtn) {
      ev.preventDefault(); ev.stopPropagation();
      const rowEl = actBtn.closest('.sess-row');
      const sid = rowEl && rowEl.getAttribute('data-session-id');
      const act = actBtn.getAttribute('data-sess-act');
      if (!sid || !act) return;
      const titleHint = (rowEl.querySelector('.sess-item__title') && rowEl.querySelector('.sess-item__title').textContent) || sid;
      try {
        if (act === 'archive') {
          if (!confirm('确定归档「' + titleHint + '」？文件将移到 llm_sessions/archived/。')) return;
          const r = await fetch('/api/ui/session/archive', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ session_id: sid, agent_id: agentId })
          });
          const j = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(j.detail || r.statusText);
        } else if (act === 'delete') {
          if (!confirm('确定删除「' + titleHint + '」？此操作不可恢复。')) return;
          const r = await fetch('/api/ui/session/delete', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ session_id: sid, agent_id: agentId })
          });
          const j = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(j.detail || r.statusText);
        } else if (act === 'copy-id') {
          try { await navigator.clipboard.writeText(sid); systemMsg('info', '已复制会话 ID：' + sid); }
          catch (_) {
            const ta = document.createElement('textarea');
            ta.value = sid; ta.style.position = 'fixed'; ta.style.opacity = '0';
            document.body.appendChild(ta); ta.select(); document.execCommand('copy');
            document.body.removeChild(ta); systemMsg('info', '已复制会话 ID：' + sid);
          }
          return;
        }
      } catch (e) { alert(String(e)); return; }
      removeSessionReadBaseline(sid);
      if (sessionId === sid) {
        sessionId = oaRandomUUID();
        localStorage.setItem(_sidStorageKey(agentId, projectId), sessionId);
        updateComposerButtons(); log.innerHTML = ''; resetAgentReplyDedupe(); reconnectWsForSession();
      }
      await refreshSessionList();
      highlightSessList(sessionId);
      updateMainHeaderForSession(sessionId);
      await loadTranscriptIntoLog(true);
      if (typeof activatePage === 'function') activatePage('chat');
      return;
    }
    const btn = ev.target.closest('.sess-item-main');
    if (!btn) return;
    const sid = btn.getAttribute('data-session-id');
    if (!sid) return;
    sessionId = sid;
    localStorage.setItem(_sidStorageKey(agentId, projectId), sessionId);
    updateComposerButtons();
    const row = lastSessionsCache.find((r) => r.session_id === sid);
    markSessionReadByCount(sid, row ? (row.message_count || 0) : 0);
    reconnectWsForSession(); resetAgentReplyDedupe();
    highlightSessList(sid); updateMainHeaderForSession(sid);
    refreshSessionList().catch(() => {});
    loadTranscriptIntoLog(true);
    if (typeof activatePage === 'function') activatePage('chat');
  });
}

// ---------------- Web UI sessions initialization ----------------

async function initWebUiSessions() {
  // 页面刷新后先恢复正在运行中的会话状态（心跳指示）
  await restoreRunningSessions();
  const sidebar = document.getElementById('chatSidebar');
  const fs = document.getElementById('fieldsetChatSessions');
