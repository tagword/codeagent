// ---------------- LLM Presets management (multi-model) ----------------
// Capability-first forms + grouped board by use_type.

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
  return SELF_HOSTED_PROVIDERS.indexOf((providerId || '').trim()) >= 0;
}

function listProviderModelsGrouped(providerId, useType) {
  const prov = getProviderEntry(providerId);
  const caps = (prov && prov.capabilities && prov.capabilities.length)
    ? prov.capabilities
    : ['chat'];
  const rows = [];
  caps.forEach(function(cap) {
    if (useType && cap !== useType) return;
    const models = (prov && prov.models && prov.models[cap]) ? prov.models[cap] : [];
    const group = PRESET_USE_TYPE_LABELS[cap] || cap;
    models.forEach(function(m) {
      rows.push({
        id: m.id,
        label: m.label || m.id,
        useType: cap,
        group: group,
      });
    });
  });
  return rows;
}

function inferUseTypeForProviderModel(providerId, modelId) {
  const mid = String(modelId || '').trim();
  if (!mid) return 'chat';
  const rows = listProviderModelsGrouped(providerId);
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].id === mid) return rows[i].useType;
  }
  const low = mid.toLowerCase();
  if (providerId === 'minimax' && low.startsWith('music')) return 'music';
  if (providerId === 'agnes' && low.indexOf('video') >= 0) return 'video_gen';
  if (providerId === 'minimax' && low.startsWith('speech')) return 'speech';
  if (providerId === 'minimax' && low.startsWith('image')) return 'image';
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

function setSelectValue(sel, value) {
  if (!sel || value == null || value === '') return;
  sel.value = value;
  if (sel.value !== value) {
    for (let i = 0; i < sel.options.length; i++) {
      if (sel.options[i].value === value) {
        sel.selectedIndex = i;
        break;
      }
    }
  }
}

