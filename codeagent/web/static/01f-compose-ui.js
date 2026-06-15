/* Compose UI: multimodal model select refresh, attachment thumbnail rendering
   for chat & activity bar compose surfaces. */

async function refreshMultimodalModelSelects() {
  if (typeof refreshModelSelect === 'function') {
    await refreshModelSelect();
  } else if (typeof refreshChatModelSelect === 'function') {
    await refreshChatModelSelect();
  }
  if (typeof refreshTtsOptions === 'function') {
    await refreshTtsOptions().catch(function() {});
  }
  if (typeof refreshComposeModelStackUi === 'function') {
    refreshComposeModelStackUi();
  }
}

function truncateComposeLabel(text, maxLen) {
  const s = String(text || '').trim();
  const cap = typeof maxLen === 'number' ? maxLen : 20;
  if (s.length <= cap) return s;
  return s.slice(0, cap - 1) + '…';
}

function composePillMaxLenFallback() {
  try {
    return window.matchMedia('(max-width: 768px)').matches ? 12 : 20;
  } catch (_) {
    return 20;
  }
}

function updateComposeModelPill() {
  if (typeof updateComposeModelStackPill === 'function') {
    updateComposeModelStackPill();
    return;
  }
  const pill = document.getElementById('composeModelPillLabel');
  const sel = document.getElementById('modelSelect');
  if (!pill || !sel) return;
  const text = (typeof getChatMainDisplayLabel === 'function')
    ? getChatMainDisplayLabel(sel)
    : ((sel.options[sel.selectedIndex] && sel.options[sel.selectedIndex].textContent) || '默认模型').trim();
  pill.textContent = truncateComposeLabel(text, typeof composePillMaxLen === 'function' ? composePillMaxLen() : composePillMaxLenFallback());
  pill.title = text;
  const trigger = document.getElementById('composeModelTrigger');
  if (trigger) trigger.title = '当前：' + text;
}

function setComposeSettingsOpen(open) {
  const sheet = document.getElementById('composeSettingsSheet');
  const trigger = document.getElementById('composeModelTrigger');
  const box = document.getElementById('composeBox');
  if (!sheet || !trigger) return;
  sheet.hidden = !open;
  trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
  trigger.classList.toggle('is-open', open);
  if (box) box.classList.toggle('compose__box--sheet-open', open);
}

function toggleComposeSettings() {
  const sheet = document.getElementById('composeSettingsSheet');
  setComposeSettingsOpen(!!(sheet && sheet.hidden));
}

(function initComposeUi() {
  const trigger = document.getElementById('composeModelTrigger');
  const closeBtn = document.getElementById('composeSettingsClose');
  const box = document.getElementById('composeBox');
  const sel = document.getElementById('modelSelect');

  trigger && trigger.addEventListener('click', function(e) {
    e.stopPropagation();
    toggleComposeSettings();
  });
  closeBtn && closeBtn.addEventListener('click', function() {
    setComposeSettingsOpen(false);
  });
  document.addEventListener('click', function() {
    setComposeSettingsOpen(false);
  });
  box && box.addEventListener('click', function(e) {
    e.stopPropagation();
  });
  sel && sel.addEventListener('change', updateComposeModelPill);

  updateComposeModelPill();
})();
