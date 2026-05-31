const TTS_VOICE_KEY = 'oa_tts_voice_id';
const TTS_MODEL_KEY = 'oa_tts_model';

function getSelectedTtsVoice() {
  try { return localStorage.getItem(TTS_VOICE_KEY) || ''; } catch (_) { return ''; }
}

function setSelectedTtsVoice(val) {
  try { localStorage.setItem(TTS_VOICE_KEY, String(val || '').trim()); } catch (_) {}
}

function getSelectedTtsModel() {
  try { return localStorage.getItem(TTS_MODEL_KEY) || ''; } catch (_) { return ''; }
}

function setSelectedTtsModel(val) {
  try { localStorage.setItem(TTS_MODEL_KEY, String(val || '').trim()); } catch (_) {}
}

function getTtsPlaybackSettings() {
  var voiceSel = document.getElementById('ttsVoiceSelect');
  var modelSel = document.getElementById('ttsModelSelect');
  return {
    voice_id: (voiceSel && voiceSel.value) || getSelectedTtsVoice() || '',
    model: (modelSel && modelSel.value) || getSelectedTtsModel() || '',
  };
}

function populateTtsSelects(data) {
  var voiceSel = document.getElementById('ttsVoiceSelect');
  var modelSel = document.getElementById('ttsModelSelect');
  var hint = document.getElementById('ttsVoiceHint');
  if (!voiceSel || !modelSel) return;

  var configured = !!(data && data.configured);
  var voices = (data && data.voices) || [];
  var models = (data && data.models) || [];
  var curVoice = getSelectedTtsVoice() || (data && data.default_voice_id) || '';
  var curModel = getSelectedTtsModel() || (data && data.default_model) || '';

  voiceSel.innerHTML = '';
  modelSel.innerHTML = '';

  if (!configured) {
    voiceSel.disabled = true;
    modelSel.disabled = true;
    var o1 = document.createElement('option');
    o1.value = '';
    o1.textContent = '需 MiniMax API Key（LLM 预设或 MCP）';
    voiceSel.appendChild(o1);
    var o2 = document.createElement('option');
    o2.value = '';
    o2.textContent = '需 MiniMax API Key（LLM 预设或 MCP）';
    modelSel.appendChild(o2);
    if (hint) hint.style.display = '';
    return;
  }

  voiceSel.disabled = false;
  modelSel.disabled = false;
  if (hint) hint.style.display = '';

  var groups = {};
  voices.forEach(function(v) {
    var lang = v.lang || '其他';
    if (!groups[lang]) groups[lang] = [];
    groups[lang].push(v);
  });
  Object.keys(groups).sort().forEach(function(lang) {
    var og = document.createElement('optgroup');
    og.label = lang;
    groups[lang].forEach(function(v) {
      var o = document.createElement('option');
      o.value = v.id;
      o.textContent = v.name + ' · ' + v.id;
      if (v.id === curVoice) o.selected = true;
      og.appendChild(o);
    });
    voiceSel.appendChild(og);
  });
  if (curVoice && !Array.from(voiceSel.options).some(function(o) { return o.value === curVoice; })) {
    var extra = document.createElement('option');
    extra.value = curVoice;
    extra.textContent = curVoice + '（自定义）';
    extra.selected = true;
    voiceSel.insertBefore(extra, voiceSel.firstChild);
  }
  if (!voiceSel.value && data.default_voice_id) {
    voiceSel.value = data.default_voice_id;
    setSelectedTtsVoice(voiceSel.value);
  }

  models.forEach(function(m) {
    var o = document.createElement('option');
    o.value = m.id;
    o.textContent = m.name || m.id;
    if (m.id === curModel) o.selected = true;
    modelSel.appendChild(o);
  });
  if (!modelSel.value && data.default_model) {
    modelSel.value = data.default_model;
    setSelectedTtsModel(modelSel.value);
  }
}

async function refreshTtsOptions() {
  try {
    var r = await fetch('/api/ui/tts/options');
    if (!r.ok) return;
    var j = await r.json();
    populateTtsSelects(j);
  } catch (_) {}
}

(function initTtsSettings() {
  var voiceSel = document.getElementById('ttsVoiceSelect');
  var modelSel = document.getElementById('ttsModelSelect');
  refreshTtsOptions().catch(function() {});

  voiceSel && voiceSel.addEventListener('change', function() {
    setSelectedTtsVoice(voiceSel.value);
    if (typeof clearAllBubbleTtsCaches === 'function') clearAllBubbleTtsCaches();
  });
  modelSel && modelSel.addEventListener('change', function() {
    setSelectedTtsModel(modelSel.value);
    if (typeof clearAllBubbleTtsCaches === 'function') clearAllBubbleTtsCaches();
  });
})();
