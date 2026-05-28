const VISION_MODEL_KEY = 'oa_vision_preset_id';

function getSelectedVisionModel() {
  try { return localStorage.getItem(VISION_MODEL_KEY) || ''; } catch (_) { return ''; }
}

function setSelectedVisionModel(val) {
  try { localStorage.setItem(VISION_MODEL_KEY, String(val || '').trim()); } catch (_) {}
}

function hasVisionPresets() {
  return typeof _visionPresetsCache !== 'undefined' && _visionPresetsCache.length > 0;
}

function visionModelReadyForAttachments() {
  if (!hasVisionPresets()) return false;
  const v = getSelectedVisionModel();
  return !!v && v !== '__none__';
}

async function refreshVisionModelSelect() {
  const sel = document.getElementById('visionModelSelect');
  if (!sel) return;
  try {
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) return;
    const j = await r.json();
    const presets = (j.presets || []).filter(function(p) { return p.supports_vision === true; });
    window._visionPresetsCache = presets;
    const cur = getSelectedVisionModel();
    sel.innerHTML = '';
    if (!presets.length) {
      sel.disabled = true;
      const o = document.createElement('option');
      o.value = '';
      o.textContent = '未配置多模态模型';
      sel.appendChild(o);
      updateAttachmentUiGate();
      return;
    }
    sel.disabled = false;
    const ph = document.createElement('option');
    ph.value = '';
    ph.textContent = '— 选择多模态模型 —';
    sel.appendChild(ph);
    presets.forEach(function(p) {
      const o = document.createElement('option');
      o.value = p.id || '';
      o.textContent = (p.name || p.model || p.id) + ' (多模态)';
      sel.appendChild(o);
    });
    if (cur && presets.some(function(p) { return p.id === cur; })) {
      sel.value = cur;
    } else if (presets.length === 1) {
      sel.value = presets[0].id;
      setSelectedVisionModel(presets[0].id);
    }
    updateAttachmentUiGate();
  } catch (_) {}
}

(function bindVisionModelSelect() {
  const sel = document.getElementById('visionModelSelect');
  if (!sel) return;
  sel.addEventListener('change', function() {
    setSelectedVisionModel(sel.value);
    updateAttachmentUiGate();
  });
})();

const _origRefreshModelSelect = typeof refreshModelSelect === 'function' ? refreshModelSelect : null;
refreshModelSelect = async function() {
  if (_origRefreshModelSelect) await _origRefreshModelSelect();
  await refreshVisionModelSelect();
};
