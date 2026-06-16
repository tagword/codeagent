let _summarizerDefaultId = '';

/** Read env value: prefer CODEAGENT_* (product), fall back to SEED_* if present. */
function _envVal(j, codeagentKey, seedKey, fallback) {
  if (j[codeagentKey] !== undefined && j[codeagentKey] !== null && String(j[codeagentKey]) !== '') return j[codeagentKey];
  if (seedKey && j[seedKey] !== undefined && j[seedKey] !== null && String(j[seedKey]) !== '') return j[seedKey];
  return fallback;
}

/** Populate the summarizer model <select> with LLM presets */
async function populateSummarizerSelect() {
  const sel = document.getElementById('selCompactSummarizer');
  if (!sel) return;
  try {
    const r = await fetch('/api/ui/llm/presets');
    if (!r.ok) return;
    const j = await r.json();
    _summarizerPresetsCache = j.presets || [];
    _summarizerDefaultId = j.default_id || '';
    sel.innerHTML = '';
    (_summarizerPresetsCache).forEach(function(p) {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.model || p.id;
      sel.appendChild(opt);
    });
  } catch (_) {}
}

/** Try to match a preset by base_url+model; return its id or empty string */
function _matchSummarizerPreset(baseUrl, model) {
  if (!baseUrl || !model) return '';
  const b = baseUrl.trim().replace(/\/+$/, '');
  const m = model.trim();
  if (!b || !m) return '';
  for (var i = 0; i < (_summarizerPresetsCache || []).length; i++) {
    var p = _summarizerPresetsCache[i];
    if ((p.base_url || '').replace(/\/+$/, '') === b && (p.model || '').trim() === m) {
      return p.id;
    }
  }
  return '';
}

async function loadChatEnvConfig() {
  const status = document.getElementById('chatEnvStatus');
  if (!status) return;
  status.textContent = '加载中…';
  try {
    await populateSummarizerSelect();
    const r = await fetch('/api/ui/env/chat');
    if (!r.ok) throw new Error(r.statusText);
    const j = await r.json();
    const chkAuto = document.getElementById('chkAutoContinue');
    if (chkAuto) chkAuto.checked = _envVal(j, 'CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT', 'SEED_CHAT_AUTO_CONTINUE_ON_LIMIT', '0') === '1';
    const inpSegments = document.getElementById('inpAutoContinueMax');
    if (inpSegments) {
      inpSegments.value = _envVal(j, 'CODEAGENT_CHAT_AUTO_CONTINUE_MAX_SEGMENTS', 'SEED_CHAT_AUTO_CONTINUE_MAX_SEGMENTS', '4');
      rowAutoContinueToggle();
    }
    const inpRounds = document.getElementById('inpMaxToolRounds');
    if (inpRounds) inpRounds.value = _envVal(j, 'CODEAGENT_CHAT_MAX_TOOL_ROUNDS_DEFAULT', 'SEED_CHAT_MAX_TOOL_ROUNDS_DEFAULT', '16');
    const inpMaxOut = document.getElementById('inpMaxOutputTokens');
    if (inpMaxOut) inpMaxOut.value = _envVal(j, 'CODEAGENT_CHAT_MAX_TOKENS', 'SEED_LLM_MAX_TOKENS', '8192');
    const inpCtxLimit = document.getElementById('inpContextLimit');
    if (inpCtxLimit) inpCtxLimit.value = _envVal(j, 'CODEAGENT_LLM_CONTEXT_SIZE', 'SEED_LLM_CONTEXT_SIZE', '');
    const chkCompact = document.getElementById('chkContextCompact');
    if (chkCompact) chkCompact.checked = _envVal(j, 'CODEAGENT_CONTEXT_COMPACT', 'SEED_CONTEXT_COMPACT', '') === '1';
    const inpMinBytes = document.getElementById('inpCompactMinBytes');
    if (inpMinBytes) inpMinBytes.value = _envVal(j, 'CODEAGENT_CONTEXT_COMPACT_MIN_TOKENS', 'SEED_CONTEXT_COMPACT_MIN_TOKENS', '30000');
    const sel = document.getElementById('selCompactSummarizer');
    if (sel) {
      const matched = _matchSummarizerPreset(
        _envVal(j, 'CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_BASEURL', 'SEED_CONTEXT_COMPACT_SUMMARIZER_BASEURL', ''),
        _envVal(j, 'CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_MODEL', 'SEED_CONTEXT_COMPACT_SUMMARIZER_MODEL', '')
      );
      sel.value = matched || _summarizerDefaultId || '';
    }
    const inpSumMax = document.getElementById('inpCompactSummarizerMaxTokens');
    if (inpSumMax) inpSumMax.value = _envVal(j, 'CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_MAX_TOKENS', 'SEED_CONTEXT_COMPACT_SUMMARIZER_MAX_TOKENS', '4096');
    toggleCompactSubRows();
    status.textContent = '';
    status.classList.remove('is-err');
  } catch (e) { status.classList.add('is-err'); status.textContent = '加载失败：' + String(e); }
}

