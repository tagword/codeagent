/* ================================================================
 * 01c-session-thinking.js
 *   思考模式 + 推理强度（DeepSeek 思考模式等）的持久化与 UI 同步。
 *   依赖：00-storage.js (STORAGE_KEYS)。
 *   依赖全局 DOM 元素：thinkToggle, reasoningEffortSelect（在 body.html 顶部）。
 * ================================================================ */

const THINK_KEY = STORAGE_KEYS.ENABLE_THINKING;
const REASONING_EFFORT_KEY = STORAGE_KEYS.REASONING_EFFORT;

function getThinkState() {
  try {
    const v = localStorage.getItem(THINK_KEY);
    if (v === null) return true;
    return v === '1';
  } catch (_) { return true; }
}
function getReasoningEffort() {
  try {
    const v = localStorage.getItem(REASONING_EFFORT_KEY);
    return v === 'max' ? 'max' : 'high';
  } catch (_) { return 'high'; }
}
function syncReasoningEffortUi() {
  const on = getThinkState();
  if (reasoningEffortSelect) {
    reasoningEffortSelect.disabled = !on;
    reasoningEffortSelect.value = getReasoningEffort();
    reasoningEffortSelect.title = on
      ? '推理强度（DeepSeek 思考模式）：高 = reasoning_effort high，最高 = max'
      : '开启「思考」后可选择推理强度';
  }
}
function setThinkState(on) {
  try { localStorage.setItem(THINK_KEY, on ? '1' : '0'); } catch (_) {}
  if (thinkToggle) {
    thinkToggle.setAttribute('aria-pressed', on ? 'true' : 'false');
    thinkToggle.title = on
      ? '思考：已开启。模型会先思考再回答（慢但更准）。点击关闭。'
      : '思考：已关闭。模型直接回答（更快）。点击开启。';
  }
  syncReasoningEffortUi();
}
function setReasoningEffort(val) {
  const effort = val === 'max' ? 'max' : 'high';
  try { localStorage.setItem(REASONING_EFFORT_KEY, effort); } catch (_) {}
  syncReasoningEffortUi();
}
if (thinkToggle) {
  setThinkState(getThinkState());
  thinkToggle.addEventListener('click', function(e) {
    e.stopPropagation();
    setThinkState(!getThinkState());
  });
}
if (reasoningEffortSelect) {
  syncReasoningEffortUi();
  reasoningEffortSelect.addEventListener('change', () => {
    setReasoningEffort(reasoningEffortSelect.value);
  });
}
