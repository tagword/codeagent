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
        if (j.session_id === sessionId) systemMsg('info', '上下文已压缩（compact）：丢弃 ' + (j.dropped_messages || 0) + ' 条历史消息，保留最近 ' + (j.kept_user_rounds || 0) + ' 轮。');
        return;
      }
      if (j.type === 'context_usage') {
        if (j.session_id === sessionId) {
          const cur = Number(j.body_bytes || 0);
          const minb = Number(j.compact_min_bytes || 0);
          if (cur > 0 && minb > 0) systemMsg('info', '上下文用量接近阈值：约 ' + Math.round((cur / minb) * 100) + '%（' + cur + '/' + minb + ' bytes）。达到阈值将触发 compact。');
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
