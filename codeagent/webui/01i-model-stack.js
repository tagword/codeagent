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

function stripModelPath(name) {
  const s = String(name || '').trim();
  if (!s) return '';
  const i = s.lastIndexOf('/');
  return (i >= 0 && i < s.length - 1) ? s.slice(i + 1) : s;
}

function findChatPresetById(id) {
  if (!id) return null;
  return (window._llmPresetsCache || []).find(function(p) {
    return p.id === id && (typeof inferPresetUseType !== 'function' || inferPresetUseType(p) === 'chat');
  }) || null;
}

function presetComposeLabel(p, opts) {
  if (!p) return '';
  opts = opts || {};
  let base = stripModelPath(presetShortLabel(p) || p.model || p.name || p.id || '');
  if (!base) return '';
  if (opts.isDefault) base += ' · 默认';
  return base;
}

function presetOptionDetail(p) {
  if (!p) return '';
  const parts = [];
  const name = (p.name || '').trim();
  const model = stripModelPath(p.model_label || p.model || '');
  const prov = (p.provider_label || p.provider || '').trim();
  if (name && name !== model) parts.push(name);
  if (model) parts.push(model);
  if (prov) parts.push(prov);
  const ut = (p.use_type_label || '').trim();
  if (ut) parts.push(ut);
  return parts.filter(Boolean).join(' · ') || String(p.id || '');
}

function getChatMainDisplayLabel(sel) {
  if (!sel || sel.disabled) return '默认模型';
  const v = sel.value;
  if (!v || v === '__default__') {
    const def = findChatPresetById(window._llmDefaultId || '');
    if (def) return presetComposeLabel(def, { isDefault: true });
    return '默认模型';
  }
  const preset = findChatPresetById(v);
  if (preset) {
    return presetComposeLabel(preset, { isDefault: preset.id === (window._llmDefaultId || '') });
  }
  return getSelectShortLabel(sel) || '默认模型';
}

function getSelectShortLabel(sel) {
  if (!sel || sel.disabled) return '';
  const v = sel.value;
  if (!v || v === '__default__' || v === '__none__') return '';

  const chatPreset = findChatPresetById(v);
  if (chatPreset) return stripModelPath(presetShortLabel(chatPreset) || chatPreset.model || chatPreset.id);

  const opt = sel.options[sel.selectedIndex];
  if (!opt) return stripModelPath(v);
  let t = (opt.textContent || '').trim().replace(/\s*（默认）\s*$/, '').replace(/\s*·\s*默认\s*$/, '');
  const parts = t.split(/\s*·\s*/).map(function(p) { return stripModelPath(p.trim()); }).filter(Boolean);
  if (!parts.length) return stripModelPath(v);

  const skip = /^(对话|chat|识图|生图|音频|音乐|视频|多模态)$/i;
  const modelish = parts.filter(function(p) { return p.includes('-') || p.includes('.'); });
  if (modelish.length) return modelish[0];
  const filtered = parts.filter(function(p) { return !skip.test(p); });
  if (filtered.length) {
    filtered.sort(function(a, b) { return a.length - b.length; });
    return filtered[0];
  }
  return parts[parts.length - 1] || stripModelPath(v);
}

function composePillMaxLen() {
  try {
    return window.matchMedia('(max-width: 768px)').matches ? 12 : 20;
  } catch (_) {
    return 20;
  }
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
  const extra = document.getElementById('composeModelPillExtra');
  const pin = document.getElementById('composeModelPillPin');
  const trigger = document.getElementById('composeModelTrigger');
  const chatSel = document.getElementById('modelSelect');
  if (!pill || !chatSel) return;

  const main = getChatMainDisplayLabel(chatSel);
  const extras = [];

  const visionLabel = getSelectShortLabel(document.getElementById('visionModelSelect'));
  if (visionLabel) extras.push('识图 ' + visionLabel);

  const imageLabel = getSelectShortLabel(document.getElementById('imageGenModelSelect'));
  if (imageLabel) extras.push('生图 ' + imageLabel);

  const audioLabel = getSelectShortLabel(document.getElementById('audioModelSelect'));
  if (audioLabel) extras.push('音频 ' + audioLabel);

  const musicLabel = getSelectShortLabel(document.getElementById('musicModelSelect'));
  if (musicLabel) extras.push('音乐 ' + musicLabel);

  const videoGenLabel = getSelectShortLabel(document.getElementById('videoGenModelSelect'));
  if (videoGenLabel) extras.push('视频 ' + videoGenLabel);

  const summary = [main].concat(extras).join(' · ');
  pill.textContent = truncateStackLabel(main, composePillMaxLen());
  pill.title = main;

  if (extra) {
    if (extras.length > 0) {
      extra.textContent = '+' + extras.length;
      extra.hidden = false;
      extra.setAttribute('aria-hidden', 'false');
      extra.title = extras.join('、');
    } else {
      extra.hidden = true;
      extra.setAttribute('aria-hidden', 'true');
      extra.textContent = '';
    }
  }

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

  window.addEventListener('resize', function() {
    if (typeof updateComposeModelStackPill === 'function') updateComposeModelStackPill();
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
