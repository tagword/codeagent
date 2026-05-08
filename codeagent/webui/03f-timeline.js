/**
 * 渲染助手消息，但将 toolTrace 中的每个工具调用渲染为独立元素，
 * 而不是全部塞在一个气泡里。用于转录加载时保持与实时执行一致的展示。
 */
function bubbleAgentWithSplitToolTrace(text, toolTrace, reasoningContent, opts) {
  opts = opts || {};
  const at = opts.at;
  const tt = Array.isArray(toolTrace) ? toolTrace : [];

  // 1. 文本内容气泡（reasoning_content 不展现给用户）
  const cleanText = stripOaToolOrphans(normReply(text || ''));
  if (cleanText) {
    const wrap = document.createElement('div');
    wrap.className = 'msg-row msg-agent';
    const col = document.createElement('div');
    col.className = 'msg-col';
    const meta = document.createElement('div');
    meta.className = 'msg-meta';
    const label = '助手';
    const ts = formatBubbleTime(at);
    meta.textContent = ts ? label + ' · ' + ts : label;
    const b = document.createElement('div');
    b.className = 'bubble bubble-agent';
    b.innerHTML = renderMarkdown(cleanText);
    ensureLinksOpenNewTab(b);
    col.appendChild(meta);
    col.appendChild(b);
    wrap.appendChild(col);
    if (opts.prepend && log.firstChild) {
      log.insertBefore(wrap, log.firstChild);
    } else {
      log.appendChild(wrap);
    }
  }

  // 3. 每个工具调用独立渲染（与 WS 实时 appendAgentToolTraceRowToLog 一致）
  tt.forEach(function(row, i) {
    appendAgentToolTraceRowToLog(row, i, tt.length, { prepend: !!opts.prepend, skipScroll: true });
  });

  if (!opts.skipScroll && !opts.prepend) scrollLog();
}

function systemMsg(kind, text, opts) {
  opts = opts || {};
  const d = document.createElement('div');
  d.className = 'system-msg system-' + kind;
  d.textContent = text;
  log.appendChild(d);
  if (!opts.skipScroll) scrollLog();
}
