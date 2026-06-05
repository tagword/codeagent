// ── Token 用量更新（DeepSeek 精确计数） ─────────────────────────
let _tokenContextMax = 200000; // 默认 200k tokens

function setTokenContextMax(maxTokens) {
  _tokenContextMax = maxTokens > 0 ? maxTokens : 200000;
}

/** 更新 token 用量指示器（仅 token 用量，不含费用）
 *  @param {number|Object} curOrUsage - bodyBytes 或 {total_tokens, content_tokens}
 *  @param {number} [compactMinTokens] - 兼容旧格式的 min_tokens
 */
function updateTokenUsage(curOrUsage, compactMinTokens) {
  var el = document.getElementById('tokenUsage');
  if (!el) return;
  var segEls = el.querySelectorAll('.token-usage__seg');
  var pctEl = el.querySelector('.token-usage__pct');
  var curTokens = 0;
  var maxTokens = _tokenContextMax;
  if (typeof curOrUsage === 'object' && curOrUsage !== null) {
    // API prompt_tokens / legacy body_bytes (tokens) beat local estimate
    if (curOrUsage.prompt_tokens != null && Number(curOrUsage.prompt_tokens) > 0) {
      curTokens = Number(curOrUsage.prompt_tokens);
    } else if (curOrUsage.body_bytes != null && curOrUsage.body_bytes !== '' && Number(curOrUsage.body_bytes) > 0) {
      curTokens = Number(curOrUsage.body_bytes);
    } else if (curOrUsage.estimated_tokens != null && Number(curOrUsage.estimated_tokens) > 0) {
      curTokens = Number(curOrUsage.estimated_tokens);
    } else {
      curTokens = curOrUsage.total_tokens || 0;
    }
    if (curOrUsage.compact_min_tokens) maxTokens = Number(curOrUsage.compact_min_tokens);
    else if (curOrUsage.context_limit) maxTokens = curOrUsage.context_limit;
  } else {
    curTokens = Math.round((curOrUsage || 0) / 4);
    if (compactMinTokens > 0) maxTokens = compactMinTokens;
  }
  if (curTokens <= 0) {
    // 不隐藏 — 工具执行期间 body_bytes 可能短暂为 0，保持可见
    el.style.display = 'inline-flex';
    for (var si = 0; si < segEls.length; si++) {
      segEls[si].classList.toggle('is-on', false);
    }
    if (pctEl) pctEl.textContent = '0%';
    el.setAttribute('aria-valuenow', '0');
    el.setAttribute('aria-valuetext', '0 / 5 档，0%');
    el.title = '上下文占用';
    el.classList.remove('is-warm', 'is-hot');
    return;
  }
  el.style.display = 'inline-flex';
  var pct = maxTokens > 0 ? Math.round(Math.min((curTokens / maxTokens) * 100, 100)) : 0;
  var filled = pct > 0 ? Math.min(5, Math.ceil((pct / 100) * 5)) : 0;
  for (var si = 0; si < segEls.length; si++) {
    segEls[si].classList.toggle('is-on', si < filled);
  }
  if (pctEl) pctEl.textContent = pct + '%';
  el.setAttribute('aria-valuenow', String(pct));
  el.setAttribute('aria-valuemax', '100');
  el.setAttribute('aria-valuetext', filled + ' / 5 档，' + pct + '%');
  var curLabel = curTokens >= 1000 ? (curTokens / 1000).toFixed(1) + 'k' : String(curTokens);
  var maxLabel = maxTokens >= 1000 ? (maxTokens / 1000).toFixed(0) + 'k' : String(maxTokens);
  el.title = '上下文 ' + curLabel + ' / ' + maxLabel + ' tokens（' + pct + '%）';
  el.classList.toggle('is-warm', pct >= 60 && pct < 85);
  el.classList.toggle('is-hot', pct >= 85);
}

/** 更新侧边栏费用汇总
 *  @param {Object} accUsage - accumulated_usage 对象（含 per_model, total_cost）
 */
