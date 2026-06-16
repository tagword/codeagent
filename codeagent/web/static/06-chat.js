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
    if (tryGetLS(STORAGE_KEYS.SETUP_GREETED) === '1') return;
    trySetLS(STORAGE_KEYS.SETUP_GREETED, '1');
    const greetSid = sessionId;
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          session_id: greetSid, agent_id: agentId, project_id: projectId,
          message: '请向用户简短打招呼（2-3 句），并说明：① 输入框下方可切换思考模式与主模型；② 点模型 pill 可打开模型栈（识图/生图等需在配置页添加）；③ 上下文占用指示器显示 token 用量，超过 30k 会自动压缩；④ 更多设置在左侧「配置」。'
        })
      });
      const j = await r.json().catch(() => ({}));
      const replySid = (j.session_id || greetSid);
      if (r.ok && j.reply && sessionId === replySid) {
        rememberLocalAgentReply(j.reply);
        if (typeof bubbleAgentWithSplitToolTrace === 'function') {
          bubbleAgentWithSplitToolTrace(j.reply, j.tool_trace || [], { at: Date.now() });
        } else {
          bubble('agent', j.reply, { at: Date.now(), toolTrace: j.tool_trace || [] });
        }
      }
    } catch (_) {}
  } catch (_) {}
})();

// ---------------- Send / stop ----------------

async function stopActiveChat() {
  const requestSid = sessionId;
  if (!isSessionRunning(requestSid)) return;
  const btn = (typeof stopBtn !== 'undefined' && stopBtn) || sendBtn;
  try {
    if (btn) btn.disabled = true;
    const r = await fetch('/api/chat/stop', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: requestSid, agent_id: agentId })
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || r.statusText);
    if (sessionId === requestSid) {
      if (j.cancelled) {
        systemMsg('info', '已请求停止当前执行；当前工具若支持中断，会尽快停止。');
      } else {
        systemMsg('info', '当前会话没有正在运行的 agent。');
        setSessionRunning(requestSid, false);
      }
    }
  } catch (e) { if (sessionId === requestSid) systemMsg('err', '停止失败：' + String(e)); }
  finally { updateComposerButtons(); }
}

function buildChatRequestBody(requestSid, text, attachmentIds) {
  return {
    session_id: requestSid, agent_id: agentId, project_id: projectId,
    message: text,
    attachment_ids: attachmentIds.length ? attachmentIds : undefined,
    enable_thinking: getThinkState(),
    reasoning_effort: getThinkState() ? getReasoningEffort() : undefined,
    llm_id: (modelSelect && modelSelect.value !== '__default__') ? modelSelect.value : undefined,
    vision_llm_id: (typeof getSelectedVisionModel === 'function' ? getSelectedVisionModel() : '') || undefined,
    image_gen_llm_id: (typeof getSelectedImageGenModel === 'function' ? getSelectedImageGenModel() : '') || undefined,
    audio_llm_id: (typeof getSelectedAudioModel === 'function' ? getSelectedAudioModel() : '') || undefined,
    music_llm_id: (typeof getSelectedMusicModel === 'function' ? getSelectedMusicModel() : '') || undefined,
    video_gen_llm_id: (typeof getSelectedVideoGenModel === 'function' ? getSelectedVideoGenModel() : '') || undefined
  };
}

