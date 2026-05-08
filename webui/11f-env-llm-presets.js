// ---------------- LLM Presets management (multi-model) ----------------
// Each preset card has an inline edit form below it + "设为默认" button.

let llmDefaultId = '';

async function loadLlmPresets() {
  const list = document.getElementById('llmPresetList');
  const status = document.getElementById('llmPresetStatus');
  if (!list) return;
  if (status) status.classList.remove('is-err');
  try {
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const j = await r.json();
    const presets = j.presets || [];
    llmDefaultId = j.default_id || '';
    list.innerHTML = '';
    if (presets.length === 0) {
      list.innerHTML = '<div class="preset-empty">暂无预设，点击 "+ 新增预设" 添加。</div>';
      return;
    }
    presets.forEach(function(p) { list.appendChild(buildPresetCard(p)); });
    if (status) {
      status.classList.remove('is-err');
      status.textContent = '共 ' + presets.length + ' 个预设';
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

  // --- Header bar ---
  const header = document.createElement('div');
  header.className = 'preset-card';

  const info = document.createElement('div');
  info.className = 'preset-card__info';

  const nameRow = document.createElement('div');
  nameRow.className = 'preset-card__name';
  nameRow.textContent = p.name || p.id || '未命名';
  if (isDefault) {
    const badge = document.createElement('span');
    badge.className = 'preset-card__badge';
    badge.textContent = '默认';
    nameRow.appendChild(badge);
  }

  const detail = document.createElement('div');
  detail.className = 'preset-card__detail';
  detail.textContent = (p.model || '') + ' @ ' + (p.base_url || '');
  const keyHint = p.api_key ? ' [已配置 Key]' : ' [无 Key]';
  detail.textContent += keyHint;

  info.appendChild(nameRow);
  info.appendChild(detail);

  const actions = document.createElement('div');
  actions.className = 'preset-card__actions';

  if (!isDefault) {
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
          body: JSON.stringify({ preset_id: p.id })
        });
        const dj = await dr.json().catch(function() { return {}; });
        if (!dr.ok) throw new Error(dj.detail || dr.statusText);
        await loadLlmPresets();
        refreshChatModelSelect();
      } catch (e) {
        const status = document.getElementById('llmPresetStatus');
        if (status) { status.classList.add('is-err'); status.textContent = String(e); }
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
    if (!confirm('确定删除预设「' + (p.name || p.id) + '」？')) return;
    try {
      const dr = await fetch('/api/ui/llm/presets/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ preset_id: p.id })
      });
      const dj = await dr.json().catch(function() { return {}; });
      if (!dr.ok) throw new Error(dj.detail || dr.statusText);
      await loadLlmPresets();
      refreshChatModelSelect();
    } catch (e) {
      const status = document.getElementById('llmPresetStatus');
      if (status) { status.classList.add('is-err'); status.textContent = String(e); }
    }
  });
  actions.appendChild(btnDel);

  header.appendChild(info);
  header.appendChild(actions);

  // --- Inline edit form (collapsible) ---
  const editWrap = document.createElement('div');
  editWrap.className = 'preset-edit-wrap';
  editWrap.style.display = 'none';

  const editStatus = document.createElement('div');
  editStatus.className = 'status-line';

  editWrap.innerHTML =
    '<label class="form-label">名称</label>' +
    '<input class="preset-fld-name" type="text" placeholder="我的 DeepSeek" value="' + escAttr(p.name || '') + '"/>' +
    '<label class="form-label">Base URL</label>' +
    '<input class="preset-fld-base" type="text" placeholder="https://api.deepseek.com/v1" value="' + escAttr(p.base_url || '') + '"/>' +
    '<label class="form-label">模型名称</label>' +
    '<input class="preset-fld-model" type="text" placeholder="deepseek-chat" value="' + escAttr(p.model || '') + '"/>' +
    '<label class="form-label">API Key（可选）</label>' +
    '<input class="preset-fld-key" type="password" placeholder="sk-..." value="' + escAttr(p.api_key || '') + '"/>' +
    '<label class="form-label">认证方案</label>' +
    '<select class="preset-fld-scheme md-select" style="max-width:100%;">' +
    '  <option' + (p.auth_scheme === 'Bearer' || !p.auth_scheme ? ' selected' : '') + '>Bearer</option>' +
    '  <option' + (p.auth_scheme === 'None' ? ' selected' : '') + '>None</option>' +
    '</select>' +
    '<div class="row-actions" style="margin-top: var(--sp-3);">' +
    '  <button type="button" class="btn btn--primary btn--sm preset-save-btn">保存</button>' +
    '  <button type="button" class="btn btn--ghost btn--sm preset-test-btn">测试连接</button>' +
    '  <button type="button" class="btn btn--subtle btn--sm preset-cancel-btn">取消</button>' +
    '</div>';

  editWrap.appendChild(editStatus);

  // --- Toggle edit (click the header) ---
  const toggleEdit = function(show) {
    editWrap.style.display = show ? 'block' : 'none';
    editStatus.textContent = '';
    editStatus.classList.remove('is-err');
  };
  header.style.cursor = 'pointer';
  header.addEventListener('click', function(e) {
    if (e.target.closest('.btn') || e.target.closest('.preset-card__actions')) return;
    toggleEdit(editWrap.style.display !== 'block');
  });

  // Wire up inline form buttons
  editWrap.querySelector('.preset-cancel-btn').addEventListener('click', function() { toggleEdit(false); });
  editWrap.querySelector('.preset-save-btn').addEventListener('click', async function() {
    const name = editWrap.querySelector('.preset-fld-name').value.trim();
    const base = editWrap.querySelector('.preset-fld-base').value.trim();
    const model = editWrap.querySelector('.preset-fld-model').value.trim();
    const key = editWrap.querySelector('.preset-fld-key').value.trim();
    const scheme = editWrap.querySelector('.preset-fld-scheme').value;
    if (!name) { editStatus.textContent = '名称不能为空'; editStatus.classList.add('is-err'); return; }
    if (!base) { editStatus.textContent = 'Base URL 不能为空'; editStatus.classList.add('is-err'); return; }
    if (!model) { editStatus.textContent = '模型名称不能为空'; editStatus.classList.add('is-err'); return; }
    editStatus.textContent = '保存中…';
    editStatus.classList.remove('is-err');
    try {
      const kv = {
        id: p.id,
        name: name,
        base_url: base,
        model: model,
        api_key: key,
        auth_scheme: scheme === 'None' ? '' : scheme,
      };
      const r = await fetch('/api/ui/llm/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(kv)
      });
      const j = await r.json().catch(function() { return {}; });
      if (!r.ok) throw new Error(j.detail || r.statusText);
      editStatus.textContent = '已保存。';
      toggleEdit(false);
      await loadLlmPresets();
      refreshChatModelSelect();
    } catch (e) {
      editStatus.classList.add('is-err');
      editStatus.textContent = String(e);
    }
  });
  editWrap.querySelector('.preset-test-btn').addEventListener('click', async function() {
    const base = editWrap.querySelector('.preset-fld-base').value.trim();
    const model = editWrap.querySelector('.preset-fld-model').value.trim();
    const key = editWrap.querySelector('.preset-fld-key').value.trim();
    const scheme = editWrap.querySelector('.preset-fld-scheme').value;
    editStatus.textContent = '测试中…';
    editStatus.classList.remove('is-err');
    try {
      const r = await fetch('/api/ui/llm/presets/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ base_url: base, model: model, api_key: key, auth_scheme: scheme || 'Bearer' })
      });
      const j = await r.json().catch(function() { return {}; });
      if (!r.ok) throw new Error(j.detail || r.statusText);
      editStatus.textContent = j.model_hint || '测试通过';
    } catch (e) {
      editStatus.classList.add('is-err');
      editStatus.textContent = String(e);
    }
  });

  wrap.appendChild(header);
  wrap.appendChild(editWrap);
  return wrap;
}


