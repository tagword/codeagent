/* ================================================================
 * 11f-env-llm-b-form.js
 *   LLM Preset 编辑表单：
 *     - 标签/segment 构造
 *     - 整张表单 HTML（presetFormHtml）
 *     - 表单 ↔ 状态的双向同步（syncPresetConnectionVisibility /
 *       refreshPresetCopyFromOptions / applyConnectionFromPreset /
 *       refreshPresetModelOptions / syncPresetFormFromProvider）
 *     - 收集器（collectPresetPayload）
 *     - 事件绑定（wirePresetForm / wirePresetSaveAndTest）
 *
 *   依赖 11f-env-llm-a-state.js（按字母序保证加载）。
 *   上游依赖：00-utils.js (escAttr)。
 * ================================================================ */

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
    '<label class="form-label">最大输出 tokens</label>' +
    '<input class="preset-fld-max-tokens" type="number" min="256" max="65536" step="512" style="width:100%;" value="' + (p.max_tokens || 8192) + '"/>' +
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
  let maxTokens = parseInt((editWrap.querySelector('.preset-fld-max-tokens') || {}).value, 10);
  if (isNaN(maxTokens) || maxTokens < 256) maxTokens = 8192;
  if (maxTokens > 65536) maxTokens = 65536;
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
      max_tokens: maxTokens,
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
    max_tokens: maxTokens,
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
