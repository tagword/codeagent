/* ================================================================
 * 11h-env-mcp-c-board.js
 *   MCP server 卡片构建、渲染、网络层、init IIFE。
 *   依赖：a-state.js (isMinimaxMcpServer / mcpStatusForId / mcpStatusLine / formatArgsList)
 *        b-form.js (mcpGenericFormHtml / mcpMinimaxFormHtml / collectServerFromWrap
 *                   / collectAllMcpServersFromBoard)
 *   上游依赖：00-utils.js (escapeHtml)。
 *
 *   DOM 缓存：mcpDom = { board, status, chkOn, chkReg, pathEl, uvxEl,
 *                        btn, ref, addBtn, tplSel } 在 initMcpBoard IIFE
 *   中一次性 getElementById 填充。
 * ================================================================ */

const mcpDom = {};

/* ---- 卡片构建 ---- */

function buildMcpServerCard(serverId, cfg, status, meta) {
  meta = meta || {};
  const wrap = document.createElement('div');
  wrap.className = 'mcp-card-wrap';
  wrap.setAttribute('data-server-id', serverId);

  const minimax = isMinimaxMcpServer(serverId, cfg);
  const transport = cfg.transport || 'stdio';

  // ---- Header（始终可见） ----
  const header = document.createElement('div');
  header.className = 'mcp-card';

  const info = document.createElement('div');
  info.className = 'mcp-card__info';

  // 第一行：服务名 + 传输标签 + 状态
  const titleRow = document.createElement('div');
  titleRow.style.cssText = 'display:flex;align-items:center;gap:var(--sp-1);flex-wrap:wrap;';

  const title = document.createElement('span');
  title.className = 'mcp-card__name';
  title.textContent = serverId + (minimax ? ' · MiniMax' : '');

  const tTag = document.createElement('span');
  tTag.className = 'mcp-card__transport';
  tTag.textContent = transport === 'sse' ? 'SSE' : 'stdio';
  tTag.style.cssText = transport === 'sse'
    ? 'font-size:11px;padding:1px 6px;border-radius:var(--r-sm);background:var(--accent-dim, #e8f0fe);color:var(--accent,#1a73e8);font-weight:500;'
    : 'font-size:11px;padding:1px 6px;border-radius:var(--r-sm);background:var(--bg-2,#eee);color:var(--fg-2,#666);font-weight:500;';

  const badge = document.createElement('span');
  badge.className = 'mcp-card__badge' + (status && status.connected ? ' mcp-card__badge--ok' : '');
  badge.textContent = mcpStatusLine(status);

  titleRow.appendChild(title);
  titleRow.appendChild(tTag);
  titleRow.appendChild(badge);

  // 第二行：详情（command / url）
  const detail = document.createElement('div');
  detail.className = 'mcp-card__detail';
  if (transport === 'sse') {
    detail.textContent = '→ ' + (cfg.url || '未配置 URL');
  } else {
    detail.textContent = '$ ' + (cfg.command || '') + (cfg.args && cfg.args.length ? ' ' + formatArgsList(cfg.args) : '');
  }

  // 错误信息（未连接时显示）
  if (status && !status.connected && status.last_error) {
    const errLine = document.createElement('div');
    errLine.className = 'mcp-card__error';
    errLine.textContent = '⚠ ' + status.last_error;
    info.appendChild(titleRow);
    info.appendChild(detail);
    info.appendChild(errLine);
  } else {
    info.appendChild(titleRow);
    info.appendChild(detail);
  }

  // ---- 操作按钮 ----
  const actions = document.createElement('div');
  actions.className = 'mcp-card__actions';

  const btnTest = document.createElement('button');
  btnTest.type = 'button';
  btnTest.className = 'btn btn--ghost btn--xs';
  btnTest.textContent = '测试';
  btnTest.addEventListener('click', function(ev) {
    ev.stopPropagation();
    testMcpCard(wrap, meta);
  });

  const btnDel = document.createElement('button');
  btnDel.type = 'button';
  btnDel.className = 'btn btn--ghost btn--xs mcp-del';
  btnDel.textContent = '删除';
  btnDel.addEventListener('click', function(ev) {
    ev.stopPropagation();
    if (!confirm('确定删除 MCP 服务「' + serverId + '」？')) return;
    wrap.remove();
    updateMcpBoardEmptyState();
    var statusEl = mcpDom.status;
    if (statusEl) statusEl.textContent = '已删除，正在保存…';
    saveMcpEnvAndConfig().catch(function(e) {
      if (statusEl) {
        statusEl.classList.add('is-err');
        statusEl.textContent = '删除成功但保存失败：' + String(e.message || e) + '，请点击「保存全部」重试。';
      }
    });
  });

  actions.appendChild(btnTest);
  actions.appendChild(btnDel);

  header.appendChild(info);
  header.appendChild(actions);

  // ---- 编辑区（可展开） ----
  const editWrap = document.createElement('div');
  editWrap.className = 'mcp-edit-wrap';
  editWrap.style.display = 'none';
  const editStatus = document.createElement('div');
  editStatus.className = 'status-line';

  if (minimax) {
    editWrap.innerHTML = mcpMinimaxFormHtml(cfg, meta);
  } else {
    editWrap.innerHTML = '<input type="hidden" class="mcp-fld-kind" value="generic"/>' +
      mcpGenericFormHtml(cfg, { serverId: serverId, idReadonly: true });
  }

  // 内联操作栏：保存 + 测试 + 删除
  const editActions = document.createElement('div');
  editActions.className = 'row-actions mcp-edit-actions';
  editActions.style.cssText = 'margin:var(--sp-2) 0 0;display:flex;gap:var(--sp-1);';
  editActions.innerHTML =
    '<button type="button" class="btn btn--primary btn--sm mcp-apply-btn">应用</button>' +
    '<button type="button" class="btn btn--ghost btn--sm mcp-test-btn">测试</button>' +
    '<button type="button" class="btn btn--subtle btn--sm mcp-edit-del-btn" style="margin-left:auto;color:var(--danger);">删除</button>';
  editWrap.appendChild(editActions);
  editWrap.appendChild(editStatus);

  // 编辑窗「应用」按钮
  editActions.querySelector('.mcp-apply-btn').addEventListener('click', function() {
    applyMcpCard(wrap, meta);
  });

  // 编辑窗「测试」按钮
  editActions.querySelector('.mcp-test-btn').addEventListener('click', function() {
    testMcpCard(wrap, meta);
  });

  // 编辑窗「删除」按钮
  editActions.querySelector('.mcp-edit-del-btn').addEventListener('click', function() {
    if (!confirm('确定删除 MCP 服务「' + serverId + '」？')) return;
    wrap.remove();
    updateMcpBoardEmptyState();
    var statusEl = mcpDom.status;
    if (statusEl) statusEl.textContent = '已删除，正在保存…';
    saveMcpEnvAndConfig().catch(function(e) {
      if (statusEl) {
        statusEl.classList.add('is-err');
        statusEl.textContent = '删除失败：' + String(e.message || e);
      }
    });
  });

  // Header 点击展开/收起编辑区
  header.style.cursor = 'pointer';
  header.addEventListener('click', function(ev) {
    if (ev.target.closest('.btn')) return;
    var open = editWrap.style.display !== 'block';
    editWrap.style.display = open ? 'block' : 'none';
    editStatus.textContent = '';
    editStatus.classList.remove('is-err');
  });

  wrap.appendChild(header);
  wrap.appendChild(editWrap);
  return wrap;
}

