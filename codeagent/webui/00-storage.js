/* ================================================================
 * 00-storage.js
 *   localStorage / sessionStorage 集中封装。
 *
 *   历史：localStorage key 字符串散落在 8+ 个文件共 30+ 处，try/catch
 *   防护重复 ~30 次。重命名风险高。
 *
 *   本文件：
 *     1) STORAGE_KEYS — 唯一 key 来源（按用途分组）
 *     2) getLS/setLS/removeLS/tryGetLS/trySetLS — 集中 try/catch
 *        （getLS 返回 null 表示 key 缺失或 quota 等异常，不再抛）
 *
 *   按字母序：00-storage.js 排在 00-utils.js 之前。
 *   （'00-storage' < '00-utils'：'-' ASCII 45 < 'u' ASCII 117）
 * ================================================================ */

/** 所有 storage key 的单一来源。 */
const STORAGE_KEYS = Object.freeze({
  // ── 思考 / 推理 ──
  ENABLE_THINKING: 'oa_enable_thinking',
  REASONING_EFFORT: 'oa_reasoning_effort',
  // ── 会话身份 ──
  SESS_LAST_READ: 'oa_sess_last_read_v2',
  SESS_COMPLETED: 'oaSessionCompletedMap',
  SESS_ACTIVE_PAGE: 'oa_active_page',
  SESS_ACTIVITY_MODE: 'oa_activity_mode',
  // ── 模型选择（旧 fallback） ──
  LLM_PRESET_ID: 'oa_llm_preset_id',
  // ── 一次性 flag ──
  SETUP_GREETED: 'oa_setup_greeted',
  // ── 面板显隐 ──
  TODO_PANEL_OPEN: 'oa_todo_panel_open',
  PLAN_PANEL_OPEN: 'oa_plan_panel_open',
  GIT_PANEL_OPEN: 'oa_git_panel_open',
  // ── Todo 列表 scope ──
  TODO_SCOPE: 'oa_todo_scope',
  // ── WS 凭据（sessionStorage） ──
  WS_TOKEN: 'oa_webui_ws_token',
});

/** 动态 key 构造器（agent/session 作用域）。 */
function sidStorageKey(aid, pid) {
  // 历史：oa_sid_v5_<aid>_<pid>，_pid 部分做尾部归一化（空/null/legacy）
  const a = String(aid || 'default');
  const p = String(pid == null ? '' : pid).trim();
  return 'oa_sid_v5_' + a + (p ? '_' + p : '');
}
function projectStorageKey(aid) {
  return 'oa_proj_' + String(aid || 'default');
}

/** 读取：异常或缺失 → fallback（默认 ''）。 */
function tryGetLS(key, fallback) {
  try { return localStorage.getItem(key) || fallback || ''; }
  catch (_) { return fallback || ''; }
}
/** 写入：quota 满等异常静默吞掉。 */
function trySetLS(key, val) {
  try { localStorage.setItem(key, String(val == null ? '' : val)); return true; }
  catch (_) { return false; }
}
/** 删除：缺失也安全。 */
function tryRemoveLS(key) {
  try { localStorage.removeItem(key); return true; }
  catch (_) { return false; }
}

/** 同上但走 sessionStorage（WS token 等短生命周期）。 */
function tryGetSS(key, fallback) {
  try { return sessionStorage.getItem(key) || fallback || ''; }
  catch (_) { return fallback || ''; }
}
function trySetSS(key, val) {
  try { sessionStorage.setItem(key, String(val == null ? '' : val)); return true; }
  catch (_) { return false; }
}
function tryRemoveSS(key) {
  try { sessionStorage.removeItem(key); return true; }
  catch (_) { return false; }
}
