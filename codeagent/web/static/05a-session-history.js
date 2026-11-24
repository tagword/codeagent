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

// ---------------- 会话加载代次 & 「钉住底部」 ----------------
// 为什么需要代次：切换会话时旧的 history / 分页请求可能晚于新会话返回，
// 若不加判据，旧数据的渲染与 fixTop 会作用到新会话的日志上（内容串台 + 滚动错位）。
let _historyLoadSeq = 0;

// 为什么需要钉底：历史渲染完成后内容高度还会变（图片/mermaid 异步渲染、
// 字体加载、侧栏抽屉开关引起的重排）。只在渲染后写一次 scrollTop，
// 后续高度增长会把视口留在半空 —— 用户看到的就是「先到底又弹回中间」。
let _pinBottomRaf = 0;
let _pinBottomUntil = 0;

function _cancelPinBottom() {
  _pinBottomUntil = 0;
  if (_pinBottomRaf) {
    try { cancelAnimationFrame(_pinBottomRaf); } catch (_) {}
    _pinBottomRaf = 0;
  }
}

/** 在 ms 毫秒内持续把日志钉在底部（用户一有滚动/按键操作立即放弃）。 */
function pinLogBottomFor(ms) {
  if (!log) return;
  _pinBottomUntil = Date.now() + (ms || 1500);
  if (_pinBottomRaf) return;
  (function tick() {
    _pinBottomRaf = 0;
    if (!log) return;
    if (!_pinBottomUntil || Date.now() > _pinBottomUntil) return;
    const dist = log.scrollHeight - log.scrollTop - log.clientHeight;
    if (dist > 2) log.scrollTop = log.scrollHeight;
    _pinBottomRaf = requestAnimationFrame(tick);
  })();
}

// 用户主动操作 → 立刻停止钉底，别跟用户抢滚动条
['wheel', 'touchmove', 'keydown', 'pointerdown'].forEach(function (ev) {
  try { log.addEventListener(ev, _cancelPinBottom, { passive: true }); } catch (_) {}
});

// ---------------- Session history loading ----------------

function bindHistoryPagingOnce() {
  if (historyPagingBound || !log) return;
  historyPagingBound = true;
  log.addEventListener('scroll', () => {
    // 日志被切换会话清空后 scrollTop 会归零并冒出一个 scroll 事件；
    // 此时若沿用旧会话的分页状态就会去拉「更早的记录」，其 fixTop
    // 会用一个陈旧的高度差改写 scrollTop（滚动错位的另一个入口）。
    if (!log.children.length) return;
    if (!historyHasMoreOlder || historyLoadingOlder) return;
    if (log.scrollTop > 120) return;
    if (historyScrollTimer) return;
    const gen = _historyLoadSeq;
    const forSid = sessionId;
    historyScrollTimer = setTimeout(() => {
      historyScrollTimer = null;
      if (gen !== _historyLoadSeq || forSid !== sessionId) return;  // 已切会话
      if (!log.children.length) return;
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
  _cancelPinBottom();   // 上翻看旧消息时别再被钉回底部
  const gen = _historyLoadSeq;   // 绑定发起时的会话代次
  const forSid = sessionId;
  const beforeIdx = historyFirstBlockIndex;
  historyLoadingOlder = true;
  const oldH = log.scrollHeight;
  const oldT = log.scrollTop;
  try {
    const r = await fetch('/api/ui/session/history?session_id=' + encodeURIComponent(forSid) +
      '&agent_id=' + encodeURIComponent(agentId) + projectQuerySuffix() +
      '&before_block_index=' + encodeURIComponent(String(beforeIdx)));
    const j = await parseJsonResponse(r);
    if (!r.ok) throw new Error(j.detail || r.statusText);
    // 会话已切换（或又发起了新的加载）→ 丢弃这次结果，别把它插到别的会话里
    if (gen !== _historyLoadSeq || forSid !== sessionId) return;
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
  } catch (e) {
    if (gen === _historyLoadSeq && forSid === sessionId) {
      systemMsg('err', '加载更早记录失败：' + String(e));
    }
  }
  finally { if (gen === _historyLoadSeq) historyLoadingOlder = false; }
}

async function loadSessionHistoryIntoLog(skipTreeRefresh) {
  const gen = ++_historyLoadSeq;
  const forSid = sessionId;
  // 立刻作废上一会话的分页状态：否则 log.innerHTML='' 引起的 scroll 事件
  // 会带着旧会话的 block index 去给新会话「加载更早记录」，其 fixTop 会把
  // scrollTop 写成一个陈旧的值 —— 表现为先到底、再弹回中间。
  historyFirstBlockIndex = null;
  historyHasMoreOlder = false;
  historyLoadingOlder = false;
  try {
    if (typeof resetTokenUsageCache === 'function') resetTokenUsageCache();
    // 立即用持久化的 context_usage 恢复指示器，避免在历史加载完成前变成 1% 误显示
    try {
      const cuRow = (lastSessionsCache || []).find((r) => r.session_id === sessionId);
      const cu = cuRow && cuRow.context_usage;
      if (cu && typeof updateTokenUsage === 'function') {
        var cuPt = (typeof pickContextUsageTokens === 'function')
          ? pickContextUsageTokens(cu) : (Number(cu.prompt_tokens) || 0);
        if (cuPt > 0) {
          updateTokenUsage({ prompt_tokens: cuPt, peak_prompt_tokens: cu.peak_prompt_tokens });
        }
      }
    } catch (_) {}
    const r = await fetch('/api/ui/session/history?session_id=' + encodeURIComponent(sessionId) +
      '&agent_id=' + encodeURIComponent(agentId) + projectQuerySuffix());
    const j = await parseJsonResponse(r);
    if (!r.ok) throw new Error(j.detail || r.statusText);
    if (gen !== _historyLoadSeq || forSid !== sessionId) return;  // 已切到别的会话
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
    // 滚动到底部：先立刻贴底，再在接下来 1.5s 内持续钉底。
    // 只写一次不够 —— 图片 / mermaid / 字体 / 抽屉重排都会在之后改变内容高度，
    // 高度一涨，视口就离开底部（用户看到「先到底又弹回中间」）。
    scrollLogForce();
    requestAnimationFrame(() => {
      scrollLogForce();
      pinLogBottomFor(1500);
    });
    // 历史加载完成后用持久化的 context_usage 校正指示器
    try {
      const cu = j && j.context_usage;
      if (cu && typeof updateTokenUsage === 'function') {
        var histPt = (typeof pickContextUsageTokens === 'function')
          ? pickContextUsageTokens(cu) : (Number(cu.prompt_tokens) || 0);
        if (histPt > 0) {
          updateTokenUsage({ prompt_tokens: histPt, peak_prompt_tokens: cu.peak_prompt_tokens });
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
    if (gen !== _historyLoadSeq || forSid !== sessionId) return;
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