function presetAutoId(provider, model) {
  const raw = ((provider || 'custom').trim() || 'custom') + '_' + ((model || '').trim() || 'default');
  return raw
    .replace(/[^a-zA-Z0-9\u4e00-\u9fff_-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .toLowerCase() || 'preset';
}

function presetCardTitle(p) {
  if (!p) return '未命名';
  const prov = providerLabel(p);
  const model = (p.model_label || p.model || '').trim();
  return model ? prov + ' · ' + model : prov;
}

function presetProviderOptionsHtml(selectedId, includeCustom) {
  let opts = '';
  llmProviderCatalog.forEach(function(prov) {
    if (prov.id === 'custom' && !includeCustom) return;
    const sel = prov.id === selectedId ? ' selected' : '';
    opts += '<option value="' + escAttr(prov.id) + '">' + escAttr(prov.label || prov.id) + '</option>';
  });
  return opts;
}

function presetUseTypeSegmentHtml(selectedUseType) {
  const cur = (selectedUseType || 'chat').trim();
  let html = '<div class="preset-use-type-seg" role="group" aria-label="用途">';
  PRESET_USE_TYPE_ORDER.forEach(function(ut) {
    const label = PRESET_USE_TYPE_LABELS[ut] || ut;
    const active = ut === cur ? ' is-active' : '';
    html += '<button type="button" class="preset-use-type-seg__btn' + active + '" data-use-type="' + escAttr(ut) + '">' + escAttr(label) + '</button>';
  });
  html += '</div>';
  return html;
}

function getSelectedUseType(editWrap) {
  if (!editWrap) return 'chat';
  const active = editWrap.querySelector('.preset-use-type-seg__btn.is-active');
  return (active && active.getAttribute('data-use-type')) || 'chat';
}

function setSelectedUseType(editWrap, useType) {
  if (!editWrap) return;
  const ut = (useType || 'chat').trim();
  editWrap.querySelectorAll('.preset-use-type-seg__btn').forEach(function(btn) {
    btn.classList.toggle('is-active', btn.getAttribute('data-use-type') === ut);
  });
}

function presetFormHtml(p) {
  p = p || {};
  const provider = resolvePresetProviderId(p);
  const useType = inferPresetUseType(p);
  const manualConn = providerNeedsManualConnection(provider);
  const authNone = !p.auth_scheme || p.auth_scheme === 'None' || p.auth_scheme === '';
  return (
    '<label class="form-label">用途</label>' +
    presetUseTypeSegmentHtml(useType) +
    '<label class="form-label">服务商</label>' +
    '<select class="preset-fld-provider md-select" style="max-width:100%;">' +
    presetProviderOptionsHtml(provider, true) +
    '</select>' +
    '<div class="preset-catalog-fields"' + (manualConn ? ' style="display:none;"' : '') + '>' +
    '  <label class="form-label">模型</label>' +
    '  <select class="preset-fld-model-id md-select" style="max-width:100%;"></select>' +
    '  <div class="preset-manual-model-row" style="display:none;">' +
    '    <label class="form-label">模型名称（手动）</label>' +
    '    <input class="preset-fld-model-manual" type="text" placeholder="模型 id，如 qwen2.5:7b"/>' +
    '  </div>' +
    '</div>' +
    '<div class="preset-connection-fields"' + (manualConn ? '' : ' style="display:none;"') + '>' +
    '  <label class="form-label">Base URL</label>' +
    '  <input class="preset-fld-base" type="text" placeholder="http://127.0.0.1:11434/v1" value="' + escAttr(p.base_url || '') + '"/>' +
    '  <label class="form-label">模型名称</label>' +
    '  <input class="preset-fld-model" type="text" placeholder="服务端 model id" value="' + escAttr(p.model || '') + '"/>' +
    '  <label class="form-label">认证</label>' +
    '  <select class="preset-fld-scheme md-select" style="max-width:100%;">' +
    '    <option' + (!authNone ? ' selected' : '') + '>Bearer</option>' +
    '    <option' + (authNone ? ' selected' : '') + '>None</option>' +
    '  </select>' +
    '</div>' +
    '<label class="form-label">API Key</label>' +
    '<input class="preset-fld-key" type="password" placeholder="本地部署可留空" value="' + escAttr(p.api_key || '') + '"/>' +
    '<div class="preset-copy-row">' +
    '  <label class="form-label">复制连接</label>' +
    '  <select class="preset-fld-copy-from md-select" style="max-width:100%;"><option value="">从已有预设复制 Base URL / Key…</option></select>' +
    '</div>' +
    '<p class="form-hint preset-capability-hint" style="margin:var(--sp-2) 0 0;"></p>' +
    '<div class="row-actions" style="margin-top: var(--sp-3);">' +
    '  <button type="button" class="btn btn--primary btn--sm preset-save-btn">保存</button>' +
    '  <button type="button" class="btn btn--ghost btn--sm preset-test-btn">测试连接</button>' +
    '  <button type="button" class="btn btn--subtle btn--sm preset-cancel-btn">取消</button>' +
    '</div>'
  );
}

function syncPresetConnectionVisibility(editWrap) {
  if (!editWrap) return;
  const prov = (editWrap.querySelector('.preset-fld-provider') || {}).value || 'deepseek';
  const manual = providerNeedsManualConnection(prov);
  const catalog = editWrap.querySelector('.preset-catalog-fields');
  const connection = editWrap.querySelector('.preset-connection-fields');
  if (catalog) catalog.style.display = manual ? 'none' : '';
  if (connection) connection.style.display = manual ? 'block' : 'none';
  if (manual && prov !== 'custom') {
    const spec = getProviderEntry(prov);
    const baseInp = editWrap.querySelector('.preset-fld-base');
    if (baseInp && !baseInp.value.trim() && spec && spec.default_base_url) {
      baseInp.value = spec.default_base_url;
    }
  }
}

function refreshPresetCopyFromOptions(editWrap) {
  const sel = editWrap && editWrap.querySelector('.preset-fld-copy-from');
  if (!sel) return;
  const curId = editWrap.getAttribute('data-preset-id') || '';
  const presets = window._llmPresetsCache || [];
  sel.innerHTML = '<option value="">从已有预设复制 Base URL / Key…</option>';
  presets.forEach(function(p) {
    if (!p || !p.id || p.id === curId) return;
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = presetCardTitle(p) + ' · ' + presetUseTypeLabel(p);
    sel.appendChild(opt);
  });
}

function applyConnectionFromPreset(editWrap, source) {
  if (!editWrap || !source) return;
  const provSel = editWrap.querySelector('.preset-fld-provider');
  if (provSel) {
    setSelectValue(provSel, resolvePresetProviderId(source));
  }
  const baseInp = editWrap.querySelector('.preset-fld-base');
  const modelInp = editWrap.querySelector('.preset-fld-model');
  const keyInp = editWrap.querySelector('.preset-fld-key');
  const schemeSel = editWrap.querySelector('.preset-fld-scheme');
  if (baseInp) baseInp.value = source.base_url || '';
  if (modelInp && !modelInp.value.trim()) modelInp.value = source.model || '';
  if (keyInp && !keyInp.value.trim()) keyInp.value = source.api_key || '';
  if (schemeSel) {
    const none = !source.auth_scheme || source.auth_scheme === 'None';
    schemeSel.value = none ? 'None' : 'Bearer';
  }
  syncPresetConnectionVisibility(editWrap);
  syncPresetFormFromProvider(editWrap, {
    providerId: resolvePresetProviderId(source),
    modelId: source.model || '',
  });
  updatePresetCapabilityHint(editWrap);
}

function refreshPresetModelOptions(editWrap, providerId, selectedModelId, useType) {
  const sel = editWrap.querySelector('.preset-fld-model-id');
  const manualRow = editWrap.querySelector('.preset-manual-model-row');
  const manualInp = editWrap.querySelector('.preset-fld-model-manual');
  if (!sel) return;
  const ut = useType || getSelectedUseType(editWrap);
  const rows = listProviderModelsGrouped(providerId, ut);
  sel.innerHTML = '';
  if (!rows.length) {
    sel.style.display = 'none';
    if (manualRow) manualRow.style.display = 'block';
    if (manualInp && selectedModelId) manualInp.value = selectedModelId;
    return;
  }
  sel.style.display = '';
  if (manualRow) manualRow.style.display = 'none';
  rows.forEach(function(row) {
    const opt = document.createElement('option');
    opt.value = row.id;
    opt.textContent = row.label;
    opt.setAttribute('data-use-type', row.useType);
    if (row.id === selectedModelId) opt.selected = true;
    sel.appendChild(opt);
  });
  if (!sel.value && sel.options.length) sel.selectedIndex = 0;
}

function syncPresetFormFromProvider(editWrap, initial) {
  initial = initial || {};
  const provSel = editWrap.querySelector('.preset-fld-provider');
  const pid = initial.providerId || (provSel && provSel.value) || 'deepseek';
  if (initial.useType) setSelectedUseType(editWrap, initial.useType);
  if (provSel) setSelectValue(provSel, pid);
  syncPresetConnectionVisibility(editWrap);
  refreshPresetModelOptions(editWrap, pid, initial.modelId || '', getSelectedUseType(editWrap));
  const modelSel = editWrap.querySelector('.preset-fld-model-id');
  if (modelSel && initial.modelId) setSelectValue(modelSel, initial.modelId);
  updatePresetCapabilityHint(editWrap);
}

function getFormModelName(editWrap) {
  const prov = (editWrap.querySelector('.preset-fld-provider') || {}).value || 'deepseek';
  if (providerNeedsManualConnection(prov)) {
    return (editWrap.querySelector('.preset-fld-model') || {}).value.trim();
  }
  const modelSel = editWrap.querySelector('.preset-fld-model-id');
  const manual = (editWrap.querySelector('.preset-fld-model-manual') || {}).value.trim();
  if (modelSel && modelSel.style.display !== 'none') return modelSel.value;
  return manual;
}

function formUsesManualConnection(editWrap) {
  const prov = (editWrap.querySelector('.preset-fld-provider') || {}).value || 'deepseek';
  if (providerNeedsManualConnection(prov)) return true;
  const rows = listProviderModelsGrouped(prov, getSelectedUseType(editWrap));
  return rows.length === 0;
}

function updatePresetCapabilityHint(editWrap) {
  const hint = editWrap && editWrap.querySelector('.preset-capability-hint');
  if (!hint) return;
  const prov = (editWrap.querySelector('.preset-fld-provider') || {}).value || 'deepseek';
  const useType = getSelectedUseType(editWrap);
  const cap = PRESET_USE_TYPE_LABELS[useType] || useType;
  const extra = presetCapabilityHint(prov, useType);
  hint.textContent = extra ? ('能力：' + cap + ' — ' + extra) : ('能力：' + cap);
}

function collectPresetPayload(editWrap, presetId) {
  const provider = (editWrap.querySelector('.preset-fld-provider') || {}).value.trim();
  const key = (editWrap.querySelector('.preset-fld-key') || {}).value.trim();
  const useType = getSelectedUseType(editWrap);
  const manualConn = formUsesManualConnection(editWrap);
  const schemeSel = editWrap.querySelector('.preset-fld-scheme');
  const scheme = schemeSel ? schemeSel.value : 'Bearer';

  if (manualConn) {
    const model = (editWrap.querySelector('.preset-fld-model') || {}).value.trim()
      || getFormModelName(editWrap);
    const prov = provider || 'custom';
    return {
      id: presetId || presetAutoId(prov, model),
      provider: prov,
      use_type: useType,
      base_url: (editWrap.querySelector('.preset-fld-base') || {}).value.trim(),
      model: model,
      api_key: key,
      auth_scheme: scheme === 'None' ? '' : scheme,
      advanced: true,
    };
  }

  const model = getFormModelName(editWrap);
  return {
    id: presetId || presetAutoId(provider, model),
    provider: provider,
    use_type: useType,
    model: model,
    api_key: key,
    auth_scheme: 'Bearer',
  };
}

function wirePresetForm(editWrap, p) {
  p = p || {};
  if (p.id) editWrap.setAttribute('data-preset-id', p.id);
  setSelectedUseType(editWrap, inferPresetUseType(p));

  syncPresetFormFromProvider(editWrap, {
    providerId: resolvePresetProviderId(p),
    modelId: p.model || '',
    useType: inferPresetUseType(p),
  });
  refreshPresetCopyFromOptions(editWrap);

  const provSel = editWrap.querySelector('.preset-fld-provider');
  if (provSel) {
    provSel.addEventListener('change', function() {
      syncPresetConnectionVisibility(editWrap);
      syncPresetFormFromProvider(editWrap, { useType: getSelectedUseType(editWrap) });
    });
  }

  editWrap.querySelectorAll('.preset-use-type-seg__btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      setSelectedUseType(editWrap, btn.getAttribute('data-use-type'));
      syncPresetFormFromProvider(editWrap, { useType: getSelectedUseType(editWrap) });
    });
  });

  const modelSel = editWrap.querySelector('.preset-fld-model-id');
  const manualInp = editWrap.querySelector('.preset-fld-model-manual');
  const connModelInp = editWrap.querySelector('.preset-fld-model');
  if (modelSel) modelSel.addEventListener('change', function() { updatePresetCapabilityHint(editWrap); });
  if (manualInp) manualInp.addEventListener('input', function() { updatePresetCapabilityHint(editWrap); });
  if (connModelInp) connModelInp.addEventListener('input', function() { updatePresetCapabilityHint(editWrap); });

  const copySel = editWrap.querySelector('.preset-fld-copy-from');
  if (copySel) {
    copySel.addEventListener('change', function() {
      const pid = copySel.value;
      if (!pid) return;
      const src = (window._llmPresetsCache || []).find(function(x) { return x.id === pid; });
      if (src) applyConnectionFromPreset(editWrap, src);
      copySel.value = '';
    });
  }

  updatePresetCapabilityHint(editWrap);
}