async function submitChatMessage() {
  // 运行中且无输入 → 停止；有输入 → 注入队列（不停止）
  if (isSessionRunning(sessionId) && !composeHasSendPayload()) {
    await stopActiveChat();
    return;
  }

  const text = msg.value.trim();
  const hasPending = pendingAttachments && pendingAttachments.length > 0;
  if (!text && !hasPending) return;

  if (hasPending) {
    let needImage = false;
    let needVideo = false;
    let needAudio = false;
    pendingAttachments.forEach(function(p) {
      const m = p.mime || '';
      if (m.startsWith('image/')) needImage = true;
      if (m.startsWith('video/')) needVideo = true;
      if (m.startsWith('audio/')) needAudio = true;
    });
    if (needImage && typeof attachmentImageReady === 'function' && !attachmentImageReady()) {
      systemMsg('err', '请先配置识图：多模态 LLM 或 MiniMax MCP');
      return;
    }
    if (needVideo && typeof attachmentVideoReady === 'function' && !attachmentVideoReady()) {
      systemMsg('err', '请先选择多模态模型（视频分析）');
      return;
    }
    if (needAudio && typeof audioModelReadyForAttachments === 'function' && !audioModelReadyForAttachments()) {
      systemMsg('err', '请先选择音频转写模型');
      return;
    }
  }

  msg.value = '';
  if (typeof saveMsgDraft === 'function') saveMsgDraft();
  updateComposerButtons();

  const requestSid = sessionId;
  scrollLogForce();
  let attachmentIds = [];
  try {
    if (hasPending && typeof uploadPendingAttachments === 'function') {
      attachmentIds = await uploadPendingAttachments();
    }
  } catch (e) {
    systemMsg('err', String(e));
    return;
  }

  const displayText = text || (attachmentIds.length ? '[附件]' : '');
  bubble('user', displayText, { at: Date.now(), attachmentIds: attachmentIds });
  if (typeof resetAgentReplyDedupe === 'function') resetAgentReplyDedupe();

  // 运行状态由后端 WS run_started / run_finished 驱动；此处不手动 bump
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildChatRequestBody(requestSid, text, attachmentIds))
    });
    const j = await r.json().catch(async () => {
      const respText = await r.text().catch(() => '');
      return { detail: respText || r.statusText };
    });

    if (r.status === 202 && j.queued) {
      setSessionRunning(requestSid, true);
      if (sessionId === requestSid) {
        systemMsg('info', '已加入执行队列，将在当前步骤完成后继续处理。');
      }
      if (webuiSessionsEnabled) {
        pinSessionToTopOnce = requestSid;
        await refreshSessionList();
      }
      return;
    }

    if (!r.ok) throw new Error(j.detail || r.statusText);

    const replySid = (j.session_id || requestSid);
    const reply = j.reply || '';
    const viewingReplySession = sessionId === replySid;
    if (viewingReplySession) {
      rememberLocalAgentReply(reply);
      const hadWsTextDone = typeof consumeWsTextDone === 'function' ? consumeWsTextDone(replySid) : false;
      const hadLiveProgress = consumeLiveProgressSeen(replySid);
      const traceLen = (j.tool_trace || []).length;
      if (!hadWsTextDone && (reply || traceLen) && !hadLiveProgress) {
        if (typeof bubbleAgentWithSplitToolTrace === 'function') {
          bubbleAgentWithSplitToolTrace(reply, j.tool_trace || [], { at: Date.now() });
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
            bubbleAgentWithSplitToolTrace(remainingDelta, [], { at: Date.now(), skipScroll: true });
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
      if (j.tools_used && j.tools_used.length && !_tt.length && !hadLiveProgress) {
        systemMsg('tools', '工具：' + j.tools_used.join(', '));
      }
      if (j.cancelled && sessionId === requestSid) {
        systemMsg('info', '当前执行已停止。');
      }
    }

    if (webuiSessionsEnabled) {
      pinSessionToTopOnce = requestSid;
      await refreshSessionList();
      if (viewingReplySession) {
        const row2 = lastSessionsCache.find((r) => r.session_id === sessionId);
        markSessionReadByCount(sessionId, row2 ? (row2.message_count || 0) : 0);
      }
    }

    window._lastContextUsage = j.context || null;
    window._lastAccumulatedUsage = j.accumulated_usage || null;
  } catch (e) {
    if (sessionId === requestSid) systemMsg('err', String(e));
  } finally {
    var ctx = window._lastContextUsage;
    if (ctx && typeof updateTokenUsage === 'function') {
      updateTokenUsage(ctx);
      window._lastContextUsage = null;
    } else if (typeof recalcTokenUsageFromDom === 'function') {
      setTimeout(recalcTokenUsageFromDom, 50);
    }
    var au = window._lastAccumulatedUsage;
    if (au && typeof updateSidebarCost === 'function') {
      updateSidebarCost(au);
      window._lastAccumulatedUsage = null;
    }
  }
}

if (sendBtn) sendBtn.onclick = submitChatMessage;

if (typeof stopBtn !== 'undefined' && stopBtn) stopBtn.onclick = stopActiveChat;

updateComposerButtons();

if (msg) {
  msg.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  if (e.shiftKey) return;
  if (e.isComposing || e.keyCode === 229) return;
  if (window.matchMedia('(max-width: 768px)').matches) return;
  e.preventDefault();
  sendBtn.click();
  });

  msg.addEventListener('input', () => {
    msg.style.height = 'auto';
    msg.style.height = Math.min(msg.scrollHeight, 220) + 'px';
    updateComposerButtons();
  });
}

// ---------------- Active page persistence (localStorage) ----------------

const TAB_KEY = STORAGE_KEYS.SESS_ACTIVE_PAGE;
const WORKSPACE_PAGE_IDS = ['chat', 'config', 'tasks', 'agent', 'files', 'team', 'hub'];

function switchToPage(id) {
  if (!id) return;
  const targetId = 'page-' + id;
  WORKSPACE_PAGE_IDS.forEach((suffix) => {
    const p = document.getElementById('page-' + suffix);
    if (!p) return;
    p.classList.toggle('active', p.id === targetId);
    p.scrollTop = 0;
  });
  var ws = document.querySelector('.workspace');
  if (ws) ws.scrollTop = 0;
}

function activatePage(id) {
  var actMode = '';
  try { actMode = document.body.getAttribute('data-activity-mode') || ''; } catch (_) {}
  if (actMode && actMode !== 'chat' && actMode !== 'stats' && actMode !== 'files' && id === 'chat') {
    id = actMode;
  }
  switchToPage(id);
  try { localStorage.setItem(TAB_KEY, id); } catch (_) {}
  if (id === 'config') {
    loadChatEnvConfig();
    loadLlmPresets();
    if (typeof loadMcpEnvConfig === 'function') loadMcpEnvConfig();
    loadConfigPaths();
    loadGitRemoteConfig();
  }
  if (id === 'tasks') { loadCronPanel(); }
  if (id === 'agent') { loadAgentPage(); }
  if (id === 'chat' && webuiSessionsEnabled) {
    refreshSessionList().catch(() => {});
    loadSessionHistoryIntoLog(true);
  }
  if (id === 'chat' || id === 'config') {
    if (typeof refreshMultimodalModelSelects === 'function') {
      refreshMultimodalModelSelects().catch(function() {});
    } else {
      refreshModelSelect().catch(function() {});
    }
  }
}
