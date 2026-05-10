/* ================================================================
 * 13-todos.js — Todo panel UI (v3: scope toggle + session isolation)
 *   - render todo items from /api/ui/projects/todos
 *   - scope toggle: 当前会话（session） / 全部（project）
 *   - toggle checkboxes to update status
 *   - delete buttons
 *   - grouped by session_id with round identifiers
 *   - auto-refresh on project changes
 * ================================================================ */

const btnToggleTodos = document.getElementById('btnToggleTodos');
const todoPanel = document.getElementById('todoPanel');
const todoList = document.getElementById('todoList');
const btnTodoRefresh = document.getElementById('btnTodoRefresh');
const todoScopeToggle = document.getElementById('todoScopeToggle');

let todoScope = 'session'; // 'session' | 'project'

// 用实际 DOM display 状态判断，避免被对方面板互斥关闭后状态不同步
function todoIsVisible() {
  return todoPanel.style.display === 'flex';
}

try {
  if (localStorage.getItem('oa_todo_panel_open') === '1') {
    // 初始化互斥：如果 Plan 已打开，不覆盖
    var planP = document.getElementById('planPanel');
    if (planP && planP.style.display === 'flex') {
      // Plan 已开 → 忽略 localStorage，自己不打开
    } else {
      todoPanel.style.display = 'flex';
      btnToggleTodos.classList.add('is-active');
      setTimeout(function() { refreshTodos(); }, 100);
    }
  }
} catch (_) {}

try {
  const saved = localStorage.getItem('oa_todo_scope');
  if (saved === 'project' || saved === 'session') todoScope = saved;
} catch (_) {}

btnToggleTodos.addEventListener('click', () => {
  var opening = !todoIsVisible();
  todoPanel.style.display = opening ? 'flex' : 'none';
  btnToggleTodos.classList.toggle('is-active', opening);
  try { localStorage.setItem('oa_todo_panel_open', opening ? '1' : '0'); } catch (_) {}
  // 互斥：打开待办时自动关闭计划面板
  if (opening) {
    var planPanel = document.getElementById('planPanel');
    var planBtn = document.getElementById('btnTogglePlans');
    if (planPanel && planPanel.style.display !== 'none') {
      planPanel.style.display = 'none';
      if (planBtn) planBtn.classList.remove('is-active');
      try { localStorage.setItem('oa_plan_panel_open', '0'); } catch (_) {}
    }
    refreshTodos();
  }
});

if (btnTodoRefresh) { btnTodoRefresh.addEventListener('click', refreshTodos); }

/* ---- Scope toggle ---- */

function applyScopeUI() {
  if (!todoScopeToggle) return;
  const btns = todoScopeToggle.querySelectorAll('.todo-scope-btn');
  for (const btn of btns) {
    btn.classList.toggle('is-active', btn.dataset.scope === todoScope);
  }
}

if (todoScopeToggle) {
  todoScopeToggle.addEventListener('click', (e) => {
    const btn = e.target.closest('.todo-scope-btn');
    if (!btn) return;
    const scope = btn.dataset.scope;
    if (scope === todoScope) return;
    todoScope = scope;
    try { localStorage.setItem('oa_todo_scope', todoScope); } catch (_) {}
    applyScopeUI();
    refreshTodos();
  });
  applyScopeUI();
}

/* ---- helpers ---- */

function shortenId(id) {
  if (!id) return '—';
  return id.length > 8 ? id.slice(0, 8) : id;
}

function formatRelativeTime(isoStr) {
  if (!isoStr) return '';
  const then = new Date(isoStr);
  if (isNaN(then.getTime())) return isoStr;
  const diffMs = Date.now() - then.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 10) return '刚刚';
  if (diffSec < 60) return diffSec + '秒前';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return diffMin + '分钟前';
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return diffHr + '小时前';
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return diffDay + '天前';
  return then.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

// Deterministic color from session_id hash
const sessionColors = [
  { bg: '#e3f2fd', text: '#1565c0', border: '#90caf9' },
  { bg: '#fce4ec', text: '#c62828', border: '#f48fb1' },
  { bg: '#e8f5e9', text: '#2e7d32', border: '#a5d6a7' },
  { bg: '#fff3e0', text: '#e65100', border: '#ffcc80' },
  { bg: '#f3e5f5', text: '#7b1fa2', border: '#ce93d8' },
  { bg: '#e0f7fa', text: '#00695c', border: '#80deea' },
  { bg: '#fbe9e7', text: '#bf360c', border: '#ffab91' },
  { bg: '#ede7f6', text: '#4527a0', border: '#b39ddb' },
  { bg: '#f1f8e9', text: '#558b2f', border: '#aed581' },
  { bg: '#fff8e1', text: '#f57f17', border: '#ffe082' },
];

function sessionColor(sessionId) {
  if (!sessionId) return sessionColors[0];
  let hash = 0;
  for (let i = 0; i < sessionId.length; i++) {
    hash = ((hash << 5) - hash) + sessionId.charCodeAt(i);
    hash |= 0;
  }
  const idx = Math.abs(hash) % sessionColors.length;
  return sessionColors[idx];
}

function formatSessionLabel(sessionId) {
  if (!sessionId) return '未分组';
  return shortenId(sessionId);
}

