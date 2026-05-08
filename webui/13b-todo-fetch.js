/* ---- API ---- */

async function fetchTodos() {
  const pid = typeof projectId !== 'undefined' ? (projectId || '') : '';
  if (!pid) return [];
  try {
    let url = '/api/ui/projects/todos?project_id=' + encodeURIComponent(pid)
      + '&agent_id=' + encodeURIComponent(typeof agentId !== 'undefined' ? agentId : 'default');
    // When scope is "session", filter by current session_id
    if (todoScope === 'session') {
      const sid = typeof sessionId !== 'undefined' ? (sessionId || '') : '';
      if (sid) url += '&session_id=' + encodeURIComponent(sid);
    }
    const r = await fetch(url);
    if (!r.ok) return [];
    const j = await r.json();
    return j.todos || [];
  } catch (_) { return []; }
}

/* ---- Grouping & Rendering ---- */

function groupBySession(todos) {
  const groups = {};
  for (const t of todos) {
    const sid = t.session_id || '';
    if (!groups[sid]) groups[sid] = [];
    groups[sid].push(t);
  }
  for (const sid in groups) {
    groups[sid].sort((a, b) => {
      const da = a.created_at || '';
      const db = b.created_at || '';
      return da.localeCompare(db);
    });
  }
  const keys = Object.keys(groups);
  keys.sort((a, b) => {
    const aOldest = groups[a][0]?.created_at || '';
    const bOldest = groups[b][0]?.created_at || '';
    const cmp = aOldest.localeCompare(bOldest);
    if (cmp !== 0) return cmp;
    return a.localeCompare(b);
  });
  return keys.map(k => ({ sessionId: k, items: groups[k] }));
}

async function refreshTodos() {
  const todos = await fetchTodos();
  if (!todoList) return;
  todoList.innerHTML = '';
  if (!todos || !todos.length) {
    const msg = todoScope === 'session'
      ? '当前会话暂无待办事项<br/>让 Agent 创建待办'
      : '暂无待办事项<br/>在会话中让 Agent 创建待办';
    todoList.innerHTML = '<div class="todo-empty">' + msg + '</div>';
    return;
  }
  const grouped = groupBySession(todos);
  let first = true;
  for (const g of grouped) {
    if (!first) {
      const sep = document.createElement('div');
      sep.className = 'todo-group-sep';
      todoList.appendChild(sep);
    }
    first = false;
    // In session scope, the group header is simpler — just a count
    if (todoScope === 'session') {
      // Show a minimal "来自当前会话" indicator instead of full group header
      const c = sessionColor(g.sessionId);
      const header = document.createElement('div');
      header.className = 'todo-group-header';
      header.innerHTML = '<span class="todo-group-badge" style="--gb-bg:' + c.bg + ';--gb-text:' + c.text + ';--gb-border:' + c.border + '">' + formatSessionLabel(g.sessionId) + '</span>'
        + '<span class="todo-group-meta"><span class="todo-group-count">' + g.items.length + ' 项</span></span>';
      todoList.appendChild(header);
    } else {
      todoList.appendChild(buildGroupHeader(g.sessionId, g.items));
    }
    for (const t of g.items) {
      todoList.appendChild(buildTodoItem(t, g.sessionId));
    }
  }
}

function buildGroupHeader(sessionId, items) {
  const c = sessionColor(sessionId);
  const header = document.createElement('div');
  header.className = 'todo-group-header';
  const label = formatSessionLabel(sessionId);
  const count = items.length;
  const times = items.map(t => t.created_at).filter(Boolean).sort();
  const timeStr = times.length > 0
    ? formatRelativeTime(times[0]) + (times.length > 1 ? ' ~ ' + formatRelativeTime(times[times.length - 1]) : '')
    : '';
  header.innerHTML = `
    <span class="todo-group-badge" style="--gb-bg:${c.bg};--gb-text:${c.text};--gb-border:${c.border}">
      ${label}
    </span>
    <span class="todo-group-meta">
      <span class="todo-group-count">${count} 项</span>
      ${timeStr ? '<span class="todo-group-time">' + timeStr + '</span>' : ''}
    </span>
  `;
  return header;
}
