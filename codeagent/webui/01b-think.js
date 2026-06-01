
/* Chat main LLM selector — now per-session (delegates to ModelStackState) */

function getSelectedModel() {
  // 1) session override, 2) global default, 3) empty
  if (window.ModelStackState) return window.ModelStackState.getEffectiveModel('llm');
  try { return localStorage.getItem('oa_llm_preset_id') || ''; } catch (_) { return ''; }
}
function setSelectedModel(val) {
  if (window.ModelStackState) {
    if (val && val !== '__default__') {
      window.ModelStackState.setSessionOverride('llm', val);
      window.ModelStackState.schedulePersistToBackend();
    } else {
      window.ModelStackState.clearSessionOverride('llm');
      window.ModelStackState.schedulePersistToBackend();
    }
    return;
  }
  try { localStorage.setItem('oa_llm_preset_id', String(val || '').trim()); } catch (_) {}
}
async function refreshModelSelect() {
  if (!modelSelect) return;
  // Effective value (session override → global default → empty)
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
    } else {
      modelSelect.value = '__default__';
    }
    if (typeof updateComposeModelPill === 'function') updateComposeModelPill();
  } catch (_) {}
}
const refreshChatModelSelect = refreshModelSelect;
modelSelect && modelSelect.addEventListener('change', function() {
  setSelectedModel(modelSelect.value);
  if (typeof updateComposeModelPill === 'function') updateComposeModelPill();
});

// ---------------- Thinking toggle persistence ----------------
