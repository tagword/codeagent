/* ================================================================
 * 03-markdown.js
 *   - Markdown rendering, bubble builder, system messages
 *   - Tool call XML extraction / rendering
 *   - Links open in new tab
 * ================================================================ */

function ensureLinksOpenNewTab(el) {
  try {
    if (!el) return;
    const links = el.querySelectorAll ? el.querySelectorAll('a[href]') : [];
    links.forEach((a) => {
      try { a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noopener noreferrer'); } catch (_) {}
    });
  } catch (_) {}
}

// ── Streaming text update ──────────────────────────────────────────────
let _streamBubbleWrap = null; // holds the current streaming agent bubble
let _streamConsumedLen = 0;   // text offset — advanced ONLY at tool-start boundaries
let _streamLatestFullLen = 0; // length of the most recent full text seen (for split point)

function getOrCreateStreamBubble(at) {
  if (_streamBubbleWrap && _streamBubbleWrap.parentNode) {
    return _streamBubbleWrap;
  }
  _streamBubbleWrap = null;
  const wrap = document.createElement('div');
  wrap.className = 'msg-row msg-agent';
  const col = document.createElement('div');
  col.className = 'msg-col';
  const meta = document.createElement('div');
  meta.className = 'msg-meta';
  meta.textContent = '助手 · 输出中…';
  const b = document.createElement('div');
  b.className = 'bubble bubble-agent bubble-streaming';
  b.innerHTML = '<p><em>正在输出…</em></p>';
  col.appendChild(meta);
  col.appendChild(b);
  wrap.appendChild(col);
  log.appendChild(wrap);
  scrollLog();
  _streamBubbleWrap = wrap;
  return wrap;
}

/**
 * Return the portion of fullText starting from _streamConsumedLen.
 * Within a single round this returns the *full* text for that round
 * (so progressive text_delta events accumulate correctly).
 * Across rounds the offset prevents repeating earlier content.
 */
function _streamDeltaText(fullText) {
  const t = String(fullText || '');
  if (_streamConsumedLen <= 0 || _streamConsumedLen >= t.length) return t;
  return t.substring(_streamConsumedLen);
}

/** 仅返回尚未通过消费偏移写出的后缀；已全文应用则 ''（避免 REST/text_done 重复整段）。 */
function _streamUnconsumedSuffix(fullText) {
  const t = String(fullText || '');
  if (!t) return '';
  if (_streamConsumedLen <= 0) return t;
  if (_streamConsumedLen >= t.length) return '';
  return t.substring(_streamConsumedLen);
}

/**
 * Track the latest full-text length — does NOT advance _streamConsumedLen.
 * Used by splitStreamBubbleAtToolStart to know where the current round ends.
 */
function _noteStreamFullText(fullText) {
  const t = String(fullText || '');
  if (t.length > _streamLatestFullLen) _streamLatestFullLen = t.length;
}

/**
 * Advance _streamConsumedLen (for use in fallback handlers where we know
 * the text has been fully displayed and must not repeat).
 */
