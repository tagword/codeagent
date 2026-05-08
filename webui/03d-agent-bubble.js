function buildAgentBubbleInnerHtml(text, toolTrace, reasoningContent) {
  // 注意：toolTrace 参数不再内联渲染。工具链统一由 bubbleAgentWithSplitToolTrace
  // 或 appendAgentToolTraceRowToLog 渲染为独立块（系统消息样式），不与文本气泡混合。
  // 这样可以避免工具链在文本气泡内和独立块中重复展示两只。
  // reasoningContent 不展现给用户，仅用于 LLM 上下文恢复。
  let inner = '';
  const ex = extractOaToolCallBlocks(stripOaToolOrphans(normReply(text)));
  inner += renderMarkdown(ex.text);
  ex.blocks.forEach((blk, i) => {
    inner += oaToolDetailsHtml(blk, '内联工具调用' + (ex.blocks.length > 1 ? ' (' + (i + 1) + ')' : ''));
  });
  return inner;
}

function bubble(role, text, opts) {
  opts = opts || {};
  const at = opts.at;
  // Skip empty/whitespace-only agent bubbles (tool-only assistant messages should only render their tool blocks)
  if (role === 'agent' && !(text || '').trim()) {
    // Still render tool blocks if present
    const tt = Array.isArray(opts.toolTrace) ? opts.toolTrace : [];
    if (tt.length) {
      tt.forEach(function(row, i) {
        appendAgentToolTraceRowToLog(row, i, tt.length, { prepend: !!opts.prepend, skipScroll: true });
      });
    }
    if (!opts.skipScroll) scrollLog();
    return;
  }
  const wrap = document.createElement('div');
  wrap.className = 'msg-row msg-' + role;
  const col = document.createElement('div');
  col.className = 'msg-col';
  const meta = document.createElement('div');
  meta.className = 'msg-meta';
  const label = role === 'user' ? '你' : '助手';
  const ts = formatBubbleTime(at);
  meta.textContent = ts ? label + ' · ' + ts : label;
  const b = document.createElement('div');
  b.className = 'bubble bubble-' + role;
  if (role === 'agent') b.innerHTML = buildAgentBubbleInnerHtml(text, [], null);
  else b.innerHTML = renderMarkdown(normReply(text));
  ensureLinksOpenNewTab(b);
  col.appendChild(meta);
  col.appendChild(b);
  wrap.appendChild(col);
  if (opts.prepend && log.firstChild) {
    log.insertBefore(wrap, log.firstChild);
  } else {
    log.appendChild(wrap);
  }
  if (!opts.prepend && !opts.skipScroll) scrollLog();
  // 工具链渲染为独立块（不与文本气泡混合），避免重复展示
  if (role === 'agent') {
    const tt = Array.isArray(opts.toolTrace) ? opts.toolTrace : [];
    if (opts.prepend) {
      // 预置（加载旧历史）时：工具块应插入到文本气泡之后、原 log 最前内容之前
      // 逐个 prepend 会反转顺序，故从后向前遍历以保持正序
      for (var i = tt.length - 1; i >= 0; i--) {
        appendAgentToolTraceRowToLog(tt[i], i, tt.length, { prepend: true, skipScroll: true });
      }
    } else {
      tt.forEach(function(row, i) {
        appendAgentToolTraceRowToLog(row, i, tt.length, { skipScroll: true });
      });
    }
  }
}
