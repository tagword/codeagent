
const MODEL_KEY = 'oa_llm_preset_id';
function getSelectedModel() {
  try { return localStorage.getItem(MODEL_KEY) || ''; } catch (_) { return ''; }
}
function setSelectedModel(val) {
  try { localStorage.setItem(MODEL_KEY, String(val || '').trim()); } catch (_) {}
}
async function refreshModelSelect() {
  if (!modelSelect) return;
  const cur = getSelectedModel();
  try {
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) return;
    const j = await r.json();
    const presets = (j.presets || []).filter(function(p) {
      return inferPresetUseType(p) === 'chat';
    });
    const defaultId = j.default_id || '';
    modelSelect.innerHTML = '<option value="__default__">默认模型</option>';
    presets.forEach(function(p) {
      const o = document.createElement('option');
      o.value = p.id || '';
      let label = p.name || p.model || p.id;
      const prov = (p.provider_label || '').trim();
      const ut = (p.use_type_label || '').trim();
      const mdl = (p.model_label || p.model || '').trim();
      if (prov) label += ' · ' + prov;
      if (ut) label += ' · ' + ut;
      if (mdl && mdl !== label) label += ' · ' + mdl;
      if (p.id === defaultId) label += ' （默认）';
      o.textContent = label;
      modelSelect.appendChild(o);
    });
    if (cur && cur !== '__default__' && presets.some(function(p) { return p.id === cur; })) {
      modelSelect.value = cur;
    } else if (defaultId && presets.some(function(p) { return p.id === defaultId; })) {
      modelSelect.value = defaultId;
      setSelectedModel(defaultId);
    } else {
      modelSelect.value = '__default__';
      setSelectedModel('');
    }
    if (typeof updateComposeModelPill === 'function') updateComposeModelPill();
  } catch (_) {}
}
const refreshChatModelSelect = refreshModelSelect;
modelSelect && modelSelect.addEventListener('change', function() {
  setSelectedModel(modelSelect.value);
});

// ---------------- Thinking toggle persistence ----------------
