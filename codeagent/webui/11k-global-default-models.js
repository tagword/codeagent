/* ================================================================
 * 11k-global-default-models.js
 *   Wires the "全局默认模型栈" fieldset in the env config panel.
 *   Backed entirely by localStorage (no backend persistence).
 * ================================================================ */

(function initGlobalDefaultModels() {
  const GRID = document.getElementById('globalDefaultGrid');
  if (!GRID || !window.ModelStackState) return;

  const SLOT_TO_FILTER = {
    llm:       function(p){ return p.use_type === 'chat' || p.use_type === 'llm' || p.supports_chat; },
    vision:    function(p){ return p.supports_vision === true; },
    image_gen: function(p){ return p.supports_image_gen === true; },
    audio:     function(p){ return p.supports_audio === true; },
    music:     function(p){ return p.supports_music === true; },
    video_gen: function(p){ return p.supports_video_gen === true; },
  };
  const SLOT_TO_LABEL = {
    llm: '（主对话）', vision: '（多模态/识图）', image_gen: '（生图）',
    audio: '（音频）', music: '（音乐）', video_gen: '（视频）',
  };

  async function fetchPresets() {
    try {
      const r = await fetch('/api/ui/llm/presets');
      if (!r.ok) return { presets: [], default_id: '' };
      return await r.json();
    } catch (_) { return { presets: [], default_id: '' }; }
  }

  function fillSelect(sel, presets, currentVal) {
    if (!sel) return;
    const slot = sel.getAttribute('data-slot');
    const filter = SLOT_TO_FILTER[slot] || function() { return true; };
    const suitable = (presets || []).filter(filter);
    // Always show all presets (with a category hint) so user can still pick
    // something unusual if they want; but mark unsuitable ones.
    sel.innerHTML = '';
    const def = document.createElement('option');
    def.value = '';
    def.textContent = '跟随系统默认';
    sel.appendChild(def);
    (presets || []).forEach(function(p) {
      const o = document.createElement('option');
      o.value = p.id || '';
      const suitableTag = filter(p) ? '' : ' · (非典型)';
      o.textContent = (p.name || p.model || p.id) + ' · ' + (p.provider_label || '') + SLOT_TO_LABEL[slot] + suitableTag;
      sel.appendChild(o);
    });
    if (currentVal && Array.from(sel.options).some(function(o){ return o.value === currentVal; })) {
      sel.value = currentVal;
    } else {
      sel.value = '';
    }
  }

  function loadIntoUi() {
    const MS = window.ModelStackState;
    const slots = MS.SLOTS;
    slots.forEach(function(slot) {
      const sel = document.getElementById(
        slot === 'llm' ? 'globalDefaultLlm'
        : slot === 'vision' ? 'globalDefaultVision'
        : slot === 'image_gen' ? 'globalDefaultImageGen'
        : slot === 'audio' ? 'globalDefaultAudio'
        : slot === 'music' ? 'globalDefaultMusic'
        : slot === 'video_gen' ? 'globalDefaultVideoGen'
        : null
      );
      if (sel) sel.value = MS.getGlobalDefault(slot) || '';
    });
  }

  function readFromUi() {
    const MS = window.ModelStackState;
    const out = {};
    MS.SLOTS.forEach(function(slot) {
      const id = slot === 'llm' ? 'globalDefaultLlm'
        : slot === 'vision' ? 'globalDefaultVision'
        : slot === 'image_gen' ? 'globalDefaultImageGen'
        : slot === 'audio' ? 'globalDefaultAudio'
        : slot === 'music' ? 'globalDefaultMusic'
        : slot === 'video_gen' ? 'globalDefaultVideoGen'
        : null;
      const sel = id ? document.getElementById(id) : null;
      if (sel) out[slot] = sel.value || '';
    });
    return out;
  }

  function setStatus(el, text, kind) {
    if (!el) return;
    el.textContent = text || '';
    el.className = 'status-line' + (kind ? ' status-line--' + kind : '');
  }

  async function refresh() {
    const j = await fetchPresets();
    const MS = window.ModelStackState;
    MS.SLOTS.forEach(function(slot) {
      const sel = document.getElementById(
        slot === 'llm' ? 'globalDefaultLlm'
        : slot === 'vision' ? 'globalDefaultVision'
        : slot === 'image_gen' ? 'globalDefaultImageGen'
        : slot === 'audio' ? 'globalDefaultAudio'
        : slot === 'music' ? 'globalDefaultMusic'
        : slot === 'video_gen' ? 'globalDefaultVideoGen'
        : null
      );
      fillSelect(sel, j.presets || [], MS.getGlobalDefault(slot));
    });
  }

  // Save
  const saveBtn = document.getElementById('btnGlobalDefaultSave');
  if (saveBtn) {
    saveBtn.addEventListener('click', function() {
      const values = readFromUi();
      window.ModelStackState.setAllGlobalDefaults(values);
      setStatus(document.getElementById('globalDefaultStatus'),
        '已保存。后续新建的会话将以此为默认。', 'ok');
      // Refresh any open chat panel so the pill reflects new defaults
      if (typeof window.refreshModelStackUi === 'function') {
        window.refreshModelStackUi();
      }
    });
  }

  // Reset
  const resetBtn = document.getElementById('btnGlobalDefaultReset');
  if (resetBtn) {
    resetBtn.addEventListener('click', function() {
      if (!confirm('重置全部 6 个全局默认模型为「跟随系统默认」吗？')) return;
      const empty = {};
      window.ModelStackState.SLOTS.forEach(function(s) { empty[s] = ''; });
      window.ModelStackState.setAllGlobalDefaults(empty);
      loadIntoUi();
      setStatus(document.getElementById('globalDefaultStatus'), '已重置。', 'ok');
      if (typeof window.refreshModelStackUi === 'function') {
        window.refreshModelStackUi();
      }
    });
  }

  // First paint
  document.addEventListener('DOMContentLoaded', function() {
    loadIntoUi();
    refresh().then(loadIntoUi);
  });
  if (document.readyState !== 'loading') {
    loadIntoUi();
    refresh().then(loadIntoUi);
  }

  // Expose for external refresh
  window.refreshGlobalDefaultModelsUi = function() {
    loadIntoUi();
    return refresh().then(loadIntoUi);
  };
})();