function wirePresetSaveAndTest(editWrap, editStatus, options) {
  options = options || {};
  const presetId = options.presetId || '';

  editWrap.querySelector('.preset-save-btn').addEventListener('click', async function() {
    const kv = collectPresetPayload(editWrap, presetId);
    if (!kv.provider) {
      editStatus.textContent = '请选择服务商';
      editStatus.classList.add('is-err');
      return;
    }
    if (!kv.model) {
      editStatus.textContent = '请填写或选择模型';
      editStatus.classList.add('is-err');
      return;
    }
    if (kv.advanced && !kv.base_url) {
      editStatus.textContent = '请填写 Base URL';
      editStatus.classList.add('is-err');
      return;
    }
    editStatus.textContent = '保存中…';
    editStatus.classList.remove('is-err');
    try {
      const r = await fetch('/api/ui/llm/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(kv),
      });
      const j = await r.json().catch(function() { return {}; });
      if (!r.ok) throw new Error(j.detail || r.statusText);
      editStatus.textContent = '已保存。';
      if (options.onSaved) options.onSaved();
      await loadLlmPresets();
      if (typeof refreshMultimodalModelSelects === 'function') {
        await refreshMultimodalModelSelects();
      } else {
        refreshChatModelSelect();
        if (typeof refreshTtsOptions === 'function') refreshTtsOptions().catch(function() {});
      }
    } catch (e) {
      editStatus.classList.add('is-err');
      editStatus.textContent = String(e);
    }
  });

  editWrap.querySelector('.preset-test-btn').addEventListener('click', async function() {
    const kv = collectPresetPayload(editWrap, presetId);
    editStatus.textContent = '测试中…';
    editStatus.classList.remove('is-err');
    try {
      const r = await fetch('/api/ui/llm/presets/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(kv),
      });
      const j = await r.json().catch(function() { return {}; });
      if (!r.ok) throw new Error(j.detail || r.statusText);
      editStatus.textContent = j.model_hint || '测试通过';
    } catch (e) {
      editStatus.classList.add('is-err');
      editStatus.textContent = String(e);
    }
  });
}

