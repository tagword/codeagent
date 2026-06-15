/* Video-gen LLM selector — per-session via ModelStackState */

const VIDEO_GEN_MODEL_KEY = 'oa_video_gen_preset_id';  // legacy, kept for migration

function getSelectedVideoGenModel() {
  if (window.ModelStackState) return window.ModelStackState.getEffectiveModel('video_gen');
  try { return localStorage.getItem(VIDEO_GEN_MODEL_KEY) || ''; } catch (_) { return ''; }
}
function setSelectedVideoGenModel(val) {
  if (window.ModelStackState) {
    if (val && val !== '__none__') {
      window.ModelStackState.setSessionOverride('video_gen', val);
      window.ModelStackState.schedulePersistToBackend();
    } else {
      window.ModelStackState.clearSessionOverride('video_gen');
      window.ModelStackState.schedulePersistToBackend();
    }
    return;
  }
  try { localStorage.setItem(VIDEO_GEN_MODEL_KEY, String(val || '').trim()); } catch (_) {}
}

async function refreshVideoGenModelSelect() {
  const sel = document.getElementById('videoGenModelSelect');
  if (!sel) return;
  try {
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) return;
    const j = await r.json();
    const presets = (j.presets || []).filter(function(p) { return p.supports_video_gen === true; });
    window._videoGenPresetsCache = presets;
    const cur = getSelectedVideoGenModel();
    sel.innerHTML = '';
    if (!presets.length) {
      sel.disabled = true;
      const o = document.createElement('option');
      o.value = '';
      o.textContent = '未配置视频生成模型';
      sel.appendChild(o);
      return;
    }
    sel.disabled = false;
    const ph = document.createElement('option');
    ph.value = '';
    ph.textContent = '— 视频生成 —';
    sel.appendChild(ph);
    presets.forEach(function(p) {
      const o = document.createElement('option');
      o.value = p.id || '';
      const modelLabel = (p.model_label || p.model || p.id || '').trim();
      o.textContent = (p.name || modelLabel) + ' · ' + modelLabel + ' (视频生成)';
      sel.appendChild(o);
    });
    if (cur && presets.some(function(p) { return p.id === cur; })) {
      sel.value = cur;
    } else if (presets.length === 1) {
      sel.value = presets[0].id;
      setSelectedVideoGenModel(presets[0].id);
    }
  } catch (_) {}
}

(function bindVideoGenModelSelect() {
  const sel = document.getElementById('videoGenModelSelect');
  if (!sel) return;
  sel.addEventListener('change', function() {
    setSelectedVideoGenModel(sel.value);
  });
})();

if (typeof refreshMusicModelSelect === 'function') {
  const _origRefreshMusicForVideo = refreshMusicModelSelect;
  refreshMusicModelSelect = async function() {
    await _origRefreshMusicForVideo();
    await refreshVideoGenModelSelect();
  };
} else if (typeof refreshAudioModelSelect === 'function') {
  const _origRefreshAudioForVideo = refreshAudioModelSelect;
  refreshAudioModelSelect = async function() {
    await _origRefreshAudioForVideo();
    await refreshVideoGenModelSelect();
  };
}

refreshVideoGenModelSelect().catch(function() {});