// --- New preset: render as a special card with inline form at the top ---
function showNewPresetForm() {
  const list = document.getElementById('llmPresetList');
  if (!list) return;
  // Collapse any existing new-preset form first
  const existing = list.querySelector('.preset-card-wrap.is-new');
  if (existing) { existing.remove(); }

  const wrap = document.createElement('div');
  wrap.className = 'preset-card-wrap is-new';

  const editWrap = document.createElement('div');
  editWrap.className = 'preset-edit-wrap';
  editWrap.style.display = 'block';
  const editStatus = document.createElement('div');
  editStatus.className = 'status-line';

  editWrap.innerHTML =
    '<label class="form-label">名称</label>' +
    '<input class="preset-fld-name" type="text" placeholder="我的 DeepSeek"/>' +
    '<label class="form-label">Base URL</label>' +
    '<input class="preset-fld-base" type="text" placeholder="https://api.deepseek.com/v1"/>' +
    '<label class="form-label">模型名称</label>' +
    '<input class="preset-fld-model" type="text" placeholder="deepseek-chat"/>' +
    '<label class="form-label">API Key（可选）</label>' +
    '<input class="preset-fld-key" type="password" placeholder="sk-..."/>' +
    '<label class="form-label">认证方案</label>' +
    '<select class="preset-fld-scheme md-select" style="max-width:100%;">' +
    '  <option selected>Bearer</option><option>None</option>' +
    '</select>' +
    '<div class="row-actions" style="margin-top: var(--sp-3);">' +
    '  <button type="button" class="btn btn--primary btn--sm preset-save-btn">保存</button>' +
    '  <button type="button" class="btn btn--ghost btn--sm preset-test-btn">测试连接</button>' +
    '  <button type="button" class="btn btn--subtle btn--sm preset-cancel-btn">取消</button>' +
    '</div>';
  editWrap.appendChild(editStatus);

  editWrap.querySelector('.preset-cancel-btn').addEventListener('click', function() { wrap.remove(); });
  editWrap.querySelector('.preset-save-btn').addEventListener('click', async function() {
    const name = editWrap.querySelector('.preset-fld-name').value.trim();
    const base = editWrap.querySelector('.preset-fld-base').value.trim();
    const model = editWrap.querySelector('.preset-fld-model').value.trim();
    const key = editWrap.querySelector('.preset-fld-key').value.trim();
    const scheme = editWrap.querySelector('.preset-fld-scheme').value;
    if (!name) { editStatus.textContent = '名称不能为空'; editStatus.classList.add('is-err'); return; }
    if (!base) { editStatus.textContent = 'Base URL 不能为空'; editStatus.classList.add('is-err'); return; }
    if (!model) { editStatus.textContent = '模型名称不能为空'; editStatus.classList.add('is-err'); return; }
    editStatus.textContent = '保存中…';
    editStatus.classList.remove('is-err');
    try {
      const id = name.replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
      const kv = { id: id, name: name, base_url: base, model: model, api_key: key, auth_scheme: scheme === 'None' ? '' : scheme };
      const r = await fetch('/api/ui/llm/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(kv)
      });
      const j = await r.json().catch(function() { return {}; });
      if (!r.ok) throw new Error(j.detail || r.statusText);
      wrap.remove();
      await loadLlmPresets();
      refreshChatModelSelect();
    } catch (e) {
      editStatus.classList.add('is-err');
      editStatus.textContent = String(e);
    }
  });
  editWrap.querySelector('.preset-test-btn').addEventListener('click', async function() {
    const base = editWrap.querySelector('.preset-fld-base').value.trim();
    const model = editWrap.querySelector('.preset-fld-model').value.trim();
    const key = editWrap.querySelector('.preset-fld-key').value.trim();
    const scheme = editWrap.querySelector('.preset-fld-scheme').value;
    editStatus.textContent = '测试中…';
    editStatus.classList.remove('is-err');
    try {
      const r = await fetch('/api/ui/llm/presets/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ base_url: base, model: model, api_key: key, auth_scheme: scheme || 'Bearer' })
      });
      const j = await r.json().catch(function() { return {}; });
      if (!r.ok) throw new Error(j.detail || r.statusText);
      editStatus.textContent = j.model_hint || '测试通过';
    } catch (e) {
      editStatus.classList.add('is-err');
      editStatus.textContent = String(e);
    }
  });

  wrap.appendChild(editWrap);
  // Insert at the top
  if (list.firstChild) { list.insertBefore(wrap, list.firstChild); }
  else { list.appendChild(wrap); }
}

(function () {
  var a = document.getElementById('btnLlmPresetAdd');
  var r = document.getElementById('btnLlmPresetRefresh');
  if (a) a.addEventListener('click', showNewPresetForm);
  if (r) r.addEventListener('click', function () { loadLlmPresets(); });
})();

