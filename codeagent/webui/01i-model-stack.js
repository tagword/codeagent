/* Model stack: auto-select single presets + compose pill summary */

function truncateStackLabel(text, maxLen) {
  const s = String(text || '').trim();
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen - 1) + '…';
}

function presetShortLabel(p) {
  if (!p) return '';
  const model = (p.model_label || p.model || p.name || p.id || '').trim();
  const prov = (p.provider_label || p.provider || '').trim();
  if (model && prov) return model;
  return model || prov || p.id || '';
}

function getSelectShortLabel(sel) {
  if (!sel || sel.disabled) return '';
  const v = sel.value;
  if (!v || v === '__default__' || v === '__none__') return '';
  const opt = sel.options[sel.selectedIndex];
  if (!opt) return '';
  const t = (opt.textContent || '').trim();
  const m = t.match(/^(.+?)\s*[·(]/);
  return (m && m[1] ? m[1].trim() : t.split('(')[0].trim()) || v;
}

function autoSelectSinglePreset(sel, getVal, setVal, presets) {
  if (!sel || sel.disabled || !Array.isArray(presets) || presets.length !== 1) return;
  const only = presets[0];
  const pid = only && only.id;
  if (!pid) return;
  const cur = (typeof getVal === 'function' ? getVal() : '') || '';
  if (cur && cur !== '__none__') return;
  if (typeof setVal === 'function') setVal(pid);
  sel.value = pid;
}

function autoSelectModelStackPresets() {
  autoSelectSinglePreset(
    document.getElementById('visionModelSelect'),
    typeof getSelectedVisionModel === 'function' ? getSelectedVisionModel : null,
    typeof setSelectedVisionModel === 'function' ? setSelectedVisionModel : null,
    window._visionPresetsCache
  );
  autoSelectSinglePreset(
    document.getElementById('imageGenModelSelect'),
    typeof getSelectedImageGenModel === 'function' ? getSelectedImageGenModel : null,
    typeof setSelectedImageGenModel === 'function' ? setSelectedImageGenModel : null,
    window._imageGenPresetsCache
  );
  autoSelectSinglePreset(
    document.getElementById('audioModelSelect'),
    typeof getSelectedAudioModel === 'function' ? getSelectedAudioModel : null,
    typeof setSelectedAudioModel === 'function' ? setSelectedAudioModel : null,
    window._audioPresetsCache
  );
  autoSelectSinglePreset(
    document.getElementById('musicModelSelect'),
    typeof getSelectedMusicModel === 'function' ? getSelectedMusicModel : null,
    typeof setSelectedMusicModel === 'function' ? setSelectedMusicModel : null,
    window._musicPresetsCache
  );
  autoSelectSinglePreset(
    document.getElementById('videoGenModelSelect'),
    typeof getSelectedVideoGenModel === 'function' ? getSelectedVideoGenModel : null,
    typeof setSelectedVideoGenModel === 'function' ? setSelectedVideoGenModel : null,
    window._videoGenPresetsCache
  );

  const chatSel = document.getElementById('modelSelect');
  if (chatSel && !chatSel.disabled) {
    const chatPresets = (window._llmPresetsCache || []).filter(function(p) {
      return typeof inferPresetUseType === 'function' && inferPresetUseType(p) === 'chat';
    });
    const cur = typeof getSelectedModel === 'function' ? getSelectedModel() : '';
    if (!cur && chatPresets.length === 1 && chatPresets[0].id) {
      chatSel.value = chatPresets[0].id;
      if (typeof setSelectedModel === 'function') setSelectedModel(chatPresets[0].id);
    }
  }
}

function updateComposeStackMissingHint() {
  const hint = document.getElementById('composeStackMissingHint');
  if (!hint) return;
  const checks = [
    { sel: document.getElementById('visionModelSelect'), cache: window._visionPresetsCache },
    { sel: document.getElementById('imageGenModelSelect'), cache: window._imageGenPresetsCache },
    { sel: document.getElementById('audioModelSelect'), cache: window._audioPresetsCache },
    { sel: document.getElementById('musicModelSelect'), cache: window._musicPresetsCache },
    { sel: document.getElementById('videoGenModelSelect'), cache: window._videoGenPresetsCache },
  ];
  let anyMissing = false;
  checks.forEach(function(c) {
    if (Array.isArray(c.cache) && c.cache.length === 0) anyMissing = true;
  });
  hint.hidden = !anyMissing;
}

function updateComposeModelStackPill() {
  const pill = document.getElementById('composeModelPillLabel');
  const pin = document.getElementById('composeModelPillPin');
  const trigger = document.getElementById('composeModelTrigger');
  const chatSel = document.getElementById('modelSelect');
  if (!pill || !chatSel) return;

  const parts = [];
  const main = getSelectShortLabel(chatSel) || '默认模型';
  parts.push(main);

  const visionSel = document.getElementById('visionModelSelect');
  const visionLabel = getSelectShortLabel(visionSel);
  if (visionLabel) parts.push('识图 ' + visionLabel);

  const imageSel = document.getElementById('imageGenModelSelect');
  const imageLabel = getSelectShortLabel(imageSel);
  if (imageLabel) parts.push('生图 ' + imageLabel);

  const audioSel = document.getElementById('audioModelSelect');
  const audioLabel = getSelectShortLabel(audioSel);
  if (audioLabel) parts.push('音频 ' + audioLabel);

  const musicSel = document.getElementById('musicModelSelect');
  const musicLabel = getSelectShortLabel(musicSel);
  if (musicLabel) parts.push('音乐 ' + musicLabel);

  const videoGenSel = document.getElementById('videoGenModelSelect');
  const videoGenLabel = getSelectShortLabel(videoGenSel);
  if (videoGenLabel) parts.push('视频 ' + videoGenLabel);

  const summary = parts.join(' · ');
  const display = truncateStackLabel(summary, 42);
  pill.textContent = display;
  pill.title = summary;
  if (trigger) trigger.title = '模型栈：' + summary;

  // Per-session override pin badge + "clear overrides" button visibility
  let hasOverride = false;
  if (window.ModelStackState) {
    const slots = window.ModelStackState.listSessionOverrideSlots();
    hasOverride = slots.length > 0;
  }
  if (pin) {
    pin.hidden = !hasOverride;
    pin.setAttribute('aria-hidden', hasOverride ? 'false' : 'true');
    if (hasOverride) pin.title = '本会话已自定义模型（按 session 隔离）';
  }
  const clearBtn = document.getElementById('composeClearOverridesBtn');
  if (clearBtn) clearBtn.hidden = !hasOverride;
  const hint = document.getElementById('composeStackActionsHint');
  if (hint) {
    hint.textContent = hasOverride
      ? '当前会话已自定义以下模型：切到别的会话不会受影响。'
      : '当前会话未自定义：使用全局默认。';
  }
}

function refreshComposeModelStackUi() {
  autoSelectModelStackPresets();
  updateComposeStackMissingHint();
  if (typeof updateComposeModelPill === 'function') {
    updateComposeModelPill();
  } else {
    updateComposeModelStackPill();
  }
}

(function initModelStackUi() {
  ['modelSelect', 'visionModelSelect', 'imageGenModelSelect', 'audioModelSelect', 'musicModelSelect', 'videoGenModelSelect'].forEach(function(id) {
    const sel = document.getElementById(id);
    if (!sel) return;
    sel.addEventListener('change', function() {
      updateComposeModelStackPill();
      updateComposeStackMissingHint();
    });
  });

  document.addEventListener('DOMContentLoaded', function() {
    refreshComposeModelStackUi();
  });
  if (document.readyState !== 'loading') {
    setTimeout(refreshComposeModelStackUi, 0);
  }

  // Bind "clear all overrides" button (only meaningful when MS is available)
  const clearBtn = document.getElementById('composeClearOverridesBtn');
  if (clearBtn) {
    clearBtn.addEventListener('click', async function() {
      if (!window.ModelStackState) return;
      const sid = window.ModelStackState.getModelStackScope();
      if (!sid) return;
      if (!confirm('清除当前会话的所有模型覆盖吗？将恢复为全局默认。')) return;
      window.ModelStackState.clearAllSessionOverrides(sid);
      // Persist (empty) to backend
      try { await window.ModelStackState.persistToBackendNow(); } catch (_) {}
      // Re-apply selectors
      if (typeof window.refreshModelStackUi === 'function') {
        window.refreshModelStackUi();
      } else {
        refreshComposeModelStackUi();
      }
    });
  }
})();
