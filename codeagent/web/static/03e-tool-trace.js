/**
 * 时间轴上的单条工具记录（与会话历史 / WS 实时共用 DOM 结构）。
 * @param {object} row { tool, arguments, result }
 * @param {number} index
 * @param {number} total
 * @param {{prepend?:boolean,skipScroll?:boolean,running?:boolean,hideIndex?:boolean}} opts
 * @returns {HTMLDetailsElement}
 */

// ── 工具组折叠容器 ─────────────────────────────────────────────
// 同一轮助手回复的所有工具调用，折叠到一个 <details.oa-tool-group> 中。
// WS 流式渲染过程中持续追加到当前组，直到下一轮 run_started 重置。

let _currentToolGroup = null;

/** 重置工具组（下一轮助手回复开始前调用）。 */
function resetToolGroup() {
  _currentToolGroup = null;
}

/** 获取当前工具组容器。不存在则创建（尚未插入 DOM，由调用者插入）。 */
function _ensureToolGroup() {
  if (!_currentToolGroup || !_currentToolGroup.parentNode) {
    _currentToolGroup = document.createElement('details');
    _currentToolGroup.className = 'oa-tool-group';
    const summary = document.createElement('summary');
    summary.className = 'oa-tool-group-summary';
    summary.textContent = '\uD83D\uDD27 工具调用';
    _currentToolGroup.appendChild(summary);
  }
  return _currentToolGroup;
}

/** 更新当前组 label 中的工具数量。 */
function _updateToolGroupLabel() {
  if (!_currentToolGroup) return;
  const count = _currentToolGroup.querySelectorAll('details.system-msg.system-tools.oa-live-tool').length;
  const summary = _currentToolGroup.querySelector('.oa-tool-group-summary');
  if (summary) summary.textContent = '\uD83D\uDD27 工具调用 (' + count + ')';
}

// ── 工具行渲染 ─────────────────────────────────────────────────

/**
 * Render thumbnail previews for image_generate tool results inside a tool trace row.
 */
function appendGeneratedImagesToToolRow(detailsEl, row) {
  if (!detailsEl || !row) return;
  const name = (row.tool || row.name || '').toLowerCase();
  if (name !== 'image_generate') return;
  let payload = null;
  try {
    payload = JSON.parse(String(row.result || ''));
  } catch (_) {
    return;
  }
  const images = payload && payload.images;
  if (!Array.isArray(images) || !images.length) return;
  detailsEl.querySelectorAll('.oa-tool-gen-images').forEach(function(n) { n.remove(); });
  const wrap = document.createElement('div');
  wrap.className = 'oa-tool-gen-images';
  images.forEach(function(img) {
    if (!img || !img.attachment_id) return;
    const el = document.createElement('img');
    el.className = 'chat-inline-img bubble-user__img';
    el.alt = img.filename || 'generated';
    el.src = '/api/attachments/' + encodeURIComponent(img.attachment_id)
      + '?session_id=' + encodeURIComponent(typeof sessionId !== 'undefined' ? sessionId : 'web-chat')
      + '&agent_id=' + encodeURIComponent(typeof agentId !== 'undefined' ? agentId : 'default');
    wrap.appendChild(el);
  });
  if (wrap.childNodes.length) {
    detailsEl.appendChild(wrap);
    if (typeof enhanceChatImagesInBubble === 'function') enhanceChatImagesInBubble(wrap);
  }
}

function appendGeneratedMusicToToolRow(detailsEl, row) {
  if (!detailsEl || !row) return;
  const name = (row.tool || row.name || '').toLowerCase();
  if (name !== 'music_generate') return;
  let payload = null;
  try {
    payload = JSON.parse(String(row.result || ''));
  } catch (_) {
    return;
  }
  const audio = payload && payload.audio;
  if (!audio || !audio.attachment_id) return;
  detailsEl.querySelectorAll('.oa-tool-gen-audio').forEach(function(n) { n.remove(); });
  const wrap = document.createElement('div');
  wrap.className = 'oa-tool-gen-audio';
  const el = document.createElement('audio');
  el.controls = true;
  el.preload = 'metadata';
  el.src = '/api/attachments/' + encodeURIComponent(audio.attachment_id)
    + '?session_id=' + encodeURIComponent(typeof sessionId !== 'undefined' ? sessionId : 'web-chat')
    + '&agent_id=' + encodeURIComponent(typeof agentId !== 'undefined' ? agentId : 'default');
  wrap.appendChild(el);
  detailsEl.appendChild(wrap);
}

