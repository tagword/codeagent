/* MCP server board: add / edit / test stdio servers (config/mcp.json) */

var MINIMAX_MCP_ID = 'MiniMax';

var MCP_TEMPLATES = [
  {
    id: 'minimax',
    label: 'MiniMax Token Plan',
    serverId: MINIMAX_MCP_ID,
    kind: 'minimax',
    hint: 'understand_image、web_search；需 uvx 与 Token Plan Key',
  },
  {
    id: 'uvx',
    label: 'uvx 包',
    serverId: '',
    kind: 'generic',
    config: {
      enabled: true,
      transport: 'stdio',
      command: 'uvx',
      args: ['your-mcp-package', '-y'],
      env: {},
    },
    hint: '将 your-mcp-package 换成 PyPI 包名',
  },
  {
    id: 'npx',
    label: 'npx 包',
    serverId: '',
    kind: 'generic',
    config: {
      enabled: true,
      transport: 'stdio',
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-filesystem', '/path/to/dir'],
      env: {},
    },
    hint: 'Node MCP 示例；请修改 args 中的路径或包名',
  },
  {
    id: 'custom',
    label: '自定义 stdio',
    serverId: '',
    kind: 'generic',
    config: {
      enabled: true,
      transport: 'stdio',
      command: '',
      args: [],
      env: {},
    },
    hint: '填写 command、args 与环境变量',
  },
];

window._mcpConfigCache = { servers: {} };
window._mcpStatusCache = [];

function _mcpEnvVal(j, key, fallback) {
  if (j[key] !== undefined && j[key] !== null && String(j[key]) !== '') return j[key];
  return fallback;
}

function isMinimaxMcpServer(id, cfg) {
  if (id === MINIMAX_MCP_ID) return true;
  const args = (cfg && cfg.args) || [];
  return args.indexOf('minimax-coding-plan-mcp') >= 0;
}

function mcpStatusForId(serverId) {
  return (window._mcpStatusCache || []).find(function(r) { return r.id === serverId; }) || null;
}

function parseArgsText(raw) {
  const s = String(raw || '').trim();
  if (!s) return [];
  if (s.startsWith('[')) {
    try {
      const arr = JSON.parse(s);
      if (Array.isArray(arr)) return arr.map(String);
    } catch (_) {}
  }
  return s.split(/\s+/).filter(Boolean);
}

function formatArgsList(args) {
  if (!Array.isArray(args) || !args.length) return '';
  return args.join(' ');
}

function parseEnvLines(raw) {
  const out = {};
  String(raw || '').split('\n').forEach(function(line) {
    const t = line.trim();
    if (!t || t.startsWith('#')) return;
    const i = t.indexOf('=');
    if (i <= 0) return;
    out[t.slice(0, i).trim()] = t.slice(i + 1).trim();
  });
  return out;
}

function formatEnvLines(env) {
  if (!env || typeof env !== 'object') return '';
  return Object.keys(env).sort().map(function(k) { return k + '=' + env[k]; }).join('\n');
}

function validateMcpServerId(id) {
  return /^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(String(id || '').trim());
}

function mcpGenericFormHtml(cfg, opts) {
  opts = opts || {};
  cfg = cfg || {};
  const idReadonly = opts.idReadonly ? ' readonly' : '';
  return (
    '<label class="form-label">服务 ID</label>' +
    '<input class="mcp-fld-id form-input-sm" type="text" placeholder="MyMCP" value="' + escAttr(opts.serverId || '') + '"' + idReadonly + '/>' +
    '<label class="checkbox-row" style="margin:var(--sp-2) 0;">' +
    '<input type="checkbox" class="mcp-fld-enabled"' + (cfg.enabled !== false ? ' checked' : '') + '/>' +
    '<span>启用</span></label>' +
    '<label class="form-label">Command</label>' +
    '<input class="mcp-fld-command form-input-sm" type="text" placeholder="uvx / npx / /path/to/bin" value="' + escAttr(cfg.command || '') + '"/>' +
    '<label class="form-label">Args</label>' +
    '<input class="mcp-fld-args form-input-sm" type="text" placeholder="pkg -y 或 JSON 数组" value="' + escAttr(formatArgsList(cfg.args)) + '"/>' +
    '<label class="form-label">工作目录 cwd（可选）</label>' +
    '<input class="mcp-fld-cwd form-input-sm" type="text" value="' + escAttr(cfg.cwd || '') + '"/>' +
    '<label class="form-label">环境变量（每行 KEY=value）</label>' +
    '<textarea class="mcp-fld-env form-input-sm" rows="4" placeholder="API_KEY=sk-...">' + escAttr(formatEnvLines(cfg.env)) + '</textarea>'
  );
}

