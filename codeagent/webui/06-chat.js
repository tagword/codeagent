/* ================================================================
 * 06-chat.js
 *   - Send / stop / keybinding handlers
 *   - Auto-grow textarea
 *   - Setup greeting (LLM-based first-time greet)
 *   - Top-level tabs dispatcher
 * ================================================================ */

// ---------------- Setup greeting (once per browser profile) ----------------

(async () => {
  try {
    const qs = new URLSearchParams(location.search || '');
    if (qs.get('setup_done') !== '1') return;
    if (localStorage.getItem('oa_setup_greeted') === '1') return;
    localStorage.setItem('oa_setup_greeted', '1');
    const greetSid = sessionId;
    bumpChatInflight(greetSid, 1);
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          session_id: greetSid, agent_id: agentId, project_id: projectId,
          message: '请根据当前 config/*.md 向用户主动打招呼，并用 2-4 条要点说明下一步如何配置/使用（包括 config/seed.env 与 skills/插件可选项）。'
        })
      });
      const j = await r.json().catch(() => ({}));
      const replySid = (j.session_id || greetSid);
      if (r.ok && j.reply && sessionId === replySid) {
        rememberLocalAgentReply(j.reply);
        if (typeof bubbleAgentWithSplitToolTrace === 'function') {
          bubbleAgentWithSplitToolTrace(j.reply, j.tool_trace || [], null, { at: Date.now() });
        } else {
          bubble('agent', j.reply, { at: Date.now(), toolTrace: j.tool_trace || [] });
        }
      }
    } finally { bumpChatInflight(greetSid, -1); }
  } catch (_) {}
})();

// ---------------- Send / stop ----------------

sendBtn.onclick = async () => {
  const text = msg.value.trim();
  if (!text) return;
  msg.value = '';
  const requestSid = sessionId;
  scrollLogForce();
  bubble('user', text, { at: Date.now() });
  if (typeof resetAgentReplyDedupe === 'function') resetAgentReplyDedupe();
  bumpChatInflight(requestSid, 1);
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: requestSid, agent_id: agentId, project_id: projectId,
        message: text, enable_thinking: getThinkState(),
        llm_id: (modelSelect ? modelSelect.value : '') || undefined
      })
    });
    const j = await r.json().catch(async () => {
      const text = await r.text().catch(() => '');
      return { detail: text || r.statusText };
    });
    if (!r.ok) throw new Error(j.detail || r.statusText);
    const replySid = (j.session_id || requestSid);
    const reply = j.reply || '';
    const viewingReplySession = sessionId === replySid;
    if (viewingReplySession) {
      rememberLocalAgentReply(reply);
      const hadWsTextDone = typeof consumeWsTextDone === 'function' ? consumeWsTextDone(replySid) : false;
      const hadLiveProgress = consumeLiveProgressSeen(replySid);
      const traceLen = (j.tool_trace || []).length;
      // 有 tool_trace 时也要渲染：否则会出现「调用了工具但 WebUI 空白」（reply 为空时常发生）。
      if (!hadWsTextDone && (reply || traceLen) && !hadLiveProgress) {
        if (typeof bubbleAgentWithSplitToolTrace === 'function') {
          bubbleAgentWithSplitToolTrace(reply, j.tool_trace || [], null, { at: Date.now() });
        } else {
          bubble('agent', reply, { at: Date.now(), toolTrace: j.tool_trace || [] });
        }
      } else if (!hadWsTextDone && hadLiveProgress) {
        if (reply) {
          var finalized = (typeof finalizeStreamBubble === 'function')
            ? finalizeStreamBubble(reply, [])
            : null;
          var remainingDelta = '';
          if (typeof _streamUnconsumedSuffix === 'function') {
            remainingDelta = _streamUnconsumedSuffix(reply);
          } else if (typeof _streamDeltaText === 'function') {
            remainingDelta = _streamDeltaText(reply);
          }
          if (!finalized && remainingDelta && typeof bubbleAgentWithSplitToolTrace === 'function') {
            bubbleAgentWithSplitToolTrace(remainingDelta, [], null, { at: Date.now(), skipScroll: true });
          }
          if (typeof _advanceStreamConsumedLen === 'function') {
            _advanceStreamConsumedLen(reply);
          }
        }
        if (typeof syncLiveToolsFromToolTrace === 'function') {
          syncLiveToolsFromToolTrace(j.tool_trace || []);
        }
      }
      const _tt = j.tool_trace || [];
      if (j.tools_used && j.tools_used.length && !_tt.length && !hadLiveProgress)
        systemMsg('tools', '工具：' + j.tools_used.join(', '));
    }
    if (webuiSessionsEnabled) {
      pinSessionToTopOnce = requestSid;
      await refreshSessionList();
      if (viewingReplySession) {
        const row2 = lastSessionsCache.find((r) => r.session_id === sessionId);
        markSessionReadByCount(sessionId, row2 ? (row2.message_count || 0) : 0);
      }
    }
  } catch (e) { if (sessionId === requestSid) systemMsg('err', String(e)); }
  finally { bumpChatInflight(requestSid, -1); }
};

stopBtn.onclick = async () => {
  const requestSid = sessionId;
  if ((chatInflightBySid[requestSid] || 0) <= 0) return;
  try {
    stopBtn.disabled = true;
    const r = await fetch('/api/chat/stop', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: requestSid, agent_id: agentId })
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.statusText);
    if (sessionId === requestSid) systemMsg('info', j.active ? '已请求停止当前执行；当前工具若支持中断，会尽快停止。' : '当前会话没有正在运行的 agent。');
  } catch (e) { if (sessionId === requestSid) systemMsg('err', '停止失败：' + String(e)); }
  finally { updateComposerButtons(); }
};

updateComposerButtons();

msg.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  if (e.shiftKey) return;
  // macOS IME (中文输入法) 在候选词确认时也会触发 Enter keydown，
  // isComposing 为 true 表示处于输入法组合状态，此时不应发送消息。
  if (e.isComposing || e.keyCode === 229) return;
  e.preventDefault();
  sendBtn.click();
});

msg.addEventListener('input', () => {
  msg.style.height = 'auto';
  msg.style.height = Math.min(msg.scrollHeight, 220) + 'px';
});

// ---------------- Active page persistence (localStorage) ----------------

const TAB_KEY = 'oa_active_page';

function switchToPage(id) {
  if (!id) return;
  document.querySelectorAll('.page').forEach((p) => p.classList.remove('active'));
  const page = document.getElementById('page-' + id);
  if (page) page.classList.add('active');
}

function activatePage(id) {
  switchToPage(id);
  try { localStorage.setItem(TAB_KEY, id); } catch (_) {}
  if (id === 'config') { loadChatEnvConfig(); loadLlmPresets(); loadConfigPaths(); loadGitRemoteConfig(); }
  if (id === 'tasks') { loadCronPanel(); }
  // id 'tasks' 对应导航栏「计划」
  if (id === 'agent') { loadAgentPage(); }
  if (id === 'chat' && webuiSessionsEnabled) {
    refreshSessionList().catch(() => {});
    loadTranscriptIntoLog(true);
  }
  if (id === 'chat' || id === 'config') refreshModelSelect().catch(() => {});
}

