/* ================================================================
 * 05a-session-history.js
 *   - Session history loading (loadSessionHistoryIntoLog)
 *   - Older history paging (loadOlderSessionHistoryChunk)
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
    tryRemoveSS(STORAGE_KEYS.WS_TOKEN);
    location.href = '/';
  });
})();

// ---------------- Session history loading ----------------

function bindHistoryPagingOnce() {
  if (historyPagingBound || !log) return;
  historyPagingBound = true;
  log.addEventListener('scroll', () => {
    if (!historyHasMoreOlder || historyLoadingOlder) return;
    if (log.scrollTop > 120) return;
    if (historyScrollTimer) return;
    historyScrollTimer = setTimeout(() => {
      historyScrollTimer = null;
      if (!historyHasMoreOlder || historyLoadingOlder) return;
      if (log.scrollTop > 120) return;
      loadOlderSessionHistoryChunk();
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

async function loadOlderSessionHistoryChunk() {
  if (!webuiSessionsEnabled || !historyHasMoreOlder || historyLoadingOlder ||
      historyFirstBlockIndex == null || historyFirstBlockIndex <= 0) return;
  historyLoadingOlder = true;
  const oldH = log.scrollHeight;
  const oldT = log.scrollTop;
  try {
    const r = await fetch('/api/ui/session/history?session_id=' + encodeURIComponent(sessionId) +
      '&agent_id=' + encodeURIComponent(agentId) + projectQuerySuffix() +
      '&before_block_index=' + encodeURIComponent(String(historyFirstBlockIndex)));
    const j = await parseJsonResponse(r);
    if (!r.ok) throw new Error(j.detail || r.statusText);
    const rows = j.messages || [];
    rows.slice().reverse().forEach((m) => {
      const ts = m.ts;
      const idx = m.idx;
      const o = { at: ts, prepend: true, idx: idx };
      if (m.role === 'user') bubble('user', m.content || m.text || '', Object.assign(o, { attachments: m.attachments || [] }));
      else {
        // 拆分渲染：工具链各自独立展示，保持与实时执行一致的样式
        var fn = (typeof bubbleAgentWithSplitToolTrace === 'function')
          ? bubbleAgentWithSplitToolTrace : bubble;
        if (fn !== bubble) {
          fn(m.content || '', m.tool_trace || [], o);
        } else {
          bubble('agent', m.content || '', Object.assign({ toolTrace: m.tool_trace || [] }, o));
        }
      }
    });
    if (j.first_block_index != null) historyFirstBlockIndex = j.first_block_index;
    historyHasMoreOlder = !!j.has_more_older;
    const fixTop = () => { log.scrollTop = oldT + (log.scrollHeight - oldH); };
    fixTop();
    requestAnimationFrame(() => { requestAnimationFrame(fixTop); });
  } catch (e) { systemMsg('err', '加载更早记录失败：' + String(e)); }
  finally { historyLoadingOlder = false; }
}

async function loadSessionHistoryIntoLog(skipTreeRefresh) {
  try {
    // 立即用持久化的 context_usage 恢复指示器，避免在历史加载完成前变成 1% 误显示
    try {
      const cuRow = (lastSessionsCache || []).find((r) => r.session_id === sessionId);
      const cu = cuRow && cuRow.context_usage;
      if (cu && typeof updateTokenUsage === 'function') {
        if (Number(cu.prompt_tokens) > 0) {
          updateTokenUsage({
            prompt_tokens: cu.prompt_tokens,
            compact_min_tokens: cu.compact_min_tokens,
            context_limit: cu.context_limit,
          });
        } else if (Number(cu.estimated_tokens) > 0) {
          updateTokenUsage({
            estimated_tokens: cu.estimated_tokens,
            compact_min_tokens: cu.compact_min_tokens,
            context_limit: cu.context_limit,
          });
        }
      }
    } catch (_) {}
    const r = await fetch('/api/ui/session/history?session_id=' + encodeURIComponent(sessionId) +
      '&agent_id=' + encodeURIComponent(agentId) + projectQuerySuffix());
    const j = await parseJsonResponse(r);
    if (!r.ok) throw new Error(j.detail || r.statusText);
    log.innerHTML = '';
    resetAgentReplyDedupe();
    historyFirstBlockIndex = j.first_block_index != null ? j.first_block_index : null;
    historyHasMoreOlder = !!j.has_more_older;
    bindHistoryPagingOnce();
    if (j.truncated_start || j.has_more_older) {
      systemMsg('info', '历史较长：默认只载入最近若干轮对话；上滑到顶部可继续加载更早内容。', { skipScroll: true });
    }
    const rows = j.messages || [];
    rows.forEach((m) => {
      const ts = m.ts;
      const idx = m.idx;
      const skip = { skipScroll: true, at: ts, idx: idx };
      if (m.role === 'user') bubble('user', m.content || m.text || '', Object.assign(skip, { attachments: m.attachments || [] }));
      else {
        // 拆分渲染：工具链各自独立展示
        var fn2 = (typeof bubbleAgentWithSplitToolTrace === 'function')
          ? bubbleAgentWithSplitToolTrace : bubble;
        if (fn2 !== bubble) {
          fn2(m.content || '', m.tool_trace || [], skip);
        } else {
          bubble('agent', m.content || '', Object.assign({ toolTrace: m.tool_trace || [] }, skip));
        }
      }
    });
    requestAnimationFrame(() => { requestAnimationFrame(() => scrollLogForce()); });
    // 历史加载完成后用持久化的 context_usage 校正指示器
    try {
      const cu = j && j.context_usage;
      if (cu && typeof updateTokenUsage === 'function') {
        if (Number(cu.prompt_tokens) > 0) {
          updateTokenUsage({
            prompt_tokens: cu.prompt_tokens,
            compact_min_tokens: cu.compact_min_tokens,
            context_limit: cu.context_limit,
          });
        } else if (Number(cu.estimated_tokens) > 0) {
          updateTokenUsage({
            estimated_tokens: cu.estimated_tokens,
            compact_min_tokens: cu.compact_min_tokens,
            context_limit: cu.context_limit,
          });
        } else if (typeof recalcTokenUsageFromDom === 'function') {
          setTimeout(recalcTokenUsageFromDom, 100);
        }
      } else if (typeof recalcTokenUsageFromDom === 'function') {
        setTimeout(recalcTokenUsageFromDom, 100);
      }
    } catch (_) {}
    // 加载侧边栏费用汇总
    if (j.accumulated_usage && typeof updateSidebarCost === 'function') {
      updateSidebarCost(j.accumulated_usage);
    }
    await refreshSessionList();
    if (!skipTreeRefresh && typeof refreshSessionsUnderProject === 'function') {
      refreshSessionsUnderProject(projectId);
    }
    const row = lastSessionsCache.find((r) => r.session_id === sessionId);
    markSessionReadByCount(sessionId, row ? (row.message_count || 0) : 0);
  } catch (e) {
    historyFirstBlockIndex = null;
    historyHasMoreOlder = false;
    systemMsg('err', '载入会话记录失败：' + String(e));
  }
}

// ---------------- Session list fetch / sync ----------------

async function refreshSessionList() {
  const listEl = document.getElementById('sessList');
  try {
    const r = await fetch('/api/ui/sessions?limit=80&agent_id=' + encodeURIComponent(agentId) + projectQuerySuffix());
