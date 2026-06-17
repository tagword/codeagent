/* ================================================================
 * 11f-env-llm-a-state.js
 *   LLM Presets 状态层：
 *     - 常量（use_type 标签、self-hosted provider、board 空态提示）
 *     - 模块级状态（llmDefaultId / llmProviderCatalog / window._llmPresetsCache）
 *     - provider 目录加载（ensureProviderCatalog / getProviderEntry / listProviderModelsGrouped）
 *     - use_type 推断与 capability 提示
 *
 *   不依赖 11f-env-llm-b/c 任何文件；下游 form/board 依赖本文件的全部
 *   exports。所有顶层声明按 var 域或 window.*，靠文件名字母序加载。
 * ================================================================ */

let llmDefaultId = '';
let llmProviderCatalog = [];
window._llmPresetsCache = [];

var PRESET_USE_TYPE_LABELS = { chat: '对话', image: '生图', vision: '识图', audio: '音频', speech: '朗读', music: '音乐', video_gen: '视频生成' };
var PRESET_USE_TYPE_ORDER = ['chat', 'vision', 'image', 'audio', 'music', 'video_gen', 'speech'];
var SELF_HOSTED_PROVIDERS = ['ollama', 'openai_compatible', 'sglang', 'custom'];

var PRESET_BOARD_EMPTY_HINTS = {
  chat: '添加主对话模型（如 DeepSeek、本地 Qwen）',
  vision: '添加识图模型（如 GPT-4o、本地 LLaVA）用于图片附件',
  image: '添加生图模型，供 image_generate 工具调用',
  audio: '添加音频转写模型（如 Whisper）',
  music: '添加 MiniMax music-2.6 等音乐生成模型',
  video_gen: '添加 Agnes agnes-video-v2.0 等视频生成模型',
  speech: '朗读 preset 供参考；气泡 TTS 优先用 MCP 按量 Key',
};

function providerLabel(presetOrId) {
  if (presetOrId && typeof presetOrId === 'object') {
    if (presetOrId.provider_label) return presetOrId.provider_label;
    return providerLabel(presetOrId.provider_stored || presetOrId.provider || '');
  }
  const pid = (presetOrId || '').trim();
  if (!pid) return '自动推断';
  const p = llmProviderCatalog.find(function(x) { return x.id === pid; });
  return p ? (p.label || p.id) : pid;
}

async function ensureProviderCatalog() {
  if (llmProviderCatalog.length) return;
  try {
    const r = await fetch('/api/ui/llm/providers');
    if (!r.ok) return;
    const j = await r.json();
    llmProviderCatalog = j.providers || [];
  } catch (_) {}
}

function inferPresetUseType(p) {
  if (!p) return 'chat';
  if (p.use_type) return p.use_type;
  if (p.supports_image_gen) return 'image';
  if (p.supports_audio) return 'audio';
  if (p.supports_speech) return 'speech';
  if (p.supports_music) return 'music';
  if (p.supports_video_gen) return 'video_gen';
  if (p.supports_vision) return 'vision';
  return 'chat';
}

function getProviderEntry(providerId) {
  return llmProviderCatalog.find(function(x) { return x.id === providerId; }) || null;
}

function providerNeedsManualConnection(providerId) {
  return SELF_HOSTED_PROVIDERS.indexOf(providerId) >= 0;
}

function listProviderModelsGrouped(providerId, useType) {
  const entry = getProviderEntry(providerId);
  if (!entry || !entry.models || typeof entry.models !== 'object') return [];
  const ut = (useType || 'chat').trim();
  const groups = entry.models[ut] || entry.models.chat || entry.models.default || [];
  if (!Array.isArray(groups)) return [];
  const rows = [];
  groups.forEach(function(m) {
    if (typeof m === 'string') {
      rows.push({ id: m, label: m, useType: ut });
    } else if (m && m.id) {
      rows.push({ id: String(m.id), label: m.label || m.id, useType: m.use_type || ut });
    }
  });
  return rows;
}

function inferUseTypeForProviderModel(providerId, modelId) {
  const groups = ['chat', 'vision', 'image', 'audio', 'music', 'video_gen', 'speech'];
  for (let i = 0; i < groups.length; i++) {
    const rows = listProviderModelsGrouped(providerId, groups[i]);
    if (rows.some(function(r) { return r.id === modelId; })) return groups[i];
  }
  return 'chat';
}

function presetUseTypeLabel(p) {
  if (!p) return '对话';
  const ut = p.use_type_label || PRESET_USE_TYPE_LABELS[inferPresetUseType(p)] || inferPresetUseType(p);
  return ut || '对话';
}

function presetCapabilityHint(providerId, useType) {
  const pid = (providerId || '').trim();
  const ut = (useType || 'chat').trim();
  if (pid === 'minimax') {
    if (ut === 'music') return '将用于 music_generate 工具；与聊天/生图/朗读共用 MiniMax API Key。';
    if (ut === 'speech') return '朗读模型列表供 TTS 参考；气泡朗读优先使用 MCP 或按量 Key。';
    if (ut === 'image') return '将用于 image_generate 工具；与聊天/音乐/朗读共用 MiniMax API Key。';
    if (ut === 'chat') return '主对话模型；同一 Key 也可用于 TTS（若无单独 MCP Key）。';
  }
  if (ut === 'image') return '将用于 image_generate 工具。';
  if (ut === 'vision') return '将用于 vision_analyze / 发送图片附件。';
  if (ut === 'audio') return '将用于 audio_transcribe / 发送音频附件。';
  if (ut === 'music') return '将用于 music_generate 工具（当前仅 MiniMax）。';
  if (ut === 'video_gen') return '将用于 video_generate 工具（Agnes agnes-video-v2.0）。';
  if (ut === 'speech') return '供朗读模型参考；气泡 TTS 使用 MCP / 按量 Key。';
  return '主 Agent 对话与工具路由的默认 LLM。';
}

function resolvePresetProviderId(p) {
  if (!p) return 'deepseek';
  const stored = (p.provider_stored || p.provider || '').trim();
  if (stored && stored !== 'custom') return stored;
  const effective = (p.provider_effective || '').trim();
  if (effective && effective !== 'openai_compatible') return effective;
  const url = (p.base_url || '').toLowerCase();
  if (url.indexOf('api.deepseek.com') >= 0) return 'deepseek';
  if (url.indexOf('minimaxi.com') >= 0 || url.indexOf('minimax.io') >= 0) return 'minimax';
  if (url.indexOf('agnes-ai.com') >= 0) return 'agnes';
  if (url.indexOf('volces.com') >= 0 || url.indexOf('volcengine') >= 0) return 'volcengine';
  if (url.indexOf('api.openai.com') >= 0) return 'openai';
  if (url.indexOf('127.0.0.1') >= 0 || url.indexOf('localhost') >= 0) return 'ollama';
  return stored || effective || 'deepseek';
}