function appendGeneratedVideoToToolRow(detailsEl, row) {
  if (!detailsEl || !row) return;
  const name = (row.tool || row.name || '').toLowerCase();
  if (name !== 'video_generate') return;
  let payload = null;
  try {
    payload = JSON.parse(String(row.result || ''));
  } catch (_) {
    return;
  }
  const video = payload && payload.video;
  if (!video || !video.attachment_id) return;
  detailsEl.querySelectorAll('.oa-tool-gen-video').forEach(function(n) { n.remove(); });
  const wrap = document.createElement('div');
  wrap.className = 'oa-tool-gen-video';
  const el = document.createElement('video');
  el.controls = true;
  el.preload = 'metadata';
  el.src = '/api/attachments/' + encodeURIComponent(video.attachment_id)
    + '?session_id=' + encodeURIComponent(typeof sessionId !== 'undefined' ? sessionId : 'web-chat')
    + '&agent_id=' + encodeURIComponent(typeof agentId !== 'undefined' ? agentId : 'default');
  wrap.appendChild(el);
  detailsEl.appendChild(wrap);
}

function appendAgentToolTraceRowToLog(row, index, total, opts) {
  opts = opts || {};
  const name = (row && (row.tool || row.name)) || 'tool';
  const args = row && row.arguments != null ? String(row.arguments) : '';
  const res = row && row.result != null ? String(row.result) : '';
  const running = !!opts.running;
  const showIdx = total > 1 && !opts.hideIndex;
  const suffix = showIdx ? ' (' + (index + 1) + ')' : '';

  const wrap = document.createElement('details');
  wrap.className = 'system-msg system-tools oa-live-tool';
  if (running) wrap.classList.add('is-running');

  const summary = document.createElement('summary');
  summary.className = 'oa-live-tool-summary';
  if (running) {
    const spinner = document.createElement('span');
    spinner.className = 'oa-live-tool-spinner';
    spinner.setAttribute('aria-hidden', 'true');
    summary.appendChild(spinner);
  }
  const label = document.createElement('span');
  label.className = 'oa-live-tool-label oa-live-tool-title';
  label.textContent = (running ? '执行中：' : '已完成：') + name + suffix;
  summary.appendChild(label);

  const pre = document.createElement('pre');
  pre.className = 'oa-tool-trace-pre';
  if (running) {
    pre.textContent = args ? '参数：\n' + args + '\n' : '';
  } else {
    pre.textContent = '参数：\n' + args + '\n\n输出：\n' + res;
  }
  wrap.appendChild(summary);
  wrap.appendChild(pre);

  appendGeneratedImagesToToolRow(wrap, row);
  appendGeneratedMusicToToolRow(wrap, row);
  appendGeneratedVideoToToolRow(wrap, row);

  // ── 放入工具组容器（而非直接 append 到 #log） ─────────────
  const group = _ensureToolGroup();
  // 首次创建时将组插入 log
  if (!group.parentNode) {
    if (opts.prepend && log.firstChild) {
      log.insertBefore(group, log.firstChild);
    } else {
      log.appendChild(group);
    }
  }
  group.appendChild(wrap);
  _updateToolGroupLabel();

  if (!opts.skipScroll) scrollLog();
  return wrap;
}

/** 用服务端 tool_trace 覆盖/补齐当前 log 内的时间轴工具块（与 WS 块对齐）。
 * 自动清理多余旧块（防重），确保最终 log 中工具块数 === toolTrace.length。 */
function syncLiveToolsFromToolTrace(toolTrace) {
  if (typeof log === 'undefined' || !log) return;
  const tt = Array.isArray(toolTrace) ? toolTrace : [];
  // 收集当前组内所有工具块
  const group = _ensureToolGroup();
  const all = [];
  try {
    group.querySelectorAll('details.system-msg.system-tools.oa-live-tool').forEach(function(n) {
      all.push(n);
    });
  } catch (_) {}
  // 清理多余旧块：保留最后 tt.length 个，移除前面的
  if (all.length > tt.length) {
    const removeCount = all.length - tt.length;
    all.slice(0, removeCount).forEach(function(n) {
      try { n.parentNode.removeChild(n); } catch (_) {}
    });
    var kept = all.slice(removeCount);
  } else {
    var kept = all.slice();
  }
  // 更新/补齐
  for (var i = 0; i < tt.length; i++) {
    if (i < kept.length) {
      updateTimelineToolRowElement(kept[i], tt[i], i, tt.length);
    } else {
      appendAgentToolTraceRowToLog(tt[i], i, tt.length, { skipScroll: true });
    }
  }
  _updateToolGroupLabel();
  scrollLog();
}

function updateTimelineToolRowElement(detailsEl, row, index, total) {
  if (!detailsEl || !row) return;
  detailsEl.classList.remove('is-running');
  const name = (row && (row.tool || row.name)) || 'tool';
  const args = row && row.arguments != null ? String(row.arguments) : '';
  const res = row && row.result != null ? String(row.result) : '';
  const title = detailsEl.querySelector('.oa-live-tool-title');
  if (title) {
    const suffix = total > 1 ? ' (' + (index + 1) + ')' : '';
    title.textContent = '已完成：' + name + suffix;
  }
  const pre = detailsEl.querySelector('.oa-tool-trace-pre');
  if (pre) pre.textContent = '参数：\n' + args + '\n\n输出：\n' + res;
  appendGeneratedImagesToToolRow(detailsEl, row);
  const spin = detailsEl.querySelector('.oa-live-tool-spinner');
  if (spin && spin.parentNode) spin.parentNode.removeChild(spin);
}
