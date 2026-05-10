function _advanceStreamConsumedLen(fullText) {
  const t = String(fullText || '');
  if (t.length > _streamConsumedLen) _streamConsumedLen = t.length;
  if (t.length > _streamLatestFullLen) _streamLatestFullLen = t.length;
}

function updateStreamBubbleText(fullText) {
  // Don't create/render streaming bubbles for whitespace-only content
  if (!(fullText || '').trim()) {
    // If a streaming bubble was already created, remove it
    if (_streamBubbleWrap && _streamBubbleWrap.parentNode) {
      _streamBubbleWrap.parentNode.removeChild(_streamBubbleWrap);
    }
    _streamBubbleWrap = null;
    _streamConsumedLen = 0;
    _streamLatestFullLen = 0;
    return;
  }
  const wrap = getOrCreateStreamBubble(Date.now());
  if (!wrap) return;
  const b = wrap.querySelector('.bubble');
  if (!b) return;
  // Show text from round-start to current (incremental build-up within round)
  const roundText = _streamDeltaText(fullText);
  _noteStreamFullText(fullText); // record length for split, do NOT advance consumed
  if (!roundText && !_streamConsumedLen) return;
  try {
    b.innerHTML = buildAgentBubbleInnerHtml(roundText, [], null);
    ensureLinksOpenNewTab(b);
  } catch (_) {
    b.textContent = roundText;
  }
  scrollLog();
}

/**
 * Finalize the streaming bubble (remove streaming-indicator, render final content).
 * Returns the bubble wrap element or null.
 */
/** 结束流式气泡；工具不在气泡内合并（时间轴拆分）。第二个参数保留以兼容旧调用，已忽略。 */
function finalizeStreamBubble(text, _toolTrace) {
  const wrap = _streamBubbleWrap;
  _streamBubbleWrap = null;
  if (!wrap || !wrap.parentNode) return null;
  const b = wrap.querySelector('.bubble');
  if (!b) return null;
  // Remove whitespace-only bubbles
  if (!(text || '').trim()) {
    wrap.parentNode.removeChild(wrap);
    _streamConsumedLen = 0;
    _streamLatestFullLen = 0;
    return null;
  }
  b.classList.remove('bubble-streaming');
  const roundText = _streamDeltaText(text);
  _noteStreamFullText(text); // record length, do NOT advance consumed
  try {
    // 时间轴拆分：正文只在气泡内，工具由独立 system-tools 块展示（与 transcript 一致）
    b.innerHTML = buildAgentBubbleInnerHtml(roundText || '', [], null);
    ensureLinksOpenNewTab(b);
  } catch (_) {
    b.textContent = roundText || '';
  }
  const meta = wrap.querySelector('.msg-meta');
  if (meta) {
    const ts = formatBubbleTime(Date.now());
    meta.textContent = ts ? '助手 · ' + ts : '助手';
  }
  scrollLog();
  return wrap;
}

/**
 * Split the streaming bubble at the current point.
 * Called when a tool_start WS event arrives — the current round's text
 * is finalized; offsets reset because each LLM round sends a fresh string
 * (not cumulative across tool rounds).
 */
function splitStreamBubbleAtToolStart() {
  var wrap = _streamBubbleWrap;
  if (wrap && wrap.parentNode) {
    var b = wrap.querySelector('.bubble');
    if (b) {
      var txt = '';
      try {
        txt = (b.textContent || '').trim();
      } catch (_) {}
      var placeholderish = !txt || /^正在输出/.test(txt);
      if (placeholderish) {
        try {
          wrap.parentNode.removeChild(wrap);
        } catch (_) {}
      } else {
        b.classList.remove('bubble-streaming');
        var meta = wrap.querySelector('.msg-meta');
        if (meta) {
          var ts = formatBubbleTime(Date.now());
          meta.textContent = ts ? '助手 · ' + ts : '助手';
        }
      }
    }
  }
  _streamBubbleWrap = null;
  _streamConsumedLen = 0;
  _streamLatestFullLen = 0;
  scrollLog();
}
