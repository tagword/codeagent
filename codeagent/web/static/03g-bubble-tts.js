/* Bubble text-to-speech: cached playback + MiniMax / browser fallback */

var _bubbleTtsAudio = null;
var _bubbleTtsBtn = null;

function plainTextForTts(raw) {
  var t = String(raw || '');
  if (typeof normReply === 'function') t = normReply(t);
  t = t.replace(/```[\s\S]*?```/g, ' ');
  t = t.replace(/`([^`]+)`/g, '$1');
  t = t.replace(/!\[[^\]]*\]\([^)]*\)/g, '');
  t = t.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1');
  t = t.replace(/^#+\s+/gm, '');
  t = t.replace(/<[^>]+>/g, ' ');
  t = t.replace(/[*_~>#|]/g, ' ');
  t = t.replace(/\s+/g, ' ').trim();
  return t;
}

function ttsCacheKey(plain, settings) {
  return (settings.voice_id || '') + '|' + (settings.model || '') + '|' + plain;
}

function clearBubbleTtsCache(btn) {
  if (!btn) return;
  if (btn._ttsCacheUrl) {
    try { URL.revokeObjectURL(btn._ttsCacheUrl); } catch (_) {}
  }
  btn._ttsCacheKey = null;
  btn._ttsCacheUrl = null;
}

function clearAllBubbleTtsCaches() {
  try {
    document.querySelectorAll('.bubble-tts-btn').forEach(function(btn) {
      clearBubbleTtsCache(btn);
    });
  } catch (_) {}
}

function stopBubbleTtsPlayback() {
  if (_bubbleTtsAudio) {
    try {
      _bubbleTtsAudio.pause();
      _bubbleTtsAudio.currentTime = 0;
    } catch (_) {}
    _bubbleTtsAudio = null;
  }
  if (window.speechSynthesis) {
    try { window.speechSynthesis.cancel(); } catch (_) {}
  }
  if (_bubbleTtsBtn) {
    _bubbleTtsBtn.classList.remove('is-playing');
    _bubbleTtsBtn.setAttribute('aria-label', '朗读');
    _bubbleTtsBtn = null;
  }
}

function speakBubbleWithBrowser(text, btn) {
  if (!window.speechSynthesis) return false;
  stopBubbleTtsPlayback();
  _bubbleTtsBtn = btn;
  btn.classList.add('is-playing');
  btn.setAttribute('aria-label', '停止朗读');
  var u = new SpeechSynthesisUtterance(text);
  u.lang = 'zh-CN';
  u.onend = function() { stopBubbleTtsPlayback(); };
  u.onerror = function() { stopBubbleTtsPlayback(); };
  window.speechSynthesis.speak(u);
  return true;
}

async function playBubbleAudioUrl(url, btn) {
  stopBubbleTtsPlayback();
  _bubbleTtsBtn = btn;
  btn.classList.add('is-playing');
  btn.setAttribute('aria-label', '停止朗读');
  var audio = new Audio(url);
  _bubbleTtsAudio = audio;
  audio.onended = function() { stopBubbleTtsPlayback(); };
  audio.onerror = function() { stopBubbleTtsPlayback(); };
  await audio.play();
}

async function fetchAndCacheBubbleTts(plain, settings, btn) {
  var r = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({
      text: plain,
      voice_id: settings.voice_id || undefined,
      model: settings.model || undefined,
    }),
  });
  if (!r.ok) {
    var err = null;
    try { err = await r.json(); } catch (_) {}
    var detail = (err && err.detail) || r.statusText || 'TTS failed';
    var e = new Error(detail);
    e.fallback = !!(err && err.fallback);
    e.statusCode = (err && err.status_code) || r.status;
    throw e;
  }
  var blob = await r.blob();
  clearBubbleTtsCache(btn);
  var url = URL.createObjectURL(blob);
  btn._ttsCacheKey = ttsCacheKey(plain, settings);
  btn._ttsCacheUrl = url;
  await playBubbleAudioUrl(url, btn);
}

async function toggleBubbleTts(text, btn) {
  if (btn.classList.contains('is-playing')) {
    stopBubbleTtsPlayback();
    return;
  }
  var plain = plainTextForTts(text);
  if (!plain || plain.length < 2) return;
  var settings = typeof getTtsPlaybackSettings === 'function'
    ? getTtsPlaybackSettings()
    : { voice_id: '', model: '' };
  var key = ttsCacheKey(plain, settings);

  if (btn._ttsCacheKey === key && btn._ttsCacheUrl) {
    try {
      await playBubbleAudioUrl(btn._ttsCacheUrl, btn);
    } catch (_) {
      clearBubbleTtsCache(btn);
      await fetchAndCacheBubbleTts(plain, settings, btn);
    }
    return;
  }

  try {
    await fetchAndCacheBubbleTts(plain, settings, btn);
  } catch (e) {
    var usedBrowser = false;
    if (e && e.fallback) {
      usedBrowser = speakBubbleWithBrowser(plain, btn);
    }
    if (typeof systemMsg === 'function') {
      var msg = String((e && e.message) || 'TTS 不可用');
      if (usedBrowser) {
        systemMsg('info', 'MiniMax 朗读失败：' + msg + '（已改用浏览器朗读）');
      } else {
        systemMsg('err', '无法朗读：' + msg);
      }
    } else if (!usedBrowser && !(e && e.fallback)) {
      speakBubbleWithBrowser(plain, btn);
    }
  }
}

async function copyBubbleContent(text, btn) {
  var content = String(text || '');
  if (typeof normReply === 'function') content = normReply(content);
  if (typeof stripOaToolOrphans === 'function') content = stripOaToolOrphans(content);
  if (typeof extractOaToolCallBlocks === 'function') content = extractOaToolCallBlocks(content).text;
  content = content.trim();
  if (!content) return;

  var copied = false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(content);
      copied = true;
    }
  } catch (_) {}

  if (!copied) {
    try {
      if (typeof copyToClipboard === 'function') {
        copyToClipboard(content);
        copied = true;
      } else {
        var ta = document.createElement('textarea');
        ta.value = content;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        copied = true;
      }
    } catch (_) {}
  }

  if (!copied || !btn) return;

  var defaultIcon = btn.innerHTML;
  btn.classList.add('is-copied');
  btn.setAttribute('aria-label', '已复制');
  btn.title = '已复制';
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';
  setTimeout(function() {
    btn.classList.remove('is-copied');
    btn.setAttribute('aria-label', '复制');
    btn.title = '复制内容';
    btn.innerHTML = defaultIcon;
  }, 1500);
}

function appendBubbleTtsBar(col, rawText, opts) {
  opts = opts || {};
  if (!col || opts.role !== 'agent') return;
  var plain = plainTextForTts(rawText);
  if (!plain || plain.length < 2) return;

  var existing = col.querySelector('.bubble-tts-bar');
  if (existing) existing.remove();

  var bar = document.createElement('div');
  bar.className = 'bubble-tts-bar';

  var copyBtn = document.createElement('button');
  copyBtn.type = 'button';
  copyBtn.className = 'bubble-copy-btn';
  copyBtn.title = '复制内容';
  copyBtn.setAttribute('aria-label', '复制');
  copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>';
  copyBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    copyBubbleContent(rawText, copyBtn);
  });

  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'bubble-tts-btn';
  btn.title = '朗读（首次合成，之后复播）';
  btn.setAttribute('aria-label', '朗读');
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 5.636a9 9 0 0 1 0 12.728"/></svg>';
  btn.addEventListener('click', function(e) {
    e.stopPropagation();
    toggleBubbleTts(rawText, btn);
  });

  bar.appendChild(copyBtn);
  bar.appendChild(btn);
  col.appendChild(bar);
}

// ── 代码块复制（全局事件委托） ──
document.addEventListener('click', function(e) {
  var btn = e.target.closest('.code-copy-btn');
  if (!btn) return;
  var wrap = btn.closest('.code-block-wrap');
  if (!wrap) return;
  var code = wrap.querySelector('code');
  if (!code) return;
  var text = code.textContent || '';
  if (!text) return;

  var copied = false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function() { copied = true; }).catch(function() {});
    }
  } catch (_) {}

  if (!copied) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      copied = true;
    } catch (_) {}
  }

  if (!copied || !btn) return;

  var orig = btn.innerHTML;
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';
  btn.classList.add('is-copied');
  setTimeout(function() {
    btn.classList.remove('is-copied');
    btn.innerHTML = orig;
  }, 1500);
});
