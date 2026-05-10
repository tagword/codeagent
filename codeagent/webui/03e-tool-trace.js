/**
 * 时间轴上的单条工具记录（与 transcript / WS 实时共用 DOM 结构）。
 * @param {object} row { tool, arguments, result }
 * @param {number} index
 * @param {number} total
 * @param {{prepend?:boolean,skipScroll?:boolean,running?:boolean,hideIndex?:boolean}} opts
 * @returns {HTMLDetailsElement}
 */
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

  if (opts.prepend && log.firstChild) {
    log.insertBefore(wrap, log.firstChild);
  } else {
    log.appendChild(wrap);
  }
  if (!opts.skipScroll) scrollLog();
  return wrap;
}

/** 用服务端 tool_trace 覆盖/补齐当前 log 内的时间轴工具块（与 WS 块对齐）。
 * 自动清理多余旧块（防重），确保最终 log 中工具块数 === toolTrace.length。 */
function syncLiveToolsFromToolTrace(toolTrace) {
  if (typeof log === 'undefined' || !log) return;
  const tt = Array.isArray(toolTrace) ? toolTrace : [];
  // 收集当前所有工具块
  const all = [];
  try {
    log.querySelectorAll('details.system-msg.system-tools.oa-live-tool').forEach(function(n) {
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
  const spin = detailsEl.querySelector('.oa-live-tool-spinner');
  if (spin && spin.parentNode) spin.parentNode.removeChild(spin);
}