function rowAutoContinueToggle() {
  const chk = document.getElementById('chkAutoContinue');
  const row = document.getElementById('rowToolRounds');
  if (row) { row.style.display = (chk && chk.checked) ? '' : 'none'; }
}

function toggleCompactSubRows() {
  const chk = document.getElementById('chkContextCompact');
  const rows = document.getElementById('compactSubRows');
  if (rows) { rows.style.display = (chk && chk.checked) ? '' : 'none'; }
}

document.addEventListener('change', function(ev) {
  if (ev.target.id === 'chkAutoContinue') rowAutoContinueToggle();
  if (ev.target.id === 'chkContextCompact') toggleCompactSubRows();
});

(function () {
  var btn = document.getElementById('btnChatEnvSave');
  if (!btn) return;
  btn.addEventListener('click', async function () {
    var status = document.getElementById('chatEnvStatus');
    if (!status) return;
    status.textContent = '保存中…';
    status.classList.remove('is-err');
    try {
      var sumBaseUrl = '';
      var sumModel = '';
      var sel = document.getElementById('selCompactSummarizer');
      if (sel && sel.value) {
        for (var i = 0; i < (_summarizerPresetsCache || []).length; i++) {
          if (_summarizerPresetsCache[i].id === sel.value) {
            sumBaseUrl = _summarizerPresetsCache[i].base_url || '';
            sumModel = _summarizerPresetsCache[i].model || '';
            break;
          }
        }
      }
      var chkAuto = document.getElementById('chkAutoContinue');
      var inpSeg = document.getElementById('inpAutoContinueMax');
      var inpRounds = document.getElementById('inpMaxToolRounds');
      var inpMaxOut = document.getElementById('inpMaxOutputTokens');
      var inpCtxLimit = document.getElementById('inpContextLimit');
      var chkCompact = document.getElementById('chkContextCompact');
      var inpMinB = document.getElementById('inpCompactMinBytes');
      var inpSumMax = document.getElementById('inpCompactSummarizerMaxTokens');
      var body = {
        CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT: chkAuto && chkAuto.checked ? '1' : '0',
        CODEAGENT_CHAT_AUTO_CONTINUE_MAX_SEGMENTS: String(parseInt(inpSeg && inpSeg.value, 10) || 0),
        CODEAGENT_CHAT_MAX_TOOL_ROUNDS_DEFAULT: String(parseInt(inpRounds && inpRounds.value, 10) || 16),
        CODEAGENT_CHAT_MAX_TOKENS: String(parseInt(inpMaxOut && inpMaxOut.value, 10) || 8192),
        CODEAGENT_LLM_CONTEXT_SIZE: String(parseInt(inpCtxLimit && inpCtxLimit.value, 10) || ''),
        CODEAGENT_CONTEXT_COMPACT: chkCompact && chkCompact.checked ? '1' : '',
        CODEAGENT_CONTEXT_COMPACT_MIN_TOKENS: String(parseInt(inpMinB && inpMinB.value, 10) || 30000),
        CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_BASEURL: sumBaseUrl,
        CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_MODEL: sumModel,
        CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_MAX_TOKENS: String(parseInt(inpSumMax && inpSumMax.value, 10) || 4096),
      };
      var r = await fetch('/api/ui/env/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok) throw new Error(j.detail || r.statusText);
      status.textContent = j.hint || '已保存';
      status.classList.remove('is-err');
      // 同步更新 context_limit 指示器分母
      var cl = parseInt(inpCtxLimit && inpCtxLimit.value, 10) || 0;
      if (cl > 0 && typeof setTokenContextMax === 'function') setTokenContextMax(cl);
    } catch (e) {
      status.classList.add('is-err');
      status.textContent = '保存失败：' + String(e);
    }
  });
})();
