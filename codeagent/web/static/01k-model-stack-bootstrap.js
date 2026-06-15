/* ================================================================
 * 01k-model-stack-bootstrap.js
 *   Boot-time wiring for the per-session model stack.
 *   Listens to the existing 'session-changed' CustomEvent
 *   dispatched by 01c-session.js and:
 *     1) migrates any legacy global keys (F7) on first session
 *     2) restores backend overrides into session storage
 *     3) refreshes the 6 selectors so the dropdown values match
 * ================================================================ */

(function bootstrapModelStack() {
  if (!window.ModelStackState) return;  // 01k-state.js must load first

  const MS = window.ModelStackState;
  const SLOTS = MS.SLOTS;

  // Re-apply all 6 selectors' current values from ModelStackState.
  function applyEffectiveToSelectors() {
    if (typeof refreshModelSelect === 'function')           refreshModelSelect();
    if (typeof refreshVisionModelSelect === 'function')     refreshVisionModelSelect();
    if (typeof refreshImageGenModelSelect === 'function')  refreshImageGenModelSelect();
    if (typeof refreshAudioModelSelect === 'function')     refreshAudioModelSelect();
    if (typeof refreshMusicModelSelect === 'function')     refreshMusicModelSelect();
    if (typeof refreshVideoGenModelSelect === 'function')  refreshVideoGenModelSelect();
  }

  async function onSessionChanged(sid) {
    try {
      // F7: one-shot migration of legacy global keys → bind to current session
      MS.migrateLegacyOnce();
      // Restore any backend-persisted overrides for this session
      await MS.restoreFromBackend(sid);
      // Apply the effective (session → global → empty) values to dropdowns
      applyEffectiveToSelectors();
      // Refresh the pill/badge so 📌 shows up
      if (typeof updateComposeModelPill === 'function') {
        updateComposeModelPill();
      } else if (typeof updateComposeModelStackPill === 'function') {
        updateComposeModelStackPill();
      }
    } catch (e) {
      try { console.warn('[model-stack] onSessionChanged failed', e); } catch (_) {}
    }
  }

  // Listen for session changes (01c-session.js dispatches this).
  window.addEventListener('session-changed', function(ev) {
    const sid = ev && ev.detail && ev.detail.sessionId;
    if (sid) onSessionChanged(sid);
  });

  // Also handle initial load (event already fired before this listener attached)
  document.addEventListener('DOMContentLoaded', function() {
    // Defer one tick so sessionId is assigned
    setTimeout(function() {
      const sid = MS.getModelStackScope();
      if (sid) onSessionChanged(sid);
    }, 0);
  });

  // Expose for manual triggers (e.g. after "clear all overrides")
  window.refreshModelStackUi = function() {
    applyEffectiveToSelectors();
    if (typeof updateComposeModelPill === 'function') updateComposeModelPill();
  };
})();
