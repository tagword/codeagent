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
        systemMsg('info', '⏳ 正在完成本轮回答…');
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
            ? finalizeStreamBubble(reply)
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
        systemMsg('info', '✅ 已停止。');
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
      var ctxPt = (typeof pickContextUsageTokens === 'function')
        ? pickContextUsageTokens(ctx) : (Number(ctx.prompt_tokens) || 0);
      if (ctxPt > 0) updateTokenUsage(ctx);
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

// ---------------- MCP skill slash suggestions ----------------

const mcpSkillSuggest = {
  box: null,
  items: [],
  active: 0,
  servers: null,
  skillsByServer: {},
  loadingKey: '',
};

function ensureMcpSkillSuggestBox() {
  if (mcpSkillSuggest.box) return mcpSkillSuggest.box;
  const host = document.getElementById('composeBox') || (msg && msg.parentElement);
  if (!host) return null;
  if (!document.getElementById('mcpSkillSuggestStyle')) {
    const style = document.createElement('style');
    style.id = 'mcpSkillSuggestStyle';
    style.textContent = [
      '.mcp-skill-suggest{position:absolute;left:12px;right:12px;bottom:calc(100% + 8px);z-index:50;background:var(--bg-panel,#fff);border:1px solid var(--border,#ddd);border-radius:var(--r-md,10px);box-shadow:0 12px 30px rgba(0,0,0,.16);overflow:hidden;max-height:260px;display:none;}',
      '.mcp-skill-suggest__head{padding:7px 10px;font-size:11px;color:var(--text-subtle,#777);border-bottom:1px solid var(--border,#eee);background:var(--bg-subtle,#f7f7f7);}',
      '.mcp-skill-suggest__item{display:flex;gap:8px;align-items:flex-start;width:100%;border:0;background:transparent;text-align:left;padding:9px 10px;cursor:pointer;color:var(--text,#222);}',
      '.mcp-skill-suggest__item:hover,.mcp-skill-suggest__item.is-active{background:var(--accent-dim,#e8f0fe);}',
      '.mcp-skill-suggest__name{font-weight:600;font-size:13px;line-height:1.3;}',
      '.mcp-skill-suggest__meta{font-size:11px;color:var(--text-subtle,#777);line-height:1.35;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.mcp-skill-suggest__badge{font-size:10px;padding:1px 5px;border-radius:999px;background:var(--bg-2,#eee);color:var(--text-subtle,#666);flex-shrink:0;margin-top:1px;}',
    ].join('');
    document.head.appendChild(style);
  }
  try {
    const cs = window.getComputedStyle(host);
    if (cs.position === 'static') host.style.position = 'relative';
  } catch (_) {}
  const box = document.createElement('div');
  box.className = 'mcp-skill-suggest';
  box.setAttribute('role', 'listbox');
  host.appendChild(box);
  mcpSkillSuggest.box = box;
  return box;
}

function hideMcpSkillSuggest() {
  const box = mcpSkillSuggest.box;
  mcpSkillSuggest.items = [];
  mcpSkillSuggest.active = 0;
  if (box) {
    box.style.display = 'none';
    box.innerHTML = '';
  }
}

async function loadMcpSuggestServers() {
  if (mcpSkillSuggest.servers) return mcpSkillSuggest.servers;
  const r = await fetch('/api/ui/mcp', { credentials: 'same-origin' });
  const j = await r.json().catch(function() { return {}; });
  if (!r.ok) throw new Error(j.detail || r.statusText || 'MCP 配置读取失败');
  const servers = (j.config && j.config.servers) ? j.config.servers : {};
  mcpSkillSuggest.servers = Object.keys(servers || {}).sort().map(function(id) {
    return { id: id, config: servers[id] || {} };
  });
  return mcpSkillSuggest.servers;
}

async function loadMcpSuggestSkills(serverId) {
  if (mcpSkillSuggest.skillsByServer[serverId]) return mcpSkillSuggest.skillsByServer[serverId];
  const r = await fetch('/api/ui/mcp/skills?server_id=' + encodeURIComponent(serverId), { credentials: 'same-origin' });
  const j = await r.json().catch(function() { return {}; });
  if (!r.ok) throw new Error(j.detail || r.statusText || 'MCP skill 读取失败');
  const skills = Array.isArray(j.skills) ? j.skills : [];
  mcpSkillSuggest.skillsByServer[serverId] = skills;
  return skills;
}

function getMcpSlashQuery() {
  if (!msg) return null;
  const value = msg.value || '';
  const caret = msg.selectionStart || 0;
  const before = value.slice(0, caret);
  if (before.indexOf('\n') >= 0) return null;
  const m = before.match(/^\/([A-Za-z][A-Za-z0-9_-]*)(?::([A-Za-z0-9_.:-]*))?(?:\s+([A-Za-z0-9_.:-]*))?$/);
  if (!m || m[1] === 'skill') return null;
  return {
    raw: before,
    serverPrefix: m[1],
    skillPrefix: m[2] !== undefined ? (m[2] || '') : (m[3] || ''),
    hasSkillPart: before.indexOf(':') >= 0 || before.indexOf(' ') >= 0,
  };
}

