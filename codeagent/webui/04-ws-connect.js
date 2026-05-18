// ── Token 用量更新 ────────────────────────────────────────────
let _tokenContextMax = 200000; // 默认 200k tokens，后续可从模型配置读取

function setTokenContextMax(maxTokens) {
  _tokenContextMax = maxTokens > 0 ? maxTokens : 200000;
}

function updateTokenUsage(bodyBytes, compactMinBytes) {
  var el = document.getElementById('tokenUsage');
  if (!el) return;
  // bytes → tokens 粗估（÷ 4）
  var curTokens = Math.round((bodyBytes || 0) / 4);
  var maxTokens = _tokenContextMax;
  if (compactMinBytes > 0) {
    // 用 compactMinBytes 反推上限，更贴合实际模型的上下文窗口
    maxTokens = Math.round(compactMinBytes / 4);
  }
  if (curTokens <= 0) { el.style.display = 'none'; return; }
  el.style.display = 'inline-flex';
  var pct = Math.round((curTokens / maxTokens) * 100);
  var label = (curTokens >= 1000 ? (curTokens / 1000).toFixed(1) + 'k' : String(curTokens))
    + '/' + (maxTokens >= 1000 ? (maxTokens / 1000).toFixed(0) + 'k' : String(maxTokens));
  el.textContent = '📊 ' + label;
  el.title = '上下文约 ' + curTokens.toLocaleString() + ' tokens / ' + maxTokens.toLocaleString() + ' tokens (' + pct + '%)';
  el.classList.toggle('is-warm', pct >= 60 && pct < 85);
  el.classList.toggle('is-hot', pct >= 85);
}

/** 从 DOM 中所有气泡内容重新估算 token 用量（compact 后调用） */
function recalcTokenUsageFromDom() {
  var totalBytes = 0;
  var bubbles = document.querySelectorAll('.bubble');
  bubbles.forEach(function (b) {
    var text = b.textContent || '';
    // 粗估 UTF-8 字节数
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if (code < 0x80) totalBytes += 1;
      else if (code < 0x800) totalBytes += 2;
      else if (code < 0xD800 || code >= 0xE000) totalBytes += 3;
      else { i++; totalBytes += 4; } // surrogate pair
    }
  });
  // 每条消息的系统开销粗估（角色标记、格式等）
  totalBytes += bubbles.length * 80;
  var compactMinBytes = _tokenContextMax * 4; // 反推阈值
  updateTokenUsage(totalBytes, compactMinBytes);
}

function connectWs() {
  if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
  if (ws) { try { ws.close(); } catch (e) {} ws = undefined; }
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  var wsTokQs = '';
  try {
    var wst = sessionStorage.getItem('oa_webui_ws_token');
    if (wst) wsTokQs = '&webui_token=' + encodeURIComponent(wst);
  } catch (_) {}
  const sock = new WebSocket(
    proto + '//' + location.host +
    '/ws?session_id=' + encodeURIComponent(sessionId) +
    '&agent_id=' + encodeURIComponent(agentId) +
    wsTokQs
  );
  ws = sock;
  sock.onmessage = (ev) => {
    try {
      const j = JSON.parse(ev.data);
      if (j.type === 'tool_start' || j.type === 'tool_output' || j.type === 'tool_end') {
        handleProgressEvent(j); return;
      }
      if (j.type === 'chat_stop_requested') {
        if (j.session_id === sessionId) systemMsg('info', '已请求停止当前执行。');
        return;
      }
      if (j.type === 'chat_cancelled') {
        if (j.session_id === sessionId) systemMsg('info', '当前执行已停止。');
        return;
      }
      if (j.type === 'context_compact') {
        if (j.session_id === sessionId) {
          systemMsg('info', '上下文已压缩（compact）：丢弃 ' + (j.dropped_messages || 0) + ' 条历史消息，保留最近 ' + (j.kept_user_rounds || 0) + ' 轮。');
          // compact 后用量会骤降，重新从 DOM 估算
          recalcTokenUsageFromDom();
        }
        return;
      }
      if (j.type === 'context_usage') {
        if (j.session_id === sessionId) {
          const cur = Number(j.body_bytes || 0);
          const minb = Number(j.compact_min_bytes || 0);
          updateTokenUsage(cur, minb);
        }
        return;
      }
      // Streaming text tokens for the current session
      if (j.type === 'text_delta' && j.session_id === sessionId) {
        updateStreamBubbleText(j.text || '');
        markLiveProgressSeen(sessionId);
        return;
      }

      if (j.type === 'text_done' && j.session_id === sessionId) {
        var finalized = finalizeStreamBubble(j.text || '', []);
        if (!finalized) {
          var remainingText = '';
          if (typeof _streamUnconsumedSuffix === 'function') {
            remainingText = _streamUnconsumedSuffix(j.text || '');
          } else if (typeof _streamDeltaText === 'function') {
            remainingText = _streamDeltaText(j.text || '');
          }
          if (remainingText && typeof bubbleAgentWithSplitToolTrace === 'function') {
            bubbleAgentWithSplitToolTrace(remainingText, [], null, { at: Date.now(), skipScroll: true });
          }
        }
        if (typeof _advanceStreamConsumedLen === 'function') {
          _advanceStreamConsumedLen(j.text || '');
        }
        if (typeof syncLiveToolsFromToolTrace === 'function') {
          syncLiveToolsFromToolTrace(j.tool_trace || []);
        }
        // Remember this reply so the subsequent WS 'reply' event is deduped.
        if (typeof rememberLocalAgentReply === 'function') {
          rememberLocalAgentReply(j.text || '');
        }
        markWsTextDone(sessionId);
        markLiveProgressSeen(sessionId);
        if (webuiSessionsEnabled) refreshSessionList().catch(function() {});
        if (typeof recalcTokenUsageFromDom === 'function') recalcTokenUsageFromDom();
        return;
      }
      if (j.type !== 'reply') return;
      if ((chatInflightBySid[sessionId] || 0) > 0) return;
      const t = normReply(j.text);
      if (!t) return;
      if (t === lastLocalAgentReplyNorm && (Date.now() - lastLocalAgentReplyAt) < 15000) return;
      if (typeof bubbleAgentWithSplitToolTrace === 'function') {
        bubbleAgentWithSplitToolTrace(j.text || '', j.tool_trace || [], null, { at: Date.now() });
      } else {
        bubble('agent', j.text || '', { at: Date.now(), toolTrace: j.tool_trace || [] });
      }
      if (typeof recalcTokenUsageFromDom === 'function') recalcTokenUsageFromDom();
      if (webuiSessionsEnabled) refreshSessionList().catch(() => {});
    } catch (_) {}
  };
  sock.onclose = () => {
    if (pauseWsReconnect) return;
    wsReconnectTimer = setTimeout(connectWs, 2000);
  };
}

function reconnectWsForSession() {
  pauseWsReconnect = true;
  if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
  if (ws) { try { ws.close(); } catch (e) {} ws = undefined; }
  pauseWsReconnect = false;
  connectWs();
}

// Optional WS connection, gated by /api/ui/flags.ws_enabled
try {
  fetch('/api/ui/flags?agent_id=' + encodeURIComponent(agentId)).then(async (r) => {
    if (!r.ok) return { ws_enabled: false };
    return await r.json();
  }).then(f => {
    if (f && f.ws_enabled === false) return;
    connectWs();
  }).catch(_ => {});
} catch (_) {}