/** 应用单个卡片的修改到 board + 触发全局保存 */
function applyMcpCard(wrap, meta) {
  var editStatus = wrap.querySelector('.mcp-edit-wrap .status-line');
  if (editStatus) {
    editStatus.textContent = '保存中…';
    editStatus.classList.remove('is-err');
  }
  try {
    var row = collectServerFromWrap(wrap, meta || {});
    if (!row) throw new Error('请填写完整配置');

    // 更新卡片 DOM 中的 data-server-id（如果 ID 变了）
    wrap.setAttribute('data-server-id', row.id);

    // 刷新卡片 header 显示
    var board = mcpDom.board;
    if (board) {
      // 重建卡片（保留原有的 expand/close 状态比较麻烦，走全量 reload）
      saveMcpEnvAndConfig();
    }
  } catch (e) {
    if (editStatus) {
      editStatus.classList.add('is-err');
      editStatus.textContent = String(e.message || e);
    }
  }
}

/* ---- 渲染 ---- */

function renderMcpServerBoard(servers, statusRows, meta) {
  const board = mcpDom.board;
  if (!board) return;
  board.innerHTML = '';
  const ids = Object.keys(servers || {}).sort();
  if (!ids.length) {
    updateMcpBoardEmptyState();
    return;
  }
  ids.forEach(function(sid) {
    const st = mcpStatusForId(sid);
    board.appendChild(buildMcpServerCard(sid, servers[sid], st, meta));
  });
}