function renderPresetBoard(presets) {
  const list = document.getElementById('llmPresetList');
  if (!list) return;
  list.innerHTML = '';
  list.className = 'preset-board';

  PRESET_USE_TYPE_ORDER.forEach(function(useType) {
    const section = document.createElement('section');
    section.className = 'preset-board-section';
    section.setAttribute('data-use-type', useType);

    const sectionPresets = presets.filter(function(p) {
      return inferPresetUseType(p) === useType;
    });

    const head = document.createElement('div');
    head.className = 'preset-board-section__head';
    const title = document.createElement('h4');
    title.className = 'preset-board-section__title';
    title.textContent = PRESET_USE_TYPE_LABELS[useType] || useType;
    const count = document.createElement('span');
    count.className = 'preset-board-section__count';
    count.textContent = String(sectionPresets.length);
    title.appendChild(count);

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'btn btn--ghost btn--xs preset-board-add';
    addBtn.textContent = '+ 添加' + (PRESET_USE_TYPE_LABELS[useType] || useType);
    addBtn.addEventListener('click', function() { showNewPresetForm(useType, section); });

    head.appendChild(title);
    head.appendChild(addBtn);
    section.appendChild(head);

    const body = document.createElement('div');
    body.className = 'preset-board-section__body';

    if (!sectionPresets.length) {
      const empty = document.createElement('p');
      empty.className = 'preset-board-section__empty';
      empty.textContent = PRESET_BOARD_EMPTY_HINTS[useType] || '暂无预设';
      body.appendChild(empty);
    } else {
      sectionPresets.forEach(function(p) {
        body.appendChild(buildPresetCard(p));
      });
    }

    section.appendChild(body);
    list.appendChild(section);
  });
}

