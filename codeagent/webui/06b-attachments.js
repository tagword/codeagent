/* Attachment composer: files, folder, paste, drag-drop */

const pendingAttachments = [];
let pendingClearVision = false;

function fileNeedsVision(mime) {
  return mime.startsWith('image/') || mime.startsWith('video/');
}

function fileNeedsAudio(mime) {
  return mime.startsWith('audio/');
}

function fileIsDocOnly(mime) {
  return mime === 'application/pdf' || mime.startsWith('text/');
}

function canStageFile(mime) {
  if (fileIsDocOnly(mime)) return true;
  if (fileNeedsVision(mime)) {
    return typeof visionModelReadyForAttachments === 'function' && visionModelReadyForAttachments();
  }
  if (fileNeedsAudio(mime)) {
    return typeof audioModelReadyForAttachments === 'function' && audioModelReadyForAttachments();
  }
  return typeof visionModelReadyForAttachments === 'function' && visionModelReadyForAttachments();
}

function updateAttachmentUiGate() {
  const visionReady = typeof visionModelReadyForAttachments === 'function' && visionModelReadyForAttachments();
  const audioReady = typeof audioModelReadyForAttachments === 'function' && audioModelReadyForAttachments();
  const btn = document.getElementById('attachBtn');
  const fbtn = document.getElementById('attachFolderBtn');
  if (btn) {
    btn.disabled = !(visionReady || audioReady);
    btn.title = btn.disabled
      ? '请先选择多模态或音频转写模型'
      : '附加图片、视频、音频或文档';
  }
  if (fbtn) {
    fbtn.disabled = !visionReady;
    fbtn.title = visionReady ? '选择文件夹' : '请先选择多模态模型';
  }
  updateVisionContextBar();
}

function updateVisionContextBar() {
  const bar = document.getElementById('visionContextBar');
  if (!bar) return;
  const v = typeof getSelectedVisionModel === 'function' ? getSelectedVisionModel() : '';
  if (!v) {
    bar.style.display = 'none';
    return;
  }
  bar.style.display = 'flex';
  const label = bar.querySelector('.compose__vision-label');
  if (label) {
    const n = pendingAttachments.length;
    const extra = n ? ' · 待发 ' + n + ' 个附件' : '';
    label.textContent = '视觉上下文 · Vision: ' + v + extra;
  }
}

function renderAttachmentPreview() {
  const bar = document.getElementById('composeAttachments');
  if (!bar) return;
  bar.innerHTML = '';
  if (!pendingAttachments.length) {
    bar.style.display = 'none';
    return;
  }
  bar.style.display = 'flex';
  pendingAttachments.forEach(function(item, idx) {
    const chip = document.createElement('span');
    chip.className = 'compose-attach-chip';
    if (item.previewUrl) {
      const img = document.createElement('img');
      img.src = item.previewUrl;
      img.alt = item.filename || '';
      chip.appendChild(img);
    }
    const label = document.createElement('span');
    label.textContent = item.filename || 'file';
    chip.appendChild(label);
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'compose-attach-rm';
    rm.textContent = '×';
    rm.addEventListener('click', function() {
      pendingAttachments.splice(idx, 1);
      renderAttachmentPreview();
    });
    chip.appendChild(rm);
    bar.appendChild(chip);
  });
}

function fileToBase64(file) {
  return new Promise(function(resolve, reject) {
    const r = new FileReader();
    r.onload = function() {
      const s = String(r.result || '');
      const i = s.indexOf(',');
      resolve(i >= 0 ? s.slice(i + 1) : s);
    };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

async function stageFiles(files) {
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    if (!f || !f.size) continue;
    const mime = f.type || '';
    if (mime === 'image/svg+xml') continue;
    if (!canStageFile(mime)) {
      if (fileNeedsAudio(mime)) systemMsg('err', '请先选择音频转写模型');
      else systemMsg('err', '请先选择支持多模态的模型');
      continue;
    }
    try {
      const data_base64 = await fileToBase64(f);
      let previewUrl = '';
      if (mime.startsWith('image/')) previewUrl = URL.createObjectURL(f);
      pendingAttachments.push({
        filename: f.name || 'upload',
        mime: mime,
        data_base64: data_base64,
        previewUrl: previewUrl,
      });
    } catch (_) {}
  }
  renderAttachmentPreview();
}

async function uploadPendingAttachments() {
  if (!pendingAttachments.length) return [];
  const payload = {
    session_id: sessionId,
    agent_id: agentId,
    files: pendingAttachments.map(function(p) {
      return { filename: p.filename, mime: p.mime, data_base64: p.data_base64 };
    }),
  };
  const r = await fetch('/api/attachments/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify(payload),
  });
  const j = await r.json().catch(function() { return {}; });
  if (!r.ok) throw new Error(j.detail || r.statusText);
  if (j.truncated) systemMsg('info', '部分文件因数量上限未上传');
  pendingAttachments.length = 0;
  renderAttachmentPreview();
  return j.attachment_ids || [];
}

(function initAttachmentUi() {
  const fileInput = document.getElementById('attachFileInput');
  const folderInput = document.getElementById('attachFolderInput');
  const attachBtn = document.getElementById('attachBtn');
  const folderBtn = document.getElementById('attachFolderBtn');
  const composeBox = document.querySelector('.compose__box');
  const clearBtn = document.getElementById('visionContextClear');

  attachBtn && attachBtn.addEventListener('click', function() {
    if (fileInput) fileInput.click();
  });
  folderBtn && folderBtn.addEventListener('click', function() {
    if (folderInput) folderInput.click();
  });
  fileInput && fileInput.addEventListener('change', function() {
    if (fileInput.files) stageFiles(Array.from(fileInput.files));
    fileInput.value = '';
  });
  folderInput && folderInput.addEventListener('change', function() {
    if (folderInput.files) stageFiles(Array.from(folderInput.files));
    folderInput.value = '';
  });

  composeBox && composeBox.addEventListener('paste', function(e) {
    const items = (e.clipboardData && e.clipboardData.items) ? Array.from(e.clipboardData.items) : [];
    const files = [];
    items.forEach(function(it) {
      if (it.kind === 'file') {
        const f = it.getAsFile();
        if (f) files.push(f);
      }
    });
    if (files.length) {
      e.preventDefault();
      stageFiles(files);
    }
  });

  composeBox && composeBox.addEventListener('dragover', function(e) {
    e.preventDefault();
  });
  composeBox && composeBox.addEventListener('drop', function(e) {
    e.preventDefault();
    const files = (e.dataTransfer && e.dataTransfer.files) ? Array.from(e.dataTransfer.files) : [];
    if (files.length) stageFiles(files);
  });

  clearBtn && clearBtn.addEventListener('click', function() {
    pendingClearVision = true;
    systemMsg('info', '已标记清除视觉上下文，下次发送生效');
  });

  refreshVisionModelSelect().catch(function() {});
})();

function renderUserAttachmentsInBubble(container, attachments) {
  if (!attachments || !attachments.length) return;
  const wrap = document.createElement('div');
  wrap.className = 'bubble-user__attachments';
  attachments.forEach(function(a) {
    if (!a || a.kind !== 'image') return;
    const img = document.createElement('img');
    img.className = 'bubble-user__img';
    img.alt = a.filename || a.id || '';
    img.src = '/api/attachments/' + encodeURIComponent(a.id)
      + '?session_id=' + encodeURIComponent(sessionId)
      + '&agent_id=' + encodeURIComponent(agentId);
    wrap.appendChild(img);
  });
  if (wrap.childNodes.length) container.insertBefore(wrap, container.firstChild);
}