function updateSidebarCost(accUsage) {
  var el = document.getElementById('sidebarCost');
  if (!el) return;
  var body = el.querySelector('.sidebar-cost__body');
  if (!accUsage || !accUsage.per_model) { el.style.display = 'none'; return; }
  el.style.display = '';
  var totalCost = typeof accUsage.total_cost === 'number' ? accUsage.total_cost : 0;
  var lines = [];
  for (var model in accUsage.per_model) {
    var md = accUsage.per_model[model];
    var tok = md.total_tokens || 0;
    var cost = typeof md.cost === 'number' ? md.cost : 0;
    if (typeof accUsage.total_cost !== 'number') totalCost += cost;
    var modelLabel = model.replace(/^deepseek-/, 'DS ');
    var tokStr = tok >= 1000 ? (tok / 1000).toFixed(1) + 'k' : String(tok);
    var costStr = cost < 0.01 ? '\u00A5' + cost.toFixed(4) : (cost < 1 ? '\u00A5' + cost.toFixed(3) : '\u00A5' + cost.toFixed(2));
    lines.push({ model: modelLabel, tokens: tokStr, cost: costStr });
  }
  var html = '<div class="cost__list">';
  for (var i = 0; i < lines.length; i++) {
    var l = lines[i];
    html += '<div class="cost__row"><span class="cost__model">' + l.model + '</span>'
      + '<span class="cost__tokens">' + l.tokens + '</span>'
      + '<span class="cost__amount">' + l.cost + '</span></div>';
  }
  if (lines.length > 1) {
    var totalStr = totalCost < 0.01 ? '\u00A5' + totalCost.toFixed(4) : (totalCost < 1 ? '\u00A5' + totalCost.toFixed(3) : '\u00A5' + totalCost.toFixed(2));
    html += '<div class="cost__row cost__row--total"><span class="cost__model">\u5408\u8BA1</span><span class="cost__tokens"></span><span class="cost__amount">' + totalStr + '</span></div>';
  }
  html += '</div>';
  if (body) body.innerHTML = html;
  else el.innerHTML = '<div class="sidebar-cost__title">\u8FD0\u884C\u8D39\u7528</div>' + html;
}

/** 从 DOM 中所有气泡内容重新估算 token 用量（WS/API 不可用时的 fallback）
 *  使用 DeepSeek 公式：中文 0.6 token/char，英文 0.3 token/char
 */
function recalcTokenUsageFromDom() {
  var totalTokens = 0;
  var bubbles = document.querySelectorAll('.bubble');
  bubbles.forEach(function (b) {
    var text = b.textContent || '';
    var cn = 0, en = 0;
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if ((code >= 0x4E00 && code <= 0x9FFF) ||
          (code >= 0x3400 && code <= 0x4DBF) ||
          (code >= 0x20000 && code <= 0x2A6DF)) {
        cn++;
      } else {
        en++;
      }
    }
    totalTokens += Math.round(cn * 0.6 + en * 0.3);
  });
  // 每条消息系统开销（role 标记等）
  totalTokens += bubbles.length * 4;
  var compactMinTokens = _tokenContextMax;
  updateTokenUsage({ total_tokens: totalTokens }, compactMinTokens);
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
      const handler = WS_HANDLERS[j.type];
      if (handler) { handler(j); return; }
      if (j.type === 'reply') handleWsReply(j);
    } catch (_) {}
  };
  sock.onclose = () => {
    if (pauseWsReconnect) return;
    wsReconnectTimer = setTimeout(connectWs, 2000);
  };
}

// ---- WS message dispatcher (data-driven) -------------------------------

/** 派发表：j.type → handler。handler 必须容忍字段缺失；sessionId 匹配在主循环中已确认。 */
const WS_HANDLERS = {
  tool_start:   handleProgressEvent,
  tool_output:  handleProgressEvent,
  tool_end:     handleProgressEvent,
  chat_stop_requested: function (j) {
    if (j.session_id === sessionId) systemMsg('info', '已请求停止当前执行。');
  },
  chat_cancelled: function (j) {
    if (j.session_id === sessionId) systemMsg('info', '当前执行已停止。');
  },
  context_compact: handleWsContextCompact,
  context_usage:  handleWsContextUsage,
  text_delta:     handleWsTextDelta,
  text_done:      handleWsTextDone,
};

function handleWsContextCompact(j) {
  if (j.session_id !== sessionId) return;
  systemMsg('info', '上下文已压缩（compact）：丢弃 ' + (j.dropped_messages || 0)
    + ' 条历史消息，保留最近 ' + (j.kept_user_rounds || 0) + ' 轮。');
  // token 计数：优先 prompt_tokens_after，否则 body_bytes_after
  if (j.prompt_tokens_after != null && Number(j.prompt_tokens_after) > 0) {
    updateTokenUsage({
      prompt_tokens: Number(j.prompt_tokens_after),
      context_limit: j.context_limit,
      compact_min_tokens: j.compact_min_tokens,
    });
  } else if (typeof j.body_bytes_after === 'number') {
    updateTokenUsage({
      body_bytes: j.body_bytes_after,
      context_limit: j.context_limit,
      compact_min_tokens: j.compact_min_tokens,
    });
  }
}

