/* ================================================================
 * 11h-env-mcp-b-form.js
 *   MCP server 表单 HTML 构造 + 收集器。
 *   依赖：a-state.js 的 isMinimaxMcpServer / MINIMAX_MCP_ID / validateMcpServerId / parseArgsText。
 *   上游依赖：00-utils.js（escAttr）。
 * ================================================================ */

/* ---- 表单构造 ---- */

function mcpGenericFormHtml(cfg, opts) {
  opts = opts || {};
  cfg = cfg || {};
  const idReadonly = opts.idReadonly ? ' readonly' : '';
  const transport = cfg.transport || 'stdio';
  const stdioSel = transport === 'stdio' ? ' selected' : '';
  const sseSel = transport === 'sse' ? ' selected' : '';
  const streamableSel = transport === 'streamable-http' ? ' selected' : '';
  const stdioVis = transport === 'stdio' ? '' : ' style="display:none;"';
  const sseVis = transport === 'sse' ? '' : ' style="display:none;"';
  const streamableVis = transport === 'streamable-http' ? '' : ' style="display:none;"';
  const remoteVis = (transport === 'sse' || transport === 'streamable-http') ? '' : ' style="display:none;"';

  const c = function(v) { return escAttr(v || ''); };
  const isStreamable = transport === 'streamable-http';
  const isSse = transport === 'sse';

  return (
    // ---- 基础信息 ----
    '<div class="mcp-form-section">' +
    '<label class="form-label">服务 ID</label>' +
    '<input class="mcp-fld-id form-input-sm" type="text" placeholder="MyMCP" value="' + c(opts.serverId || '') + '"' + idReadonly + '/>' +

    '<label class="checkbox-row" style="margin:var(--sp-1) 0 var(--sp-2);">' +
    '<input type="checkbox" class="mcp-fld-enabled"' + (cfg.enabled !== false ? ' checked' : '') + '/>' +
    '<span>启用</span></label>' +

    // ---- 传输协议选择 ----
    '<div class="form-row">' +
    '<label class="form-label">传输协议</label>' +
    '<select class="mcp-fld-transport form-input-sm mcp-transport-sel" onchange="mcpToggleTransport(this)">' +
    '<option value="stdio"' + stdioSel + '>stdio（uvx / npx / 本地进程）</option>' +
    '<option value="streamable-http"' + streamableSel + '>HTTP（Streamable HTTP，推荐远程）</option>' +
    '<option value="sse"' + sseSel + '>SSE（旧版远程）</option>' +
    '</select></div>' +

    // ---- stdio 字段组 ----
    '<div class="mcp-stdio-fields mcp-field-group"' + stdioVis + '>' +
    '<div class="mcp-field-group__label">子进程配置</div>' +
    '<label class="form-label">Command</label>' +
    '<input class="mcp-fld-command form-input-sm" type="text" placeholder="uvx / npx / /path/to/bin" value="' + c(cfg.command || '') + '"/>' +
    '<label class="form-label">Args</label>' +
    '<input class="mcp-fld-args form-input-sm" type="text" placeholder="例如：your-mcp-package -y，或 JSON 数组" value="' + c(formatArgsList(cfg.args)) + '"/>' +
    '<label class="form-label">工作目录 cwd（可选）</label>' +
    '<input class="mcp-fld-cwd form-input-sm" type="text" value="' + c(cfg.cwd || '') + '"/>' +
    '</div>' +

    // ---- 远程连接字段组（SSE + Streamable HTTP 共用 URL 与 headers） ----
    '<div class="mcp-remote-fields mcp-field-group"' + remoteVis + '>' +
    '<div class="mcp-field-group__label">远程连接配置</div>' +
    '<label class="form-label">Endpoint URL</label>' +
    '<input class="mcp-fld-url form-input-sm" type="text" placeholder="http://host:port/mcp" value="' + c(cfg.url || '') + '"/>' +
    '<label class="form-label">Headers <span class="form-hint">（每行 KEY=value，用于 Authorization 等认证）</span></label>' +
    '<textarea class="mcp-fld-headers form-input-sm" rows="3" placeholder="Authorization=Bearer xxx&#10;X-API-Key=yyy" style="font-family:var(--font-mono);font-size:var(--fs-sm);">' + c(formatEnvLines(cfg.headers)) + '</textarea>' +
    '<div class="form-hint" style="margin-top:var(--sp-1);">' +
      (isSse
        ? '⚠ SSE 协议已废弃（Spec 2024-11-05），建议改用 Streamable HTTP（Spec 2025-06-18）。'
        : (isStreamable
          ? 'Streamable HTTP 自动携带 <code>MCP-Protocol-Version: 2025-11-25</code> 头，无需手动填写。'
          : '')) +
    '</div>' +
    '</div>' +

    // ---- 环境变量 ----
    '<div class="mcp-field-group">' +
    '<div class="mcp-field-group__label">环境变量</div>' +
    '<textarea class="mcp-fld-env form-input-sm" rows="4" placeholder="KEY=value&#10;每行一个" style="font-family:var(--font-mono);font-size:var(--fs-sm);">' + c(formatEnvLines(cfg.env)) + '</textarea>' +
    '</div>' +
    '</div>'
  );
}