function updateMcpBoardEmptyState() {
  const board = mcpDom.board;
  if (!board) return;
  if (board.querySelector('.mcp-card-wrap')) {
    const empty = board.querySelector('.mcp-board-empty');
    if (empty) empty.remove();
    return;
  }
  if (!board.querySelector('.mcp-board-empty')) {
    const p = document.createElement('p');
    p.className = 'mcp-board-empty';
    p.textContent = '尚未添加 MCP 服务。可从上方的模板选择器添加 MiniMax、uvx/npx 包、自建 stdio 或 SSE 远程服务。';
    board.appendChild(p);
  }
}

/* ---- 网络层 ---- */

async function testMcpServerPayload(payload) {
  const r = await fetch('/api/ui/mcp/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify(payload),
  });
  const j = await r.json().catch(function() { return {}; });
  if (!r.ok) throw new Error(j.detail || r.statusText || '测试失败');
  return j;
}

async function testMcpCard(wrap, meta) {
  const statusEl = wrap.querySelector('.mcp-edit-wrap .status-line') || mcpDom.status;
  if (statusEl) {
    statusEl.textContent = '测试中…';
    statusEl.classList.remove('is-err');
  }
  try {
    const row = collectServerFromWrap(wrap, meta);
    if (!row) throw new Error('请填写完整配置');
    const payload = Object.assign({ id: row.id }, row.config);
    const j = await testMcpServerPayload(payload);
    const tools = (j.tools || []).join('、');
    if (statusEl) statusEl.textContent = tools ? ('✅ 测试通过：' + tools) : '✅ 测试通过';
    await loadMcpEnvConfig();
  } catch (e) {
    if (statusEl) {
      statusEl.classList.add('is-err');
      statusEl.textContent = '❌ ' + String(e.message || e);
    }
  }
}

/* ---- 添加新服务 ---- */