async function loadLlmPresets() {
  const list = document.getElementById('llmPresetList');
  const status = document.getElementById('llmPresetStatus');
  if (!list) return;
  if (status) status.classList.remove('is-err');
  try {
    await ensureProviderCatalog();
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const j = await r.json();
    const presets = j.presets || [];
    window._llmPresetsCache = presets;
    window._llmDefaultId = j.default_id || '';
    llmDefaultId = j.default_id || '';
    if (j.providers && j.providers.length) llmProviderCatalog = j.providers;

    renderPresetBoard(presets);

    if (status) {
      status.classList.remove('is-err');
      status.textContent = '共 ' + presets.length + ' 个预设';
    }
    if (typeof refreshMultimodalModelSelects === 'function') {
      refreshMultimodalModelSelects().catch(function() {});
    }
  } catch (e) {
    if (status) {
      status.classList.add('is-err');
      status.textContent = '加载预设失败：' + String(e);
    }
  }
}

function buildPresetCard(p) {
  const wrap = document.createElement('div');
  wrap.className = 'preset-card-wrap';
  const isDefault = p.id === llmDefaultId;
  const useType = inferPresetUseType(p);

  const header = document.createElement('div');
  header.className = 'preset-card';

  const info = document.createElement('div');
  info.className = 'preset-card__info';

  const nameRow = document.createElement('div');
  nameRow.className = 'preset-card__name';
  nameRow.textContent = presetCardTitle(p);
  if (isDefault) {
    const badge = document.createElement('span');
    badge.className = 'preset-card__badge';
    badge.textContent = '默认';
    nameRow.appendChild(badge);
  }
  const provBadge = document.createElement('span');
  provBadge.className = 'preset-card__badge preset-card__badge--provider';
  provBadge.textContent = providerLabel(p);
  nameRow.appendChild(provBadge);

  const detail = document.createElement('div');
  detail.className = 'preset-card__detail';
  const modelTxt = (p.model_label || p.model || '').trim();
  const urlHint = (p.base_url || '').trim();
  detail.textContent = (modelTxt ? modelTxt + ' · ' : '') +
    (urlHint ? urlHint + ' · ' : '') +
    (p.api_key ? '已配置 Key' : '未配置 Key');

  info.appendChild(nameRow);
  info.appendChild(detail);

  const actions = document.createElement('div');
  actions.className = 'preset-card__actions';

  if (!isDefault && useType === 'chat') {
    const btnDefault = document.createElement('button');
    btnDefault.type = 'button';
    btnDefault.className = 'btn btn--ghost btn--xs';
    btnDefault.textContent = '设为默认';
    btnDefault.addEventListener('click', async function(ev) {
      ev.stopPropagation();
      try {
        const dr = await fetch('/api/ui/llm/presets/default', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ preset_id: p.id }),
        });
        const dj = await dr.json().catch(function() { return {}; });
        if (!dr.ok) throw new Error(dj.detail || dr.statusText);
        await loadLlmPresets();
        if (typeof refreshMultimodalModelSelects === 'function') {
          await refreshMultimodalModelSelects();
        } else {
          refreshChatModelSelect();
        }
      } catch (e) {
        const st = document.getElementById('llmPresetStatus');
        if (st) { st.classList.add('is-err'); st.textContent = String(e); }
      }
    });
    actions.appendChild(btnDefault);
  }

  const btnDel = document.createElement('button');
  btnDel.type = 'button';
  btnDel.className = 'btn btn--ghost btn--xs preset-del';
  btnDel.textContent = '删除';
  btnDel.addEventListener('click', async function(ev) {
    ev.stopPropagation();
    if (!confirm('确定删除预设「' + presetCardTitle(p) + '」？')) return;
    try {
      const dr = await fetch('/api/ui/llm/presets/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ preset_id: p.id }),
      });
      const dj = await dr.json().catch(function() { return {}; });
      if (!dr.ok) throw new Error(dj.detail || dr.statusText);
      await loadLlmPresets();
      if (typeof refreshMultimodalModelSelects === 'function') {
        await refreshMultimodalModelSelects();
      } else {
        refreshChatModelSelect();
        if (typeof refreshTtsOptions === 'function') refreshTtsOptions().catch(function() {});
      }
    } catch (e) {
      const st = document.getElementById('llmPresetStatus');
      if (st) { st.classList.add('is-err'); st.textContent = String(e); }
    }
  });
  actions.appendChild(btnDel);

  header.appendChild(info);
  header.appendChild(actions);

  const editWrap = document.createElement('div');
  editWrap.className = 'preset-edit-wrap';
  editWrap.style.display = 'none';

  const editStatus = document.createElement('div');
  editStatus.className = 'status-line';

  editWrap.innerHTML = presetFormHtml(p);
  editWrap.appendChild(editStatus);
  wirePresetForm(editWrap, p);

  const toggleEdit = function(show) {
    editWrap.style.display = show ? 'block' : 'none';
    editStatus.textContent = '';
    editStatus.classList.remove('is-err');
  };
  header.style.cursor = 'pointer';
  header.addEventListener('click', function(e) {
    if (e.target.closest('.btn') || e.target.closest('.preset-card__actions')) return;
    const opening = editWrap.style.display !== 'block';
    toggleEdit(opening);
    if (opening) {
      syncPresetFormFromProvider(editWrap, {
        providerId: resolvePresetProviderId(p),
        modelId: p.model || '',
        useType: inferPresetUseType(p),
      });
      refreshPresetCopyFromOptions(editWrap);
      updatePresetCapabilityHint(editWrap);
    }
  });

  editWrap.querySelector('.preset-cancel-btn').addEventListener('click', function() { toggleEdit(false); });
  wirePresetSaveAndTest(editWrap, editStatus, {
    presetId: p.id,
    onSaved: function() { toggleEdit(false); },
  });

  wrap.appendChild(header);
  wrap.appendChild(editWrap);
  return wrap;
}

