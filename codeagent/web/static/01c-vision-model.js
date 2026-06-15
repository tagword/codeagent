/* Vision LLM selector — per-session via ModelStackState */

const VISION_MODEL_KEY = 'oa_vision_preset_id';  // legacy, kept for migration

function getSelectedVisionModel() {
  if (window.ModelStackState) return window.ModelStackState.getEffectiveModel('vision');
  try { return localStorage.getItem(VISION_MODEL_KEY) || ''; } catch (_) { return ''; }
}
function setSelectedVisionModel(val) {
  if (window.ModelStackState) {
    if (val && val !== '__none__') {
      window.ModelStackState.setSessionOverride('vision', val);
      window.ModelStackState.schedulePersistToBackend();
    } else {
      window.ModelStackState.clearSessionOverride('vision');
      window.ModelStackState.schedulePersistToBackend();
    }
    return;
  }
  try { localStorage.setItem(VISION_MODEL_KEY, String(val || '').trim()); } catch (_) {}
}
function clearSelectedVisionModel() { setSelectedVisionModel(''); }

function hasVisionPresets() {
  return typeof _visionPresetsCache !== 'undefined' && _visionPresetsCache.length > 0;
}

window._mcpImageReady = false;
window._mcpImageConfigured = false;

async function refreshMcpImageReady() {
  try {
    const r = await fetch('/api/ui/mcp');
    if (!r.ok) return;
    const j = await r.json();
    const iu = j.image_understanding || {};
    window._mcpImageConfigured = !!iu.configured;
    window._mcpImageReady = !!iu.configured;
    window._mcpVisionSentinel = iu.sentinel || '__mcp_minimax__';
  } catch (_) {}
}

function mcpImageReadyForAttachments() {
  return !!window._mcpImageReady;
}

function visionModelReadyForAttachments() {
  if (!hasVisionPresets()) return false;
  const v = getSelectedVisionModel();
  if (v === (window._mcpVisionSentinel || '__mcp_minimax__')) return false;
  return !!v && v !== '__none__';
}

function attachmentImageReady() {
  return visionModelReadyForAttachments() || mcpImageReadyForAttachments();
}

function attachmentVideoReady() {
  return visionModelReadyForAttachments();
}

async function refreshVisionModelSelect() {
  const sel = document.getElementById('visionModelSelect');
  if (!sel) return;
  await refreshMcpImageReady();
  try {
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) return;
    const j = await r.json();
    const presets = (j.presets || []).filter(function(p) { return p.supports_vision === true; });
    window._visionPresetsCache = presets;
    const cur = getSelectedVisionModel();
    const mcpSentinel = window._mcpVisionSentinel || '__mcp_minimax__';
    sel.innerHTML = '';
    if (!presets.length && !window._mcpImageConfigured) {
      sel.disabled = true;
      const o = document.createElement('option');
      o.value = '';
      o.textContent = '未配置多模态 / MCP 识图';
      sel.appendChild(o);
      updateAttachmentUiGate();
      return;
    }
    sel.disabled = false;
    const ph = document.createElement('option');
    ph.value = '';
    ph.textContent = '— 识图方式 —';
    sel.appendChild(ph);
    if (window._mcpImageConfigured) {
      const om = document.createElement('option');
      om.value = mcpSentinel;
      om.textContent = 'MiniMax MCP 识图 (understand_image)';
      sel.appendChild(om);
    }
    presets.forEach(function(p) {
      const o = document.createElement('option');
      o.value = p.id || '';
      o.textContent = (p.name || p.model || p.id) + ' (多模态 LLM)';
      sel.appendChild(o);
    });
    if (cur && (cur === mcpSentinel && window._mcpImageConfigured)) {
      sel.value = cur;
    } else if (cur && presets.some(function(p) { return p.id === cur; })) {
      sel.value = cur;
    } else if (!cur && window._mcpImageConfigured && !presets.length) {
      sel.value = mcpSentinel;
      setSelectedVisionModel(mcpSentinel);
    } else if (!cur && presets.length === 1) {
      sel.value = presets[0].id;
      setSelectedVisionModel(presets[0].id);
    } else if (!cur && window._mcpImageConfigured) {
      sel.value = mcpSentinel;
      setSelectedVisionModel(mcpSentinel);
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