function showNewMcpServerForm(templateId) {
  const board = mcpDom.board;
  if (!board) return;
  const existing = board.querySelector('.mcp-card-wrap.is-new');
  if (existing) existing.remove();

  const tpl = MCP_TEMPLATES.find(function(t) { return t.id === templateId; }) || MCP_TEMPLATES[MCP_TEMPLATES.length - 1];
  const wrap = document.createElement('div');
  wrap.className = 'mcp-card-wrap is-new';

  const editWrap = document.createElement('div');
  editWrap.className = 'mcp-edit-wrap';
  editWrap.style.display = 'block';

  // 新表单自带一个较大的 header 说明
  const hintBar = document.createElement('div');
  hintBar.style.cssText = 'padding:var(--sp-1) var(--sp-2);background:var(--accent-dim,#e8f0fe);border-radius:var(--r-md) var(--r-md) 0 0;font-size:var(--fs-sm);color:var(--accent,#1a73e8);';
  hintBar.textContent = '添加新 MCP 服务：' + tpl.label;

  const editStatus = document.createElement('div');
  editStatus.className = 'status-line';

  if (tpl.kind === 'minimax') {
    editWrap.innerHTML = mcpMinimaxFormHtml({ enabled: true, command: 'uvx', env: {} }, window._mcpMeta || {});
  } else {
    editWrap.innerHTML = '<input type="hidden" class="mcp-fld-kind" value="generic"/>' +
      mcpGenericFormHtml(tpl.config || {}, { serverId: tpl.serverId || '' });
  }

  const actions = document.createElement('div');
  actions.className = 'row-actions';
  actions.style.marginTop = 'var(--sp-2)';
  actions.innerHTML =
    '<button type="button" class="btn btn--primary btn--sm mcp-new-save">添加</button>' +
    '<button type="button" class="btn btn--ghost btn--sm mcp-new-test">测试</button>' +
    '<button type="button" class="btn btn--subtle btn--sm mcp-new-cancel">取消</button>';
  editWrap.appendChild(actions);
  editWrap.appendChild(editStatus);

  if (tpl.hint) {
    const hint = document.createElement('p');
    hint.className = 'form-hint';
    hint.textContent = tpl.hint;
    editWrap.insertBefore(hint, actions);
  }

  actions.querySelector('.mcp-new-cancel').addEventListener('click', function() { wrap.remove(); updateMcpBoardEmptyState(); });
  actions.querySelector('.mcp-new-test').addEventListener('click', function() { testMcpCard(wrap, window._mcpMeta || {}); });
  actions.querySelector('.mcp-new-save').addEventListener('click', function() {
    try {
      const row = collectServerFromWrap(wrap, window._mcpMeta || {});
      if (!row) throw new Error('请填写完整配置');
      if (board.querySelector('.mcp-card-wrap[data-server-id="' + row.id + '"]')) {
        throw new Error('服务 ID「' + row.id + '」已存在');
      }
      const empty = board.querySelector('.mcp-board-empty');
      if (empty) empty.remove();
      const card = buildMcpServerCard(row.id, row.config, null, window._mcpMeta || {});
      board.appendChild(card);
      wrap.remove();
      editStatus.textContent = '已添加，正在保存…';
      saveMcpEnvAndConfig().then(function() {
        editStatus.textContent = '✅ 已添加并保存。';
      }).catch(function(e) {
        editStatus.classList.add('is-err');
        editStatus.textContent = '❌ 添加成功但保存失败：' + String(e.message || e) + '，请点击「保存全部」重试。';
      });
    } catch (e) {
      editStatus.classList.add('is-err');
      editStatus.textContent = '❌ ' + String(e.message || e);
    }
  });

  wrap.appendChild(hintBar);
  wrap.appendChild(editWrap);
  board.insertBefore(wrap, board.firstChild);
  const empty = board.querySelector('.mcp-board-empty');
  if (empty) empty.remove();
  wrap.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

/* ---- 数据加载与保存 ---- */

async function loadMcpEnvConfig() {
  const status = mcpDom.status;
  if (!status) return;
  status.textContent = '加载中…';
  status.classList.remove('is-err');
  try {
    const [envR, mcpR] = await Promise.all([
      fetch('/api/ui/env/mcp'),
      fetch('/api/ui/mcp'),
    ]);
    if (!envR.ok) throw new Error(envR.statusText);
    if (!mcpR.ok) throw new Error(mcpR.statusText);
    const envJ = await envR.json();
    const mcpJ = await mcpR.json();

    if (mcpDom.chkOn) mcpDom.chkOn.checked = _mcpEnvVal(envJ, 'SEED_MCP_ENABLED', '1') === '1';
    if (mcpDom.chkReg) mcpDom.chkReg.checked = _mcpEnvVal(envJ, 'SEED_MCP_REGISTER_TOOLS', '1') === '1';

    if (mcpDom.pathEl) mcpDom.pathEl.textContent = mcpJ.path || '';

    const uvxEl = mcpDom.uvxEl;
    if (uvxEl) {
      uvxEl.textContent = mcpJ.uvx_path
        ? ('已检测到 uvx：' + mcpJ.uvx_path)
        : '未检测到 uvx；MiniMax / uvx 类 MCP 请将 command 填为 uvx 的绝对路径';
    }

    const servers = (mcpJ.config && mcpJ.config.servers) ? mcpJ.config.servers : {};
    window._mcpConfigCache = { servers: servers };
    window._mcpStatusCache = mcpJ.servers_status || [];
    window._mcpMeta = {
      uvx_path: mcpJ.uvx_path || '',
      minimax_output_dir: mcpJ.minimax_output_dir || '',
    };

    renderMcpServerBoard(servers, window._mcpStatusCache, window._mcpMeta);

    if (typeof refreshVisionModelSelect === 'function') refreshVisionModelSelect();
    status.textContent = '共 ' + Object.keys(servers).length + ' 个 MCP 服务';
  } catch (e) {
    status.classList.add('is-err');
    status.textContent = '加载失败：' + String(e);
  }
}

async function saveMcpEnvAndConfig() {
  const status = mcpDom.status;
  if (!status) return;
  status.textContent = '保存中…';
  status.classList.remove('is-err');
  try {
    const envBody = {
      SEED_MCP_ENABLED: ((mcpDom.chkOn || {}).checked) ? '1' : '0',
      SEED_MCP_REGISTER_TOOLS: ((mcpDom.chkReg || {}).checked) ? '1' : '0',
    };
    const envR = await fetch('/api/ui/env/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(envBody),
    });
    const envJ = await envR.json().catch(function() { return {}; });
    if (!envR.ok) throw new Error(envJ.detail || envR.statusText);

    const servers = collectAllMcpServersFromBoard(window._mcpMeta || {});
    const mcpR = await fetch('/api/ui/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ servers: servers }),
    });
    const mcpSave = await mcpR.json().catch(function() { return {}; });
    if (!mcpR.ok) throw new Error(mcpSave.detail || mcpR.statusText);

    status.textContent = '✅ 已保存 ' + Object.keys(servers).length + ' 个 MCP 服务。';
    await loadMcpEnvConfig();
    if (typeof refreshMultimodalModelSelects === 'function') {
      refreshMultimodalModelSelects().catch(function() {});
    } else if (typeof refreshTtsOptions === 'function') {
      refreshTtsOptions().catch(function() {});
    }
  } catch (e) {
    status.classList.add('is-err');
    status.textContent = '❌ ' + String(e.message || e);
  }
}