function mcpMinimaxFormHtml(cfg, meta) {
  meta = meta || {};
  cfg = cfg || {};
  const env = cfg.env || {};
  const c = function(v) { return escAttr(v || ''); };
  return (
    '<input type="hidden" class="mcp-fld-kind" value="minimax"/>' +

    '<div class="mcp-form-section">' +
    '<label class="checkbox-row" style="margin:0 0 var(--sp-2);">' +
    '<input type="checkbox" class="mcp-fld-enabled"' + (cfg.enabled !== false ? ' checked' : '') + '/>' +
    '<span>启用 MiniMax MCP</span></label>' +

    '<div class="mcp-field-group">' +
    '<div class="mcp-field-group__label">密钥</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">Token Plan API Key</label>' +
    '  <input class="mcp-fld-minimax-key form-input-sm" type="password" value="' + c(env.MINIMAX_API_KEY || '') + '" autocomplete="off"/>' +
    '</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">朗读 API Key（可选）</label>' +
    '  <input class="mcp-fld-minimax-tts-key form-input-sm" type="password" value="' + c(env.MINIMAX_TTS_API_KEY || '') + '" autocomplete="off"/>' +
    '</div>' +
    '</div>' +

    '<div class="mcp-field-group">' +
    '<div class="mcp-field-group__label">高级选项</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">API Host</label>' +
    '  <input class="mcp-fld-minimax-host form-input-sm" type="text" value="' + c(env.MINIMAX_API_HOST || 'https://api.minimaxi.com') + '"/>' +
    '</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">uvx 路径</label>' +
    '  <input class="mcp-fld-minimax-uvx form-input-sm" type="text" value="' + c(cfg.command || meta.uvx_path || 'uvx') + '"/>' +
    '</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">本地输出目录</label>' +
    '  <input class="mcp-fld-minimax-base form-input-sm" type="text" value="' + c(env.MINIMAX_MCP_BASE_PATH || meta.minimax_output_dir || '') + '"/>' +
    '</div>' +
    '<div class="form-row sub-row">' +
    '  <label class="form-label">资源模式</label>' +
    '  <select class="mcp-fld-minimax-mode md-select" style="max-width:200px;">' +
    '    <option value=""' + (!env.MINIMAX_API_RESOURCE_MODE ? ' selected' : '') + '>默认</option>' +
    '    <option value="url"' + (env.MINIMAX_API_RESOURCE_MODE === 'url' ? ' selected' : '') + '>url</option>' +
    '    <option value="local"' + (env.MINIMAX_API_RESOURCE_MODE === 'local' ? ' selected' : '') + '>local</option>' +
    '  </select>' +
    '</div>' +
    '</div>' +
    '</div>'
  );
}

/* ---- Transport 切换 ---- */

/** Toggle stdio/sse/streamable-http field visibility + update hint. */
function mcpToggleTransport(sel) {
  var wrap = sel.closest('.mcp-card-wrap') || sel.closest('.mcp-edit-wrap');
  if (!wrap) return;
  var stdioFields = wrap.querySelector('.mcp-stdio-fields');
  var remoteFields = wrap.querySelector('.mcp-remote-fields');
  if (!stdioFields || !remoteFields) return;
  if (sel.value === 'stdio') {
    stdioFields.style.display = '';
    remoteFields.style.display = 'none';
  } else {
    // 'sse' or 'streamable-http'
    stdioFields.style.display = 'none';
    remoteFields.style.display = '';
  }
}

/* ---- 采集器 ---- */

function collectGenericServerFromWrap(wrap) {
  const id = (wrap.querySelector('.mcp-fld-id') || {}).value.trim();
  if (!validateMcpServerId(id)) throw new Error('服务 ID 无效（字母开头，仅含字母数字 _ -）');
  const enabled = !!(wrap.querySelector('.mcp-fld-enabled') || {}).checked;
  const transport = (wrap.querySelector('.mcp-fld-transport') || {}).value || 'stdio';
  const env = parseEnvLines((wrap.querySelector('.mcp-fld-env') || {}).value);

  if (transport === 'sse' || transport === 'streamable-http') {
    const url = (wrap.querySelector('.mcp-fld-url') || {}).value.trim();
    const headers = parseEnvLines((wrap.querySelector('.mcp-fld-headers') || {}).value);
    if (enabled && !url) throw new Error('服务「' + id + '」：' + transport + ' 模式请填写 URL');
    if (!enabled && !url) return null;
    const row = { enabled: enabled, transport: transport, url: url, env: env };
    if (Object.keys(headers).length > 0) row.headers = headers;
    return { id: id, config: row };
  }

  // stdio
  const command = (wrap.querySelector('.mcp-fld-command') || {}).value.trim();
  const args = parseArgsText((wrap.querySelector('.mcp-fld-args') || {}).value);
  const cwd = (wrap.querySelector('.mcp-fld-cwd') || {}).value.trim();
  if (!enabled && !command) return null;
  if (enabled && !command) throw new Error('服务「' + id + '」：请填写 command');
  const row = { enabled: enabled, transport: 'stdio', command: command, args: args, env: env };
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
    config: { enabled: enabled, transport: 'stdio', command: uvx, args: ['minimax-coding-plan-mcp', '-y'], env: env },
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
