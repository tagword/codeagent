const MUSIC_MODEL_KEY = 'oa_music_preset_id';

function getSelectedMusicModel() {
  try { return localStorage.getItem(MUSIC_MODEL_KEY) || ''; } catch (_) { return ''; }
}

function setSelectedMusicModel(val) {
  try { localStorage.setItem(MUSIC_MODEL_KEY, String(val || '').trim()); } catch (_) {}
}

async function refreshMusicModelSelect() {
  const sel = document.getElementById('musicModelSelect');
  if (!sel) return;
  try {
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) return;
    const j = await r.json();
    const presets = (j.presets || []).filter(function(p) { return p.supports_music === true; });
    window._musicPresetsCache = presets;
    const cur = getSelectedMusicModel();
    sel.innerHTML = '';
    if (!presets.length) {
      sel.disabled = true;
      const o = document.createElement('option');
      o.value = '';
      o.textContent = '未配置音乐模型';
      sel.appendChild(o);
      return;
    }
    sel.disabled = false;
    const ph = document.createElement('option');
    ph.value = '';
    ph.textContent = '— 音乐生成 —';
    sel.appendChild(ph);
    presets.forEach(function(p) {
      const o = document.createElement('option');
      o.value = p.id || '';
      const modelLabel = (p.model_label || p.model || p.id || '').trim();
      o.textContent = (p.name || modelLabel) + ' · ' + modelLabel + ' (音乐)';
      sel.appendChild(o);
    });
    if (cur && presets.some(function(p) { return p.id === cur; })) {
      sel.value = cur;
    } else if (presets.length === 1) {
      sel.value = presets[0].id;
      setSelectedMusicModel(presets[0].id);
    }
  } catch (_) {}
}

(function bindMusicModelSelect() {
  const sel = document.getElementById('musicModelSelect');
  if (!sel) return;
  sel.addEventListener('change', function() {
    setSelectedMusicModel(sel.value);
  });
})();

if (typeof refreshAudioModelSelect === 'function') {
  const _origRefreshAudioForMusic = refreshAudioModelSelect;
  refreshAudioModelSelect = async function() {
    await _origRefreshAudioForMusic();
    await refreshMusicModelSelect();
  };
} else if (typeof refreshImageGenModelSelect === 'function') {
  const _origRefreshImageGenForMusic = refreshImageGenModelSelect;
  refreshImageGenModelSelect = async function() {
    await _origRefreshImageGenForMusic();
    await refreshMusicModelSelect();
  };
}

refreshMusicModelSelect().catch(function() {});
