/* ================================================================
 * 01c-session-identity.js
 *   Session/agent identity：当前 agentId / projectId / sessionId 三元组
 *   的状态、localStorage 持久化、URL/project 查询参数构造。
 *
 *   依赖 00-storage.js (STORAGE_KEYS)。
 *   顶层声明顺序：先 helper function（被 loadXxx 引用），再状态变量。
 *   实际加载靠 var/function hoisting 跨文件安全。
 * ================================================================ */

const READ_KEY = STORAGE_KEYS.SESS_LAST_READ;
let lastSessionsCache = [];
let webuiSessionsEnabled = false;
var agentId = 'default';

/** RFC4122 v4；在 HTTP 或非 Chromium 旧版等环境下 crypto.randomUUID 可能不存在。 */
function oaRandomUUID() {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch (_) {}
  // Math.random fallback：拼 v4 格式（4/-/位标志位）
  var bytes = new Array(16);
  for (var i = 0; i < 16; i++) bytes[i] = (Math.random() * 256) | 0;
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10
  var hex = '';
  for (var j = 0; j < 16; j++) hex += (bytes[j] + 0x100).toString(16).slice(1);
  return (
    hex.slice(0, 8) + '-' +
    hex.slice(8, 12) + '-' +
    hex.slice(12, 16) + '-' +
    hex.slice(16, 20) + '-' +
    hex.slice(20)
  );
}

function projectStorageKey(aid) {
  return 'oa_proj_' + String(aid || 'default');
}
function loadProjectIdForAgent(aid) {
  try { return localStorage.getItem(projectStorageKey(aid)) || ''; } catch (_) { return ''; }
}
function saveProjectIdForAgent(aid, pid) {
  try { localStorage.setItem(projectStorageKey(aid), String(pid || '').trim()); } catch (_) {}
}

let projectId = loadProjectIdForAgent(agentId);

let historyFirstBlockIndex = null;
let historyHasMoreOlder = false;
let historyLoadingOlder = false;
let historyScrollTimer = null;
let historyPagingBound = false;

function _sidStorageKey(aid, pid) {
  const a = String(aid || 'default');
  const p = String(pid == null ? '' : pid).trim();
  return 'oa_sid_v5_' + a + (p ? '_' + p : '');
}
function loadSessionIdForAgent(aid, pid) {
  const p = String(pid || '').trim();
  const key = _sidStorageKey(aid, p);
  let sid = localStorage.getItem(key) || '';
  if (!sid && !p) {
    const legacy = localStorage.getItem('oa_sid_' + String(aid || 'default')) || '';
    if (legacy) { sid = legacy; localStorage.setItem(key, sid); }
  }
  if (!sid) { sid = oaRandomUUID(); localStorage.setItem(key, sid); }
  return sid;
}
function saveSessionIdForAgent(aid, pid, sid) {
  try {
    localStorage.setItem(_sidStorageKey(aid, pid), String(sid || '').trim());
  } catch (_) {}
}

function projectQuerySuffix() {
  return '&project_id=' + encodeURIComponent(projectId || '');
}
