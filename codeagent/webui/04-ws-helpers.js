/* ================================================================
 * 04-websocket.js
 *   - WebSocket connection management (connectWs, reconnectWsForSession)
 *   - Live tool event stream (liveToolBlocks, handleProgressEvent)
 *   - WS flag check
 * ================================================================ */

let ws;
let wsReconnectTimer = null;
let pauseWsReconnect = false;

const liveToolBlocks = new Map();
const liveProgressSeenBySid = Object.create(null);
const wsTextDoneBySid = Object.create(null);

function markLiveProgressSeen(sid) {
  if (!sid) return;
  liveProgressSeenBySid[sid] = true;
}
function consumeLiveProgressSeen(sid) {
  const v = !!liveProgressSeenBySid[sid];
  delete liveProgressSeenBySid[sid];
  return v;
}
/** WS 已发过 text_done（本轮助手输出已由 WS 收尾），HTTP /api/chat 不应再画一遍正文 */
function markWsTextDone(sid) {
  if (sid) wsTextDoneBySid[String(sid)] = true;
}
function consumeWsTextDone(sid) {
  const k = String(sid || '');
  const v = !!wsTextDoneBySid[k];
  delete wsTextDoneBySid[k];
  return v;
}

function ensureLiveToolBlock(evt) {
  const id = String((evt && evt.event_id) || '');
  if (!id) return null;
  let row = liveToolBlocks.get(id);
  if (row) return row;
  const typ = String((evt && evt.type) || '');
  const running = typ !== 'tool_end';
  const wrap = appendAgentToolTraceRowToLog(
    {
      tool: String((evt && evt.tool) || 'tool'),
      arguments: String((evt && evt.arguments) || ''),
      result: String((evt && evt.result) || ''),
    },
    0,
    1,
    { running: running, skipScroll: true, hideIndex: true }
  );
  try {
    wrap.dataset.oaEventId = id;
  } catch (_) {}
  const pre = wrap.querySelector('.oa-tool-trace-pre');
  const title = wrap.querySelector('.oa-live-tool-title');
  row = { wrap: wrap, title: title, pre: pre, hasOutput: false };
  liveToolBlocks.set(id, row);
  scrollLog();
  return row;
}

function appendLiveToolOutput(evt) {
  const row = ensureLiveToolBlock(evt);
  if (!row) return;
  const text = String((evt && evt.text) || '');
  if (!text) return;
  if (!row.title.textContent) {
    try { const tool = String((evt && evt.tool) || 'tool'); row.title.textContent = '执行中：' + tool; } catch (_) {}
  }
  row.hasOutput = true;
  row.pre.textContent += text;
  scrollLog();
}

function handleProgressEvent(evt) {
  const t = String((evt && evt.type) || '');
  if (!t) return;
  markLiveProgressSeen(sessionId);
  if (t === 'tool_start') {
    // ── Split streaming bubble at tool boundary ──────────────────────
    // If the agent was still speaking, finalize that speech segment so
    // the next text_delta creates a fresh bubble (instead of appending
    // all rounds into one bubble).
    if (typeof splitStreamBubbleAtToolStart === 'function') {
      splitStreamBubbleAtToolStart();
    }
    // ── Create / update live tool block ──────────────────────────────
    const row = ensureLiveToolBlock(evt);
    if (!row) return;
    const args = String((evt && evt.arguments) || '');
    if (args) row.pre.textContent = '参数：\n' + args + '\n';
    scrollLog();
    return;
  }
  if (t === 'tool_output') { appendLiveToolOutput(evt); return; }
  if (t === 'tool_end') {
    const row = ensureLiveToolBlock(evt);
    if (!row) return;
    const tool = String((evt && evt.tool) || 'tool');
    if (typeof updateTimelineToolRowElement === 'function') {
      updateTimelineToolRowElement(row.wrap, {
        tool: tool,
        arguments: String((evt && evt.arguments) || ''),
        result: String((evt && evt.result) || ''),
      }, 0, 1);
    }
    liveToolBlocks.delete(String((evt && evt.event_id) || ''));
    // Auto-refresh todo panel when todo_tool finishes
    if (tool === 'todo_tool' && typeof refreshTodos === 'function' && typeof todoIsVisible === 'function' && todoIsVisible()) {
      refreshTodos();
    }
    scrollLog();
  }
}
