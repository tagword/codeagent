/* ================================================================
 * 05-transcript.js
 *   - Transcript loading (loadTranscriptIntoLog)
 *   - Older transcript paging (loadOlderTranscriptChunk)
 *   - Session list fetch / refresh (refreshSessionList)
 *   - Session list bindings (bindSessListOnce)
 *   - Web UI sessions initialization (initWebUiSessions)
 *   - Logout
 * ================================================================ */

(function () {
  const btn = document.getElementById('btnLogout');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    try { await fetch('/api/ui/auth/logout', { method: 'POST', credentials: 'same-origin' }); } catch (_) {}
    try { sessionStorage.removeItem('oa_webui_ws_token'); } catch (_) {}
    location.href = '/';
  });
})();

// ---------------- Transcript loading ----------------

function bindTranscriptPagingOnce() {
  if (transcriptPagingBound || !log) return;
  transcriptPagingBound = true;
  log.addEventListener('scroll', () => {
    if (!transcriptHasMoreOlder || transcriptLoadingOlder) return;
    if (log.scrollTop > 120) return;
    if (transcriptScrollTimer) return;
    transcriptScrollTimer = setTimeout(() => {
      transcriptScrollTimer = null;
      if (!transcriptHasMoreOlder || transcriptLoadingOlder) return;
      if (log.scrollTop > 120) return;
      loadOlderTranscriptChunk();
    }, 120);
  }, { passive: true });
}

async function parseJsonResponse(r) {
  const text = await r.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (e) {
    var hint = (text || '').replace(/\s+/g, ' ').trim().slice(0, 240);
    throw new SyntaxError('响应不是 JSON（HTTP ' + r.status + '）：' + hint);
  }
}

async function loadOlderTranscriptChunk() {
  if (!webuiSessionsEnabled || !transcriptHasMoreOlder || transcriptLoadingOlder ||
      transcriptFirstBlockIndex == null || transcriptFirstBlockIndex <= 0) return;
  transcriptLoadingOlder = true;
  const oldH = log.scrollHeight;
  const oldT = log.scrollTop;
  try {
    const r = await fetch('/api/ui/session/transcript?session_id=' + encodeURIComponent(sessionId) +
      '&agent_id=' + encodeURIComponent(agentId) + projectQuerySuffix() +
      '&before_block_index=' + encodeURIComponent(String(transcriptFirstBlockIndex)));
    const j = await parseJsonResponse(r);
    if (!r.ok) throw new Error(j.detail || r.statusText);
    const rows = j.messages || [];
    rows.slice().reverse().forEach((m) => {
      const ts = m.ts;
      const o = { at: ts, prepend: true };
      if (m.role === 'user') bubble('user', m.content || '', o);
      else {
        // 拆分渲染：工具链各自独立展示，保持与实时执行一致的样式
        var fn = (typeof bubbleAgentWithSplitToolTrace === 'function')
          ? bubbleAgentWithSplitToolTrace : bubble;
        if (fn !== bubble) {
          fn(m.content || '', m.tool_trace || [], null, o);
        } else {
          bubble('agent', m.content || '', Object.assign({ toolTrace: m.tool_trace || [] }, o));
        }
      }
    });
    if (j.first_block_index != null) transcriptFirstBlockIndex = j.first_block_index;
    transcriptHasMoreOlder = !!j.has_more_older;
    const fixTop = () => { log.scrollTop = oldT + (log.scrollHeight - oldH); };
    fixTop();
    requestAnimationFrame(() => { requestAnimationFrame(fixTop); });
  } catch (e) { systemMsg('err', '加载更早记录失败：' + String(e)); }
  finally { transcriptLoadingOlder = false; }
}

async function loadTranscriptIntoLog(skipTreeRefresh) {
  try {
    const r = await fetch('/api/ui/session/transcript?session_id=' + encodeURIComponent(sessionId) +
      '&agent_id=' + encodeURIComponent(agentId) + projectQuerySuffix());
    const j = await parseJsonResponse(r);
    if (!r.ok) throw new Error(j.detail || r.statusText);
    log.innerHTML = '';
    resetAgentReplyDedupe();
    transcriptFirstBlockIndex = j.first_block_index != null ? j.first_block_index : null;
    transcriptHasMoreOlder = !!j.has_more_older;
    bindTranscriptPagingOnce();
    if (j.truncated_start || j.has_more_older) {
      systemMsg('info', '历史较长：默认只载入最近若干轮对话；上滑到顶部可继续加载更早内容。', { skipScroll: true });
    }
    const rows = j.messages || [];
    rows.forEach((m) => {
      const ts = m.ts;
      const skip = { skipScroll: true, at: ts };
      if (m.role === 'user') bubble('user', m.content || '', skip);
      else {
        // 拆分渲染：工具链各自独立展示
        var fn2 = (typeof bubbleAgentWithSplitToolTrace === 'function')
          ? bubbleAgentWithSplitToolTrace : bubble;
        if (fn2 !== bubble) {
          fn2(m.content || '', m.tool_trace || [], null, skip);
        } else {
          bubble('agent', m.content || '', Object.assign({ toolTrace: m.tool_trace || [] }, skip));
        }
      }
    });
    requestAnimationFrame(() => { requestAnimationFrame(() => scrollLogForce()); });
    await refreshSessionList();
    if (!skipTreeRefresh && typeof refreshSessionsUnderProject === 'function') {
      refreshSessionsUnderProject(projectId);
    }
    const row = lastSessionsCache.find((r) => r.session_id === sessionId);
    markSessionReadByCount(sessionId, row ? (row.message_count || 0) : 0);
  } catch (e) {
    transcriptFirstBlockIndex = null;
    transcriptHasMoreOlder = false;
    systemMsg('err', '载入会话记录失败：' + String(e));
  }
}

// ---------------- Session list fetch / sync ----------------

async function refreshSessionList() {
  const listEl = document.getElementById('sessList');
  try {
    const r = await fetch('/api/ui/sessions?limit=80&agent_id=' + encodeURIComponent(agentId) + projectQuerySuffix());