function renderMcpSkillSuggest(title, items) {
  const box = ensureMcpSkillSuggestBox();
  if (!box) return;
  mcpSkillSuggest.items = items || [];
  mcpSkillSuggest.active = Math.min(mcpSkillSuggest.active, Math.max(0, mcpSkillSuggest.items.length - 1));
  if (!mcpSkillSuggest.items.length) {
    hideMcpSkillSuggest();
    return;
  }
  box.innerHTML = '';
  const head = document.createElement('div');
  head.className = 'mcp-skill-suggest__head';
  head.textContent = title;
  box.appendChild(head);
  mcpSkillSuggest.items.forEach(function(item, idx) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'mcp-skill-suggest__item' + (idx === mcpSkillSuggest.active ? ' is-active' : '');
    btn.setAttribute('role', 'option');
    btn.setAttribute('aria-selected', idx === mcpSkillSuggest.active ? 'true' : 'false');
    const badge = document.createElement('span');
    badge.className = 'mcp-skill-suggest__badge';
    badge.textContent = item.kind === 'server' ? 'MCP' : 'skill';
    const main = document.createElement('span');
    main.style.minWidth = '0';
    const name = document.createElement('div');
    name.className = 'mcp-skill-suggest__name';
    name.textContent = item.label;
    const meta = document.createElement('div');
    meta.className = 'mcp-skill-suggest__meta';
    meta.textContent = item.detail || '';
    main.appendChild(name);
    if (item.detail) main.appendChild(meta);
    btn.appendChild(badge);
    btn.appendChild(main);
    btn.addEventListener('mouseenter', function() {
      mcpSkillSuggest.active = idx;
      renderMcpSkillSuggest(title, mcpSkillSuggest.items);
    });
    btn.addEventListener('mousedown', function(ev) {
      ev.preventDefault();
      applyMcpSkillSuggest(item);
    });
    box.appendChild(btn);
  });
  box.style.display = 'block';
}

function applyMcpSkillSuggest(item) {
  if (!item || !msg) return;
  if (item.kind === 'server') {
    msg.value = '/' + item.serverId + ':';
  } else {
    if (item.kind !== 'skill') return;
    msg.value = '/' + item.serverId + ':' + item.skillName + ' ';
  }
  hideMcpSkillSuggest();
  msg.focus();
  msg.selectionStart = msg.selectionEnd = msg.value.length;
  if (typeof saveMsgDraft === 'function') saveMsgDraft();
  updateComposerButtons();
}

async function refreshMcpSkillSuggest() {
  const q = getMcpSlashQuery();
  if (!q) {
    hideMcpSkillSuggest();
    return;
  }
  const key = q.serverPrefix + '\n' + q.skillPrefix + '\n' + q.hasSkillPart;
  mcpSkillSuggest.loadingKey = key;
  try {
    const servers = await loadMcpSuggestServers();
    if (mcpSkillSuggest.loadingKey !== key) return;
    const matches = servers.filter(function(s) {
      return s.id.toLowerCase().indexOf(q.serverPrefix.toLowerCase()) === 0;
    });
    if (!matches.length) {
      renderMcpSkillSuggest('没有匹配的 MCP server', []);
      return;
    }
    if (matches.length > 1 && !q.hasSkillPart) {
      renderMcpSkillSuggest('选择 MCP server', matches.slice(0, 8).map(function(s) {
        return {
          kind: 'server',
          serverId: s.id,
          label: '/' + s.id,
          detail: (s.config.transport || 'stdio') + (s.config.url ? ' · ' + s.config.url : ''),
        };
      }));
      return;
    }
    const serverId = matches[0].id;
    const skills = await loadMcpSuggestSkills(serverId);
    if (mcpSkillSuggest.loadingKey !== key) return;
    const prefix = (q.skillPrefix || '').toLowerCase();
    const filtered = skills.filter(function(s) {
      return !prefix || String(s.name || '').toLowerCase().indexOf(prefix) === 0;
    }).slice(0, 10);
    renderMcpSkillSuggest('选择 ' + serverId + ' 的 skill', filtered.map(function(s) {
      const args = Array.isArray(s.arguments) && s.arguments.length
        ? '参数：' + s.arguments.map(function(a) { return a.name || ''; }).filter(Boolean).join(', ')
        : '';
      return {
        kind: 'skill',
        serverId: serverId,
        skillName: s.name,
        label: s.name,
        detail: [s.description || '', args].filter(Boolean).join(' · '),
      };
    }));
  } catch (e) {
    renderMcpSkillSuggest('MCP skill 读取失败', [{
      kind: 'none',
      label: String(e.message || e),
      detail: '',
    }]);
  }
}

function mcpSkillSuggestHandleKeydown(e) {
  const box = mcpSkillSuggest.box;
  if (!box || box.style.display !== 'block' || !mcpSkillSuggest.items.length) return false;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    mcpSkillSuggest.active = (mcpSkillSuggest.active + 1) % mcpSkillSuggest.items.length;
    renderMcpSkillSuggest((box.querySelector('.mcp-skill-suggest__head') || {}).textContent || '', mcpSkillSuggest.items);
    return true;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    mcpSkillSuggest.active = (mcpSkillSuggest.active - 1 + mcpSkillSuggest.items.length) % mcpSkillSuggest.items.length;
    renderMcpSkillSuggest((box.querySelector('.mcp-skill-suggest__head') || {}).textContent || '', mcpSkillSuggest.items);
    return true;
  }
  if (e.key === 'Enter' || e.key === 'Tab') {
    e.preventDefault();
    applyMcpSkillSuggest(mcpSkillSuggest.items[mcpSkillSuggest.active]);
    return true;
  }
  if (e.key === 'Escape') {
    e.preventDefault();
    hideMcpSkillSuggest();
    return true;
  }
  return false;
}

if (sendBtn) sendBtn.onclick = submitChatMessage;

if (typeof stopBtn !== 'undefined' && stopBtn) stopBtn.onclick = stopActiveChat;

updateComposerButtons();

if (msg) {
  msg.addEventListener('keydown', (e) => {
  if (mcpSkillSuggestHandleKeydown(e)) return;
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
    refreshMcpSkillSuggest();
  });
  msg.addEventListener('blur', () => {
    setTimeout(hideMcpSkillSuggest, 120);
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
