/* ================================================================
 * 11h-env-mcp-c-board.js
 *   MCP server 卡片构建、渲染、网络层、init IIFE。
 *   依赖：a-state.js (isMinimaxMcpServer / mcpStatusForId / mcpStatusLine / formatArgsList)
 *        b-form.js (mcpGenericFormHtml / mcpMinimaxFormHtml / collectServerFromWrap
 *                   / collectAllMcpServersFromBoard)
 *   上游依赖：00-utils.js (escapeHtml)。
 * ================================================================ */

function buildMcpServerCard(serverId, cfg, status, meta) {
  meta = meta || {};
  const wrap = document.createElement('div');
  wrap.className = 'mcp-card-wrap';
  wrap.setAttribute('data-server-id', serverId);

  const minimax = isMinimaxMcpServer(serverId, cfg);
  const header = document.createElement('div');
  header.className = 'mcp-card';

  const info = document.createElement('div');
  info.className = 'mcp-card__info';
  const title = document.createElement('div');
  title.className = 'mcp-card__name';
  title.textContent = serverId + (minimax ? ' · MiniMax' : '');
  const badge = document.createElement('span');
  badge.className = 'mcp-card__badge' + (status && status.connected ? ' mcp-card__badge--ok' : '');
  badge.textContent = mcpStatusLine(status);
  title.appendChild(badge);

  const detail = document.createElement('div');
  detail.className = 'mcp-card__detail';
  detail.textContent = (cfg.command || '') + (cfg.args && cfg.args.length ? ' ' + formatArgsList(cfg.args) : '');

  info.appendChild(title);
  info.appendChild(detail);

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
    // 删除后自动保存
    var statusEl = document.getElementById('mcpEnvStatus');
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
  editWrap.appendChild(editStatus);

  header.style.cursor = 'pointer';
  header.addEventListener('click', function(ev) {
    if (ev.target.closest('.btn')) return;
    const open = editWrap.style.display !== 'block';
    editWrap.style.display = open ? 'block' : 'none';
    editStatus.textContent = '';
    editStatus.classList.remove('is-err');
  });

  wrap.appendChild(header);
  wrap.appendChild(editWrap);
  return wrap;
}

function renderMcpServerBoard(servers, statusRows, meta) {
  const board = document.getElementById('mcpServerBoard');
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
  const board = document.getElementById('mcpServerBoard');
  if (!board) return;
  if (board.querySelector('.mcp-card-wrap')) {
    const empty = board.querySelector('.mcp-board-empty');
    if (empty) empty.remove();
    return;
  }
  if (!board.querySelector('.mcp-board-empty')) {
    const p = document.createElement('p');
    p.className = 'mcp-board-empty';
    p.textContent = '尚未添加 MCP 服务。可从下方模板快速添加 MiniMax、uvx/npx 包或自定义 stdio 服务。';
    board.appendChild(p);
  }
}

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
  const statusEl = wrap.querySelector('.mcp-edit-wrap .status-line') || document.getElementById('mcpEnvStatus');
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
    if (statusEl) statusEl.textContent = tools ? ('测试通过：' + tools) : '测试通过';
    await loadMcpEnvConfig();
  } catch (e) {
    if (statusEl) {
      statusEl.classList.add('is-err');
      statusEl.textContent = String(e.message || e);
    }
  }
}

function showNewMcpServerForm(templateId) {
  const board = document.getElementById('mcpServerBoard');
  if (!board) return;
  const existing = board.querySelector('.mcp-card-wrap.is-new');
  if (existing) existing.remove();

  const tpl = MCP_TEMPLATES.find(function(t) { return t.id === templateId; }) || MCP_TEMPLATES[MCP_TEMPLATES.length - 1];
  const wrap = document.createElement('div');
  wrap.className = 'mcp-card-wrap is-new';

  const editWrap = document.createElement('div');
  editWrap.className = 'mcp-edit-wrap';
  editWrap.style.display = 'block';
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
      // 自动保存全部到 mcp.json
      saveMcpEnvAndConfig().then(function() {
        editStatus.textContent = '已添加并保存。';
      }).catch(function(e) {
        editStatus.classList.add('is-err');
        editStatus.textContent = '添加成功但保存失败：' + String(e.message || e) + '，请点击「保存全部」重试。';
      });
    } catch (e) {
      editStatus.classList.add('is-err');
      editStatus.textContent = String(e.message || e);
    }
  });

  wrap.appendChild(editWrap);
  board.insertBefore(wrap, board.firstChild);
  const empty = board.querySelector('.mcp-board-empty');
  if (empty) empty.remove();
  wrap.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

async function loadMcpEnvConfig() {
  const status = document.getElementById('mcpEnvStatus');
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

    const chkOn = document.getElementById('chkMcpEnabled');
    if (chkOn) chkOn.checked = _mcpEnvVal(envJ, 'SEED_MCP_ENABLED', '1') === '1';
    const chkReg = document.getElementById('chkMcpRegisterTools');
    if (chkReg) chkReg.checked = _mcpEnvVal(envJ, 'SEED_MCP_REGISTER_TOOLS', '1') === '1';

    const pathEl = document.getElementById('mcpConfigPath');
    if (pathEl) pathEl.textContent = mcpJ.path || '';

    const uvxEl = document.getElementById('mcpUvxHint');
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
  const status = document.getElementById('mcpEnvStatus');
  if (!status) return;
  status.textContent = '保存中…';
  status.classList.remove('is-err');
  try {
    const envBody = {
      SEED_MCP_ENABLED: (document.getElementById('chkMcpEnabled') || {}).checked ? '1' : '0',
      SEED_MCP_REGISTER_TOOLS: (document.getElementById('chkMcpRegisterTools') || {}).checked ? '1' : '0',
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

    status.textContent = '已保存 ' + Object.keys(servers).length + ' 个 MCP 服务。';
    await loadMcpEnvConfig();
    if (typeof refreshMultimodalModelSelects === 'function') {
      refreshMultimodalModelSelects().catch(function() {});
    } else if (typeof refreshTtsOptions === 'function') {
      refreshTtsOptions().catch(function() {});
    }
  } catch (e) {
    status.classList.add('is-err');
    status.textContent = String(e.message || e);
  }
}

(function initMcpBoard() {
  const btn = document.getElementById('btnMcpEnvSave');
  if (btn) btn.addEventListener('click', function() { saveMcpEnvAndConfig(); });
  const ref = document.getElementById('btnMcpEnvRefresh');
  if (ref) ref.addEventListener('click', function() { loadMcpEnvConfig(); });

  const addBtn = document.getElementById('btnMcpAdd');
  const tplSel = document.getElementById('selMcpTemplate');
  if (addBtn) {
    addBtn.addEventListener('click', function() {
      showNewMcpServerForm((tplSel && tplSel.value) || 'custom');
    });
  }

  if (tplSel) {
    tplSel.innerHTML = '';
    MCP_TEMPLATES.forEach(function(t) {
      const o = document.createElement('option');
      o.value = t.id;
      o.textContent = t.label;
      tplSel.appendChild(o);
    });
  }

  loadMcpEnvConfig();
})();