function showNewPresetForm(preferredUseType, targetSection) {
  const list = document.getElementById('llmPresetList');
  if (!list) return;

  const existing = list.querySelector('.preset-card-wrap.is-new');
  if (existing) existing.remove();

  const useType = (preferredUseType || 'chat').trim();
  const wrap = document.createElement('div');
  wrap.className = 'preset-card-wrap is-new';

  const editWrap = document.createElement('div');
  editWrap.className = 'preset-edit-wrap';
  editWrap.style.display = 'block';
  const editStatus = document.createElement('div');
  editStatus.className = 'status-line';

  const seed = { provider: 'deepseek', provider_stored: 'deepseek', use_type: useType };
  if (useType === 'vision' || useType === 'image' || useType === 'audio') {
    seed.provider = 'ollama';
    seed.provider_stored = 'ollama';
  }

  editWrap.innerHTML = presetFormHtml(seed);
  editWrap.appendChild(editStatus);

  editWrap.querySelector('.preset-cancel-btn').addEventListener('click', function() { wrap.remove(); });
  wirePresetForm(editWrap, seed);
  wirePresetSaveAndTest(editWrap, editStatus, {
    onSaved: function() { wrap.remove(); },
  });

  wrap.appendChild(editWrap);

  if (targetSection) {
    const body = targetSection.querySelector('.preset-board-section__body');
    const empty = body && body.querySelector('.preset-board-section__empty');
    if (empty) empty.remove();
    if (body) body.insertBefore(wrap, body.firstChild);
    else list.insertBefore(wrap, list.firstChild);
  } else if (list.firstChild) {
    list.insertBefore(wrap, list.firstChild);
  } else {
    list.appendChild(wrap);
  }

  setSelectedUseType(editWrap, useType);
  syncPresetFormFromProvider(editWrap, { useType: useType, providerId: resolvePresetProviderId(seed) });
  wrap.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

(function () {
  var a = document.getElementById('btnLlmPresetAdd');
  var r = document.getElementById('btnLlmPresetRefresh');
  if (a) a.addEventListener('click', function() { showNewPresetForm('chat'); });
  if (r) r.addEventListener('click', function () { loadLlmPresets(); });
  loadLlmPresets();
})();