function mcpMinimaxFormHtml(cfg, meta) {
  meta = meta || {};
  cfg = cfg || {};
  const env = cfg.env || {};
  return (
    '<input type="hidden" class="mcp-fld-kind" value="minimax"/>' +
    '<label class="checkbox-row" style="margin:0 0 var(--sp-2);">' +
    '<input type="checkbox" class="mcp-fld-enabled"' + (cfg.enabled !== false ? ' checked' : '') + '/>' +
    '<span>启用 MiniMax MCP</span></label>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">Token Plan API Key</label>' +
    '  <input class="mcp-fld-minimax-key form-input-sm" type="password" value="' + escAttr(env.MINIMAX_API_KEY || '') + '" autocomplete="off"/>' +
    '</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">朗读 API Key（可选）</label>' +
    '  <input class="mcp-fld-minimax-tts-key form-input-sm" type="password" value="' + escAttr(env.MINIMAX_TTS_API_KEY || '') + '" autocomplete="off"/>' +
    '</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">API Host</label>' +
    '  <input class="mcp-fld-minimax-host form-input-sm" type="text" value="' + escAttr(env.MINIMAX_API_HOST || 'https://api.minimaxi.com') + '"/>' +
    '</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">uvx 路径</label>' +
    '  <input class="mcp-fld-minimax-uvx form-input-sm" type="text" value="' + escAttr(cfg.command || meta.uvx_path || 'uvx') + '"/>' +
    '</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">本地输出目录</label>' +
    '  <input class="mcp-fld-minimax-base form-input-sm" type="text" value="' + escAttr(env.MINIMAX_MCP_BASE_PATH || meta.minimax_output_dir || '') + '"/>' +
    '</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">资源模式</label>' +
    '  <select class="mcp-fld-minimax-mode md-select" style="max-width:200px;">' +
    '    <option value=""' + (!env.MINIMAX_API_RESOURCE_MODE ? ' selected' : '') + '>默认</option>' +
    '    <option value="url"' + (env.MINIMAX_API_RESOURCE_MODE === 'url' ? ' selected' : '') + '>url</option>' +
    '    <option value="local"' + (env.MINIMAX_API_RESOURCE_MODE === 'local' ? ' selected' : '') + '>local</option>' +
    '  </select>' +
    '</div>'
  );
}

function collectGenericServerFromWrap(wrap) {
  const id = (wrap.querySelector('.mcp-fld-id') || {}).value.trim();
  if (!validateMcpServerId(id)) throw new Error('服务 ID 无效（字母开头，仅含字母数字 _ -）');
  const enabled = !!(wrap.querySelector('.mcp-fld-enabled') || {}).checked;
  const command = (wrap.querySelector('.mcp-fld-command') || {}).value.trim();
  const args = parseArgsText((wrap.querySelector('.mcp-fld-args') || {}).value);
  const cwd = (wrap.querySelector('.mcp-fld-cwd') || {}).value.trim();
  const env = parseEnvLines((wrap.querySelector('.mcp-fld-env') || {}).value);
  if (!enabled && !command) return null;
  if (enabled && !command) throw new Error('服务「' + id + '」：请填写 command');
  const row = {
    enabled: enabled,
    transport: 'stdio',
    command: command,
    args: args,
    env: env,
  };
  if (cwd) row.cwd = cwd;
  return { id: id, config: row };
}

function collectMinimaxServerFromWrap(wrap, meta) {
  meta = meta || {};
  const enabled = !!(wrap.querySelector('.mcp-fld-enabled') || {}).checked;
  const key = (wrap.querySelector('.mcp-fld-minimax-key') || {}).value.trim();
  const ttsKey = (wrap.querySelector('.mcp-fld-minimax-tts-key') || {}).value.trim();
  const host = (wrap.querySelector('.mcp-fld-minimax-host') || {}).value.trim() || 'https://api.minimaxi.com';
  const uvx = (wrap.querySelector('.mcp-fld-minimax-uvx') || {}).value.trim() || 'uvx';
  const basePath = (wrap.querySelector('.mcp-fld-minimax-base') || {}).value.trim()
    || meta.minimax_output_dir || '';
  const mode = (wrap.querySelector('.mcp-fld-minimax-mode') || {}).value.trim();
  if (!enabled && !key) return null;
  const env = {
    MINIMAX_API_KEY: key,
    MINIMAX_API_HOST: host.replace(/\/+$/, ''),
    MINIMAX_MCP_BASE_PATH: basePath,
  };
  if (ttsKey) env.MINIMAX_TTS_API_KEY = ttsKey;
  if (mode === 'url' || mode === 'local') env.MINIMAX_API_RESOURCE_MODE = mode;
  return {
    id: MINIMAX_MCP_ID,
    config: {
      enabled: enabled,
      transport: 'stdio',
      command: uvx,
      args: ['minimax-coding-plan-mcp', '-y'],
      env: env,
    },
  };
}

function collectServerFromWrap(wrap, meta) {
  const kind = (wrap.querySelector('.mcp-fld-kind') || {}).value;
  const sid = wrap.getAttribute('data-server-id') || '';
  if (kind === 'minimax' || sid === MINIMAX_MCP_ID || isMinimaxMcpServer(sid, {})) {
    return collectMinimaxServerFromWrap(wrap, meta);
  }
  return collectGenericServerFromWrap(wrap);
}

function collectAllMcpServersFromBoard(meta) {
  const servers = {};
  const board = document.getElementById('mcpServerBoard');
  if (!board) return servers;
  board.querySelectorAll('.mcp-card-wrap').forEach(function(wrap) {
    try {
      const row = collectServerFromWrap(wrap, meta);
      if (row && row.id) servers[row.id] = row.config;
    } catch (e) {
      throw e;
    }
  });
  return servers;
}

function mcpStatusLine(status) {
  if (!status) return '未探测';
  if (status.connected) {
    let s = '已连接';
    if (status.tools && status.tools.length) s += '（' + status.tools.join('、') + '）';
    else if (status.tool_count) s += '（' + status.tool_count + ' 个工具）';
    return s;
  }
  if (!status.enabled) return '已禁用';
  return '未连接';
}

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
      editStatus.textContent = '';
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
