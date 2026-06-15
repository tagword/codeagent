/* Audio transcription LLM selector — per-session via ModelStackState */

const AUDIO_MODEL_KEY = 'oa_audio_preset_id';  // legacy, kept for migration

function getSelectedAudioModel() {
  if (window.ModelStackState) return window.ModelStackState.getEffectiveModel('audio');
  try { return localStorage.getItem(AUDIO_MODEL_KEY) || ''; } catch (_) { return ''; }
}
function setSelectedAudioModel(val) {
  if (window.ModelStackState) {
    if (val && val !== '__none__') {
      window.ModelStackState.setSessionOverride('audio', val);
      window.ModelStackState.schedulePersistToBackend();
    } else {
      window.ModelStackState.clearSessionOverride('audio');
      window.ModelStackState.schedulePersistToBackend();
    }
    return;
  }
  try { localStorage.setItem(AUDIO_MODEL_KEY, String(val || '').trim()); } catch (_) {}
}

function hasAudioPresets() {
  return typeof _audioPresetsCache !== 'undefined' && _audioPresetsCache.length > 0;
}

function audioModelReadyForAttachments() {
  if (!hasAudioPresets()) return false;
  const v = getSelectedAudioModel();
  return !!v && v !== '__none__';
}

async function refreshAudioModelSelect() {
  const sel = document.getElementById('audioModelSelect');
  if (!sel) return;
  try {
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) return;
    const j = await r.json();
    const presets = (j.presets || []).filter(function(p) { return p.supports_audio === true; });
    window._audioPresetsCache = presets;
    const cur = getSelectedAudioModel();
    sel.innerHTML = '';
    if (!presets.length) {
      sel.disabled = true;
      const o = document.createElement('option');
      o.value = '';
      o.textContent = '未配置音频模型';
      sel.appendChild(o);
      if (typeof updateAttachmentUiGate === 'function') updateAttachmentUiGate();
      return;
    }
    sel.disabled = false;
    const ph = document.createElement('option');
    ph.value = '';
    ph.textContent = '— 音频转写 —';
    sel.appendChild(ph);
    presets.forEach(function(p) {
      const o = document.createElement('option');
      o.value = p.id || '';
      o.textContent = (p.name || p.model || p.id) + ' (音频)';
      sel.appendChild(o);
    });
    if (cur && presets.some(function(p) { return p.id === cur; })) {
      sel.value = cur;
    } else if (presets.length === 1) {
      sel.value = presets[0].id;
      setSelectedAudioModel(presets[0].id);
    }
    if (typeof updateAttachmentUiGate === 'function') updateAttachmentUiGate();
  } catch (_) {}
}

(function bindAudioModelSelect() {
  const sel = document.getElementById('audioModelSelect');
  if (!sel) return;
  sel.addEventListener('change', function() {
    setSelectedAudioModel(sel.value);
    if (typeof updateAttachmentUiGate === 'function') updateAttachmentUiGate();
  });
})();

if (typeof refreshImageGenModelSelect === 'function') {
  const _origRefreshImageGen = refreshImageGenModelSelect;
  refreshImageGenModelSelect = async function() {
    await _origRefreshImageGen();
    await refreshAudioModelSelect();
  };
} else if (typeof refreshVisionModelSelect === 'function') {
  const _origRefreshVisionAudio = refreshVisionModelSelect;
  refreshVisionModelSelect = async function() {
    await _origRefreshVisionAudio();
    await refreshAudioModelSelect();
  };
}

refreshAudioModelSelect().catch(function() {});
