/* ================================================================
 * 11f-env-llm-c-board.js
 *   LLM Preset 看板与网络层：
 *     - 渲染 (renderPresetBoard)：按 use_type 分组展示所有 preset
 *     - 网络 (loadLlmPresets)：拉 /api/ui/llm/presets 写回缓存
 *     - 卡片 (buildPresetCard)：单条 preset 的卡片 + 展开/编辑
 *     - 新建 (showNewPresetForm)：点 + 添加 时插入临时表单
 *     - init IIFE：DOMContentLoaded 时绑定 + 首次加载
 *
 *   依赖 11f-env-llm-a-state.js (inferPresetUseType / llmDefaultId /
 *     PRESET_USE_TYPE_LABELS / PRESET_USE_TYPE_ORDER /
 *     PRESET_BOARD_EMPTY_HINTS / providerLabel / resolvePresetProviderId)
 *        11f-env-llm-b-form.js (presetFormHtml / wirePresetForm /
 *     wirePresetSaveAndTest / setSelectedUseType /
 *     syncPresetFormFromProvider / refreshPresetCopyFromOptions /
 *     updatePresetCapabilityHint / presetCardTitle)
 *   上游依赖：00-utils.js (escapeHtml)。
 * ================================================================ */

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
