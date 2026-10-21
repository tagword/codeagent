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
// 推理强度档位：DeepSeek 仅 high|max（API 不读 reasoning_effort，仅作 UI hint）；
// MiniMax-M3.1-Flash-Preview 支持 low|medium|high|xhigh|max；其他 MiniMax 模型档位无效。
// '' 表示「未指定」——后端不发 reasoning_effort 字段，模型自选档位。
const REASONING_EFFORTS = ['', 'low', 'medium', 'high', 'xhigh', 'max'];
function getReasoningEffort() {
  try {
    const v = localStorage.getItem(REASONING_EFFORT_KEY);
    return REASONING_EFFORTS.includes(v) ? v : '';
  } catch (_) { return ''; }
}
function syncReasoningEffortUi() {
  const on = getThinkState();
  if (reasoningEffortSelect) {
    reasoningEffortSelect.disabled = !on;
    reasoningEffortSelect.value = getReasoningEffort();
    reasoningEffortSelect.title = on
      ? '推理强度：DeepSeek 后端不读取此字段（仅 UI 提示）；MiniMax-M3.1-Flash-Preview 支持 低/中/高/极高/最高；其他 MiniMax 模型仅 开/关 思考生效'
      : '开启「思考」后可选择推理强度（默认 = 让模型自选）';
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
  const effort = REASONING_EFFORTS.includes(val) ? val : '';
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