/** context_usage：多种 token 计数来源的优先级收敛（统一入口） */
function handleWsContextUsage(j) {
  if (j.session_id && j.session_id !== sessionId) return;
  var cu = {
    context_limit: j.context_limit,
    compact_min_tokens: j.compact_min_tokens,
  };
  // 优先级：prompt_tokens > body_bytes > estimated_tokens > token_usage 对象 > 兜底 0
  if (j.prompt_tokens != null && Number(j.prompt_tokens) > 0) {
    cu.prompt_tokens = Number(j.prompt_tokens);
  } else if (j.body_bytes != null && Number(j.body_bytes) > 0) {
    cu.body_bytes = Number(j.body_bytes);
  } else if (j.estimated_tokens != null && Number(j.estimated_tokens) > 0) {
    cu.estimated_tokens = Number(j.estimated_tokens);
  } else if (j.token_usage) {
    updateTokenUsage(j.token_usage, j.compact_min_tokens);
    if (j.accumulated_usage && typeof updateSidebarCost === 'function') {
      updateSidebarCost(j.accumulated_usage);
    }
    return;
  } else {
    updateTokenUsage(Number(j.body_bytes || 0), Number(j.compact_min_tokens || 0));
    if (j.accumulated_usage && typeof updateSidebarCost === 'function') {
      updateSidebarCost(j.accumulated_usage);
    }
    return;
  }
  updateTokenUsage(cu);
  if (j.accumulated_usage && typeof updateSidebarCost === 'function') {
    updateSidebarCost(j.accumulated_usage);
  }
}

function handleWsTextDelta(j) {
  if (j.session_id !== sessionId) return;
  updateStreamBubbleText(j.text || '');
  if (typeof markLiveProgressSeen === 'function') markLiveProgressSeen(sessionId);
}

function handleWsTextDone(j) {
  if (j.session_id !== sessionId) return;
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
  if (typeof _advanceStreamConsumedLen === 'function') _advanceStreamConsumedLen(j.text || '');
  if (typeof syncLiveToolsFromToolTrace === 'function') syncLiveToolsFromToolTrace(j.tool_trace || []);
  // Remember this reply so the subsequent WS 'reply' event is deduped.
  if (typeof rememberLocalAgentReply === 'function') rememberLocalAgentReply(j.text || '');
  if (typeof markWsTextDone === 'function') markWsTextDone(sessionId);
  if (typeof markLiveProgressSeen === 'function') markLiveProgressSeen(sessionId);
  if (webuiSessionsEnabled) refreshSessionList().catch(function() {});
}

function handleWsReply(j) {
  if ((chatInflightBySid[sessionId] || 0) > 0) return;
  const t = normReply(j.text);
  if (!t) return;
  // 15s 内已收到相同正文（streaming 'text_done' 已写过）→ 去重
  if (t === lastLocalAgentReplyNorm && (Date.now() - lastLocalAgentReplyAt) < 15000) return;
  if (typeof bubbleAgentWithSplitToolTrace === 'function') {
    bubbleAgentWithSplitToolTrace(j.text || '', j.tool_trace || [], null, { at: Date.now() });
  } else {
    bubble('agent', j.text || '', { at: Date.now(), toolTrace: j.tool_trace || [] });
  }
  if (typeof recalcTokenUsageFromDom === 'function') recalcTokenUsageFromDom();
  if (webuiSessionsEnabled) refreshSessionList().catch(function() {});
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

// ── Compact 阈值输入框（tokens） ────────────────────────────
function initCompactMinInput() {
  var inp = document.getElementById('inpCompactMinTokens');
  if (!inp) return;
  // 加载当前值
  fetch('/api/ui/compact-config').then(r => r.json()).then(d => {
    if (d.compact_min_tokens > 0) inp.value = d.compact_min_tokens;
  }).catch(_ => {});
  // 变更时保存
  inp.addEventListener('change', function() {
    var val = parseInt(this.value, 10) || 0;
    fetch('/api/ui/compact-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ compact_min_tokens: val }),
      credentials: 'same-origin',
    }).catch(_ => {});
  });
}
// 页面加载完成后初始化
if (document.readyState === 'complete' || document.readyState === 'interactive') {
  setTimeout(initCompactMinInput, 500);
} else {
  document.addEventListener('DOMContentLoaded', function() { setTimeout(initCompactMinInput, 500); });
}
