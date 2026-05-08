/* ================================================================
 * 02-session-ui.js
 *   - Unread count bookkeeping (localStorage map)
 *   - Session list item rendering (buildSessListItem)
 *   - Session list DOM helpers (highlight, running state)
 *   - Session operations (archive, delete, copy-id)
 * ================================================================ */

// ---------------- Unread count bookkeeping ----------------

function getReadMap() {
  try {
    const o = JSON.parse(localStorage.getItem(READ_KEY) || '{}');
    return o && typeof o === 'object' ? o : {};
  } catch (_) { return {}; }
}
function saveReadMap(m) {
  localStorage.setItem(READ_KEY, JSON.stringify(m));
}
function ensureReadBaseline(rows) {
  const m = getReadMap();
  let ch = false;
  (rows || []).forEach((r) => {
    const sid = r.session_id;
    if (sid && !Object.prototype.hasOwnProperty.call(m, sid)) {
      m[sid] = r.message_count || 0;
      ch = true;
    }
  });
  if (ch) saveReadMap(m);
}
function markSessionReadByCount(sid, count) {
  const m = getReadMap();
  m[sid] = count;
  saveReadMap(m);
}
function unreadCountFor(row) {
  if (row && row.session_id === sessionId) return 0;
  const m = getReadMap();
  const mc = row.message_count || 0;
  if (!Object.prototype.hasOwnProperty.call(m, row.session_id)) return 0;
  return Math.max(0, mc - m[row.session_id]);
}
function removeSessionReadBaseline(sid) {
  const m = getReadMap();
  delete m[sid];
  saveReadMap(m);
}
function updateMainHeaderForSession(sid) {
  const titleEl = document.getElementById('currentConvTitle');
  const chEl = document.getElementById('currentConvChannel');
  if (!titleEl || !chEl) return;
  const row = lastSessionsCache.find((r) => r.session_id === sid);
  if (row) {
    titleEl.textContent = row.display_title || '对话';
    chEl.textContent = row.channel || 'Web 聊天';
  } else {
    titleEl.textContent = '新对话';
    chEl.textContent = 'Web 聊天';
  }
}
function orderSessionsWithPinFirst(sessions, pinSid) {
  const pin = String(pinSid || '');
  if (!pin || !sessions || !sessions.length) return (sessions || []).slice();
  const next = sessions.slice();
  const idx = next.findIndex((r) => r.session_id === pin);
  if (idx > 0) { const [hit] = next.splice(idx, 1); next.unshift(hit); }
  return next;
}
function highlightSessList(sid) {
  document.querySelectorAll('#sessList .sess-row').forEach((el) => {
    el.classList.toggle('is-active', el.getAttribute('data-session-id') === sid);
  });
  applyAllSessionRunningStates();
}
function applySessionRunningState(sid) {
  const k = String(sid || '');
  if (!k) return;
  const active = (chatInflightBySid[k] || 0) > 0;
  // 更新侧边栏列表
  const rows = document.querySelectorAll('#sessList .sess-row[data-session-id="' + CSS.escape(k) + '"]');
  rows.forEach((el) => el.classList.toggle('is-running', active));
  // 更新树状视图
  const treeSessions = document.querySelectorAll('.tree-session[data-session-id="' + CSS.escape(k) + '"]');
  treeSessions.forEach((el) => el.classList.toggle('is-running', active));
  // 更新当前会话的 body 标记
  if (typeof sessionId !== 'undefined' && k === String(sessionId)) {
    try { document.body.classList.toggle('chat-running', active); } catch (_) {}
  }
}
function applyAllSessionRunningStates() {
  try {
    const all = new Set(Object.keys(chatInflightBySid));
    if (typeof sessionId !== 'undefined' && sessionId) all.add(String(sessionId));
    all.forEach(applySessionRunningState);
  } catch (_) {}
}

// ---------------- Session list item rendering ----------------

function buildSessListItem(row) {
  const wrap = document.createElement('div');
  wrap.className = 'sess-row';
  wrap.setAttribute('data-session-id', row.session_id);
  // 检查初始运行状态
  if (typeof chatInflightBySid !== 'undefined' && (chatInflightBySid[row.session_id] || 0) > 0) {
    wrap.classList.add('is-running');
  }

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'sess-item-main';
  btn.setAttribute('data-session-id', row.session_id);
  btn.setAttribute('role', 'option');
  const dot = document.createElement('span');
  dot.className = 'sess-item__channel-dot';
  dot.setAttribute('aria-hidden', 'true');
  const body = document.createElement('div');
  body.className = 'sess-item__body';
  const title = document.createElement('div');
  title.className = 'sess-item__title';
  title.textContent = row.display_title || '未命名对话';
  const sub = document.createElement('div');
  sub.className = 'sess-item__sub';
  sub.textContent = (row.channel || '') + ' · ' + (row.message_count || 0) + ' 条';
  body.appendChild(title);
  body.appendChild(sub);
  const badge = document.createElement('span');
  badge.className = 'sess-item__badge';
  const un = unreadCountFor(row);
  if (un <= 0) badge.hidden = true;
  else badge.textContent = un > 99 ? '99+' : String(un);
  btn.appendChild(dot);
  btn.appendChild(body);
  btn.appendChild(badge);

  const opWrap = document.createElement('div');
  opWrap.className = 'sess-item__op-wrap';
  const trig = document.createElement('button');
  trig.type = 'button';
  trig.className = 'sess-item__op-trigger';
  trig.setAttribute('aria-label', '会话操作');
  trig.setAttribute('aria-haspopup', 'true');
  trig.textContent = '\u22EE';
  const menu = document.createElement('div');
  menu.className = 'sess-item__menu';
  menu.setAttribute('role', 'menu');
  const bCopyId = document.createElement('button');
  bCopyId.type = 'button';
  bCopyId.setAttribute('data-sess-act', 'copy-id');
  bCopyId.setAttribute('role', 'menuitem');
  bCopyId.textContent = '复制会话 ID';
  const bArch = document.createElement('button');
  bArch.type = 'button';
  bArch.setAttribute('data-sess-act', 'archive');
  bArch.setAttribute('role', 'menuitem');
  bArch.textContent = '归档';
  const bDel = document.createElement('button');
  bDel.type = 'button';
  bDel.setAttribute('data-sess-act', 'delete');
  bDel.setAttribute('role', 'menuitem');
  bDel.className = 'sess-item__menu-danger';
  bDel.textContent = '删除';
  menu.appendChild(bCopyId);
  menu.appendChild(bArch);
  menu.appendChild(bDel);
  opWrap.appendChild(trig);
  opWrap.appendChild(menu);
  wrap.appendChild(btn);
  wrap.appendChild(opWrap);
  return wrap;
}
