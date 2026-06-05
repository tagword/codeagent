/* ================================================================
 * 11h-env-mcp-b-form.js
 *   MCP server 表单 HTML 构造 + 收集器。
 *   依赖：a-state.js 的 isMinimaxMcpServer / MINIMAX_MCP_ID / validateMcpServerId / parseArgsText。
 *   上游依赖：00-utils.js（escAttr）。
 * ================================================================ */

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
