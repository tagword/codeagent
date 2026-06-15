/* Image-gen LLM selector — per-session via ModelStackState */

const IMAGE_GEN_MODEL_KEY = 'oa_image_gen_preset_id';  // legacy, kept for migration

function getSelectedImageGenModel() {
  if (window.ModelStackState) return window.ModelStackState.getEffectiveModel('image_gen');
  try { return localStorage.getItem(IMAGE_GEN_MODEL_KEY) || ''; } catch (_) { return ''; }
}
function setSelectedImageGenModel(val) {
  if (window.ModelStackState) {
    if (val && val !== '__none__') {
      window.ModelStackState.setSessionOverride('image_gen', val);
      window.ModelStackState.schedulePersistToBackend();
    } else {
      window.ModelStackState.clearSessionOverride('image_gen');
      window.ModelStackState.schedulePersistToBackend();
    }
    return;
  }
  try { localStorage.setItem(IMAGE_GEN_MODEL_KEY, String(val || '').trim()); } catch (_) {}
}

async function refreshImageGenModelSelect() {
  const sel = document.getElementById('imageGenModelSelect');
  if (!sel) return;
  try {
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) return;
    const j = await r.json();
    const presets = (j.presets || []).filter(function(p) { return p.supports_image_gen === true; });
    window._imageGenPresetsCache = presets;
    const cur = getSelectedImageGenModel();
    sel.innerHTML = '';
    if (!presets.length) {
      sel.disabled = true;
      const o = document.createElement('option');
      o.value = '';
      o.textContent = '未配置生图模型';
      sel.appendChild(o);
      return;
    }
    sel.disabled = false;
    const ph = document.createElement('option');
    ph.value = '';
    ph.textContent = '— 生图模型 —';
    sel.appendChild(ph);
    presets.forEach(function(p) {
      const o = document.createElement('option');
      o.value = p.id || '';
      o.textContent = (p.name || p.model || p.id) + ' (生图)';
      sel.appendChild(o);
    });
    if (cur && presets.some(function(p) { return p.id === cur; })) {
      sel.value = cur;
    } else if (presets.length === 1) {
      sel.value = presets[0].id;
      setSelectedImageGenModel(presets[0].id);
    }
  } catch (_) {}
}

(function bindImageGenModelSelect() {
  const sel = document.getElementById('imageGenModelSelect');
  if (!sel) return;
  sel.addEventListener('change', function() {
    setSelectedImageGenModel(sel.value);
  });
})();

const _origRefreshVisionForImageGen = typeof refreshModelSelect === 'function' ? refreshModelSelect : null;
if (typeof refreshVisionModelSelect === 'function') {
  const _origRefreshVision = refreshVisionModelSelect;
  refreshVisionModelSelect = async function() {
    await _origRefreshVision();
    await refreshImageGenModelSelect();
  };
} else if (_origRefreshVisionForImageGen) {
  refreshModelSelect = async function() {
    await _origRefreshVisionForImageGen();
    await refreshImageGenModelSelect();
  };
}

refreshImageGenModelSelect().catch(function() {});
