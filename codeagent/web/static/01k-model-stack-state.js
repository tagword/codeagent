/* ================================================================
 * 01k-model-stack-state.js
 *   Per-session + global-default model selection state.
 *
 *   Three-level precedence (highest → lowest):
 *     1. session override  — oa_ms_over::session::<sid>::<slot>
 *     2. global default    — oa_ms_global::<slot>
 *     3. system default    — empty string (handled by server)
 *
 *   Also keeps the legacy keys in sync for one-shot migration (F7).
 * ================================================================ */

(function initModelStackState() {
  // Slot definitions: the 6 model types. Order is fixed.
  const SLOTS = ['llm', 'vision', 'image_gen', 'audio', 'music', 'video_gen'];

  // Legacy single-key names (pre per-session). Read on init to seed
  // session override once, then ignored.
  const LEGACY_KEYS = {
    llm:        'oa_llm_preset_id',
    vision:     'oa_vision_preset_id',
    image_gen:  'oa_image_gen_preset_id',
    audio:      'oa_audio_preset_id',
    music:      'oa_music_preset_id',
    video_gen:  'oa_video_gen_preset_id',
  };

  function safeGet(k) {
    try { return localStorage.getItem(k) || ''; } catch (_) { return ''; }
  }
  function safeSet(k, v) {
    try { localStorage.setItem(k, String(v == null ? '' : v).trim()); } catch (_) {}
  }
  function safeDel(k) {
    try { localStorage.removeItem(k); } catch (_) {}
  }

  // ---- Current session scope (driven by 01c-session.js) ----
  function getModelStackScope() {
    // sessionId is a `let` in 01c-session.js. Reading `typeof sessionId` in
    // TDZ would throw, so wrap in try. After TDZ, `typeof` returns 'undefined'
    // cleanly. We fall back to window.sessionId (which bootstrap module may set).
    try {
      if (typeof sessionId !== 'undefined' && sessionId) return String(sessionId);
    } catch (_) {}
    try {
      if (window.sessionId) return String(window.sessionId);
    } catch (_) {}
    return '';
  }

  // ---- Session-level override ----
  function sessionKey(sid, slot) {
    return 'oa_ms_over::session::' + (sid || 'default') + '::' + slot;
  }
  function getSessionOverride(slot, sid) {
    if (!SLOTS.includes(slot)) return '';
    return safeGet(sessionKey(sid || getModelStackScope(), slot));
  }
  function setSessionOverride(slot, val, sid) {
    if (!SLOTS.includes(slot)) return;
    safeSet(sessionKey(sid || getModelStackScope(), slot), val);
  }
  function clearSessionOverride(slot, sid) {
    if (!SLOTS.includes(slot)) return;
    safeDel(sessionKey(sid || getModelStackScope(), slot));
  }
  function clearAllSessionOverrides(sid) {
    const k = sid || getModelStackScope();
    SLOTS.forEach(function(s) { safeDel(sessionKey(k, s)); });
  }
  function listSessionOverrideSlots(sid) {
    const k = sid || getModelStackScope();
    return SLOTS.filter(function(s) { return !!safeGet(sessionKey(k, s)); });
  }

  // ---- Global default ----
  function getGlobalDefault(slot) {
    if (!SLOTS.includes(slot)) return '';
    return safeGet('oa_ms_global::' + slot);
  }
  function setGlobalDefault(slot, val) {
    if (!SLOTS.includes(slot)) return;
    safeSet('oa_ms_global::' + slot, val);
  }
  function getAllGlobalDefaults() {
    const out = {};
    SLOTS.forEach(function(s) { out[s] = getGlobalDefault(s); });
    return out;
  }
  function setAllGlobalDefaults(obj) {
    SLOTS.forEach(function(s) {
      if (obj && Object.prototype.hasOwnProperty.call(obj, s)) {
        setGlobalDefault(s, obj[s]);
      }
    });
  }

  // ---- Three-level precedence resolver ----
  function getEffectiveModel(slot, sid) {
    if (!SLOTS.includes(slot)) return '';
    const s = sid || getModelStackScope();
    const a = getSessionOverride(slot, s);
    if (a) return a;
    const b = getGlobalDefault(slot);
    if (b) return b;
    return '';
  }
  function getEffectiveModelStack(sid) {
    const out = {};
    SLOTS.forEach(function(s) { out[s] = getEffectiveModel(s, sid); });
    return out;
  }

  // ---- One-shot migration from legacy global keys ----
  // Binds legacy localStorage values to the currently active session,
  // then clears them. Idempotent (uses a guard flag).
  function migrateLegacyOnce() {
    const flag = 'oa_ms_legacy_migrated_v1';
    if (safeGet(flag)) return false;
    const sid = getModelStackScope();
    if (!sid) return false; // No session yet — wait until one is active.
    let migrated = 0;
    SLOTS.forEach(function(s) {
      const legacy = safeGet(LEGACY_KEYS[s]);
      if (legacy) {
        if (!getSessionOverride(s, sid)) {
          setSessionOverride(s, legacy, sid);
          migrated++;
        }
        safeDel(LEGACY_KEYS[s]);
      }
    });
    safeSet(flag, '1');
    if (migrated > 0) {
      try { console.info('[model-stack] migrated', migrated, 'legacy keys to session', sid); } catch (_) {}
    }
    return true;
  }

  // ---- Persist overrides to backend (best-effort, debounced) ----
  let _persistTimer = null;
  function schedulePersistToBackend() {
    if (_persistTimer) clearTimeout(_persistTimer);
    _persistTimer = setTimeout(persistToBackendNow, 500);
  }
  async function persistToBackendNow() {
    _persistTimer = null;
    const sid = getModelStackScope();
    if (!sid) return;
    const aid = (typeof agentId !== 'undefined' && agentId) ? agentId : 'default';
    const overrides = {};
    SLOTS.forEach(function(s) {
      const v = getSessionOverride(s, sid);
      if (v) overrides[s] = v;
    });
    try {
      await fetch('/api/ui/session/model-stack', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid, agent_id: aid, overrides: overrides }),
      });
    } catch (_) {}
  }

  // ---- Restore overrides from backend on session switch ----
  async function restoreFromBackend(sid, aid) {
    const s = sid || getModelStackScope();
    if (!s) return;
    const a = aid || (typeof agentId !== 'undefined' ? agentId : 'default') || 'default';
    try {
      const r = await fetch('/api/ui/session/model-stack?session_id=' + encodeURIComponent(s) + '&agent_id=' + encodeURIComponent(a));
      if (!r.ok) return;
      const j = await r.json();
      const ov = (j && j.overrides) || {};
      // Clear existing session overrides for this sid, then apply backend ones.
      clearAllSessionOverrides(s);
      SLOTS.forEach(function(slot) {
        // Backend keys are llm_id, vision_llm_id, etc. → slot = strip _id
        const k = slot + '_id';
        if (typeof ov[k] === 'string' && ov[k]) {
          setSessionOverride(slot, ov[k], s);
        }
      });
    } catch (_) {}
  }

  // ---- Expose ----
  window.ModelStackState = {
    SLOTS: SLOTS,
    LEGACY_KEYS: LEGACY_KEYS,
    getModelStackScope: getModelStackScope,
    getSessionOverride: getSessionOverride,
    setSessionOverride: setSessionOverride,
    clearSessionOverride: clearSessionOverride,
    clearAllSessionOverrides: clearAllSessionOverrides,
    listSessionOverrideSlots: listSessionOverrideSlots,
    getGlobalDefault: getGlobalDefault,
    setGlobalDefault: setGlobalDefault,
    getAllGlobalDefaults: getAllGlobalDefaults,
    setAllGlobalDefaults: setAllGlobalDefaults,
    getEffectiveModel: getEffectiveModel,
    getEffectiveModelStack: getEffectiveModelStack,
    migrateLegacyOnce: migrateLegacyOnce,
    schedulePersistToBackend: schedulePersistToBackend,
    persistToBackendNow: persistToBackendNow,
    restoreFromBackend: restoreFromBackend,
  };
})();
