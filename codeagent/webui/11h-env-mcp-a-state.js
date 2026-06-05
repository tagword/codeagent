/* ================================================================
 * 11h-env-mcp-a-state.js
 *   MCP server 状态层：常量、缓存、arg/env 解析、状态行展示。
 *   不依赖任何其他 11h-env-mcp-* 文件（function declaration 全部 hoisted）。
 *   上游依赖：00-utils.js（escapeHtml / escAttr）、00-storage.js。
 * ================================================================ */

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
