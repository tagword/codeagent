function buildTodoItem(todo, sessionId) {
  const c = sessionColor(sessionId);
  const wrap = document.createElement('div');
  wrap.className = 'todo-item';
  wrap.dataset.todoId = todo.id;

  // ── Main row: checkbox + content + delete ──
  const mainRow = document.createElement('div');
  mainRow.className = 'todo-item__main';

  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'todo-item__checkbox';
  cb.checked = todo.status === 'completed';
  cb.addEventListener('change', async () => {
    await updateTodoApi(todo.id, { status: cb.checked ? 'completed' : 'pending' });
    refreshTodos();
  });

  const content = document.createElement('span');
  content.className = 'todo-item__content' + (todo.status === 'completed' ? ' todo-item__content--done' : '');
  content.textContent = todo.content;

  const delBtn = document.createElement('button');
  delBtn.className = 'todo-item__delete';
  delBtn.textContent = '\u00D7';
  delBtn.title = '删除';
  delBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    await deleteTodoApi(todo.id);
    refreshTodos();
  });

  mainRow.appendChild(cb);
  mainRow.appendChild(content);
  mainRow.appendChild(delBtn);

  // ── Meta row: time + status + (optional) session badge ──
  const metaRow = document.createElement('div');
  metaRow.className = 'todo-item__meta';

  const timeBadge = document.createElement('span');
  timeBadge.className = 'todo-item__time';
  timeBadge.textContent = formatRelativeTime(todo.created_at);
  timeBadge.title = todo.created_at || '';

  const statusBadge = document.createElement('span');
  statusBadge.className = 'todo-item__status todo-item__status--' + todo.status;
  const statusLabels = { pending: '待办', in_progress: '进行中', completed: '已完成', cancelled: '已取消' };
  statusBadge.textContent = statusLabels[todo.status] || todo.status;

  metaRow.appendChild(timeBadge);
  metaRow.appendChild(statusBadge);

  // Session badge — only in project scope (all sessions mode)
  if (todoScope === 'project' && sessionId) {
    const sidBadge = document.createElement('span');
    sidBadge.className = 'todo-item__session';
    sidBadge.style.setProperty('--s-bg', c.bg);
    sidBadge.style.setProperty('--s-text', c.text);
    sidBadge.style.setProperty('--s-border', c.border);
    sidBadge.textContent = formatSessionLabel(sessionId);
    sidBadge.title = '会话 ID: ' + (sessionId || '未分组');
    metaRow.appendChild(sidBadge);
  }

  wrap.appendChild(mainRow);
  wrap.appendChild(metaRow);
  return wrap;
}

/* ---- Network ---- */

async function updateTodoApi(todoId, updates) {
  const pid = typeof projectId !== 'undefined' ? (projectId || '') : '';
  try {
    await fetch('/api/ui/projects/todos/' + encodeURIComponent(todoId), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ project_id: pid, agent_id: typeof agentId !== 'undefined' ? agentId : 'default' }, updates))
    });
  } catch (_) {}
}

async function deleteTodoApi(todoId) {
  const pid = typeof projectId !== 'undefined' ? (projectId || '') : '';
  try {
    await fetch('/api/ui/projects/todos/' + encodeURIComponent(todoId) + '?project_id=' + encodeURIComponent(pid) + '&agent_id=' + encodeURIComponent(typeof agentId !== 'undefined' ? agentId : 'default'), { method: 'DELETE' });
  } catch (_) {}
}

window.addEventListener('project-changed', () => { if (todoIsVisible()) refreshTodos(); });
window.addEventListener('session-changed', () => { if (todoIsVisible()) refreshTodos(); });