/* ---- Init ---- */

(function initMcpBoard() {
  [
    ['board',   'mcpServerBoard'],
    ['status',  'mcpEnvStatus'],
    ['chkOn',   'chkMcpEnabled'],
    ['chkReg',  'chkMcpRegisterTools'],
    ['pathEl',  'mcpConfigPath'],
    ['uvxEl',   'mcpUvxHint'],
    ['btn',     'btnMcpEnvSave'],
    ['ref',     'btnMcpEnvRefresh'],
    ['addBtn',  'btnMcpAdd'],
    ['tplSel',  'selMcpTemplate'],
  ].forEach(function(pair) {
    mcpDom[pair[0]] = document.getElementById(pair[1]);
  });

  if (mcpDom.btn) {
    mcpDom.btn.addEventListener('click', function() { saveMcpEnvAndConfig(); });
  }
  if (mcpDom.ref) {
    mcpDom.ref.addEventListener('click', function() { loadMcpEnvConfig(); });
  }

  if (mcpDom.addBtn) {
    mcpDom.addBtn.addEventListener('click', function() {
      showNewMcpServerForm((mcpDom.tplSel && mcpDom.tplSel.value) || 'custom');
    });
  }

  if (mcpDom.tplSel) {
    mcpDom.tplSel.innerHTML = '';
    MCP_TEMPLATES.forEach(function(t) {
      const o = document.createElement('option');
      o.value = t.id;
      o.textContent = t.label;
      mcpDom.tplSel.appendChild(o);
    });
  }

  loadMcpEnvConfig();
})();
