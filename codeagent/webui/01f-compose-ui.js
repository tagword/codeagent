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
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen - 1) + '…';
}

function updateComposeModelPill() {
  if (typeof updateComposeModelStackPill === 'function') {
    updateComposeModelStackPill();
    return;
  }
  const pill = document.getElementById('composeModelPillLabel');
  const sel = document.getElementById('modelSelect');
  if (!pill || !sel) return;
  const opt = sel.options[sel.selectedIndex];
  const text = (opt && opt.textContent) ? opt.textContent.trim() : '默认模型';
  pill.textContent = truncateComposeLabel(text, 26);
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
