/* Attachment composer: files, folder, paste, drag-drop */

const pendingAttachments = [];

function fileNeedsVision(mime) {
  return mime.startsWith('image/') || mime.startsWith('video/');
}

function fileNeedsImageOnly(mime) {
  return mime.startsWith('image/');
}

function fileNeedsVideo(mime) {
  return mime.startsWith('video/');
}

function fileNeedsAudio(mime) {
  return mime.startsWith('audio/');
}

function fileIsDocOnly(mime) {
  return mime === 'application/pdf' || mime.startsWith('text/');
}

function canStageFile(mime) {
  if (fileIsDocOnly(mime)) return true;
  if (fileNeedsImageOnly(mime)) {
    return typeof attachmentImageReady === 'function' && attachmentImageReady();
  }
  if (fileNeedsVideo(mime)) {
    return typeof attachmentVideoReady === 'function' && attachmentVideoReady();
  }
  if (fileNeedsAudio(mime)) {
    return typeof audioModelReadyForAttachments === 'function' && audioModelReadyForAttachments();
  }
  return typeof attachmentImageReady === 'function' && attachmentImageReady();
}

function updateAttachmentUiGate() {
  const imageReady = typeof attachmentImageReady === 'function' && attachmentImageReady();
  const videoReady = typeof attachmentVideoReady === 'function' && attachmentVideoReady();
  const audioReady = typeof audioModelReadyForAttachments === 'function' && audioModelReadyForAttachments();
  const enabled = imageReady || videoReady || audioReady;
  const btnInline = document.getElementById('attachBtnInline');
  if (btnInline) {
    if (enabled) {
      btnInline.classList.remove('is-disabled');
      btnInline.title = '附加文件、拍照或录制视频';
    } else {
      btnInline.classList.add('is-disabled');
      btnInline.title = '请先配置识图（多模态 LLM 或 MiniMax MCP）或音频转写';
    }
  }
}

function updateComposeHeadVisibility() {
  const head = document.getElementById('composeHead');
  const att = document.getElementById('composeAttachments');
  if (!head || !att) return;
  head.hidden = att.style.display === 'none';
}

function renderAttachmentPreview() {
  const bar = document.getElementById('composeAttachments');
  if (!bar) return;
  bar.innerHTML = '';
  if (!pendingAttachments.length) {
    bar.style.display = 'none';
    updateComposeHeadVisibility();
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
    } else {
      chip.classList.add('compose-attach-chip--file');
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
  updateComposeHeadVisibility();
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
      else systemMsg('err', '请先配置识图（多模态 LLM 或 MiniMax MCP）');
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
  const nativeCameraInput = document.getElementById('nativeCameraInput');
  const nativeVideoInput = document.getElementById('nativeVideoInput');
  const composeBox = document.querySelector('.compose__box');
  const attachBtn = document.getElementById('attachBtnInline');
  const popup = document.getElementById('attachPopup');

  let popupOpen = false;

  function openPopup() {
    if (!popup || !attachBtn) return;
    var rect = attachBtn.getBoundingClientRect();
    popup.style.display = 'flex';
    popup.style.flexDirection = 'column';
    popup.style.left = Math.max(4, rect.left) + 'px';
    popup.style.bottom = (window.innerHeight - rect.top + 6) + 'px';
    popupOpen = true;
  }

  function closePopup() {
    popupOpen = false;
    if (popup) popup.style.display = 'none';
  }

  function togglePopup(e) {
    e.stopPropagation();
    if (popupOpen) { closePopup(); return; }
    openPopup();
  }

  // "+" 按钮点击切换弹出菜单
  attachBtn && attachBtn.addEventListener('click', togglePopup);

  // 弹出菜单选项点击
  popup && popup.addEventListener('click', function(e) {
    const option = e.target.closest('.compose__attach-option');
    if (!option) return;
    const action = option.getAttribute('data-action');
    closePopup();
    if (action === 'file' && fileInput) {
      fileInput.click();
    } else if (action === 'camera') {
      if (typeof openCameraModal === 'function') {
        openCameraModal('photo');
      } else if (nativeCameraInput) {
        nativeCameraInput.click();
      }
    } else if (action === 'video') {
      if (typeof openCameraModal === 'function') {
        openCameraModal('video');
      } else if (nativeVideoInput) {
        nativeVideoInput.click();
      }
    }
  });

  // 点击外部关闭弹出菜单
  document.addEventListener('click', function(e) {
    if (!popupOpen) return;
    if (attachBtn && attachBtn.contains(e.target)) return;
    if (popup && popup.contains(e.target)) return;
    closePopup();
  });

  // 按 Escape 关闭
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && popupOpen) closePopup();
  });

  // 文件输入变化处理
  fileInput && fileInput.addEventListener('change', function() {
    if (fileInput.files) stageFiles(Array.from(fileInput.files));
    fileInput.value = '';
  });
  folderInput && folderInput.addEventListener('change', function() {
    if (folderInput.files) stageFiles(Array.from(folderInput.files));
    folderInput.value = '';
  });
  nativeCameraInput && nativeCameraInput.addEventListener('change', function() {
    if (nativeCameraInput.files && nativeCameraInput.files.length && typeof stageFiles === 'function') {
      stageFiles(Array.from(nativeCameraInput.files));
    }
    nativeCameraInput.value = '';
  });
  nativeVideoInput && nativeVideoInput.addEventListener('change', function() {
    if (nativeVideoInput.files && nativeVideoInput.files.length && typeof stageFiles === 'function') {
      stageFiles(Array.from(nativeVideoInput.files));
    }
    nativeVideoInput.value = '';
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

  refreshVisionModelSelect().catch(function() {});
})();

/* "⋮" 更多菜单 (模型选择 + 思考) */
(function initMorePopup() {
  const moreBtn = document.getElementById('moreBtn');
  const popup = document.getElementById('morePopup');
  let popupOpen = false;

  function openPopup() {
    if (!popup || !moreBtn) return;
    var rect = moreBtn.getBoundingClientRect();
    popup.style.display = 'flex';
    popup.style.flexDirection = 'column';
    popup.style.right = (window.innerWidth - rect.right + 4) + 'px';
    popup.style.bottom = (window.innerHeight - rect.top + 4) + 'px';
    popupOpen = true;
  }

  function closePopup() {
    popupOpen = false;
    if (popup) popup.style.display = 'none';
  }

  function togglePopup(e) {
    e.stopPropagation();
    if (popupOpen) { closePopup(); return; }
    openPopup();
  }

  moreBtn && moreBtn.addEventListener('click', togglePopup);

  // 模型选择点击 → 打开设置面板
  const modelTrigger = document.getElementById('composeModelTrigger');
  if (modelTrigger) {
    modelTrigger.addEventListener('click', function(e) {
      closePopup();
      if (typeof toggleComposeSettings === 'function') {
        toggleComposeSettings();
      }
    });
  }

  // 思考开关
  const thinkToggleBtn = document.getElementById('thinkToggle');
  if (thinkToggleBtn) {
    thinkToggleBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      // setThinkState is already bound in 01c-session.js
      // Just let the existing listener fire; update visual state
    });
  }

  // 点击外部关闭
  document.addEventListener('click', function(e) {
    if (!popupOpen) return;
    if (moreBtn && moreBtn.contains(e.target)) return;
    if (popup && popup.contains(e.target)) return;
    closePopup();
  });

  // Escape 关闭
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && popupOpen) closePopup();
  });
})();

function renderUserAttachmentsInBubble(container, attachments) {
  if (!attachments || !attachments.length) return;
  const wrap = document.createElement('div');
  wrap.className = 'bubble-user__attachments';
  attachments.forEach(function(a) {
    if (!a || a.kind !== 'image') return;
    const img = document.createElement('img');
    img.className = 'chat-inline-img bubble-user__img';
    img.alt = a.filename || a.id || '';
    img.src = '/api/attachments/' + encodeURIComponent(a.id)
      + '?session_id=' + encodeURIComponent(sessionId)
      + '&agent_id=' + encodeURIComponent(agentId);
    wrap.appendChild(img);
  });
  if (wrap.childNodes.length) {
    container.insertBefore(wrap, container.firstChild);
    if (typeof enhanceChatImagesInBubble === 'function') enhanceChatImagesInBubble(wrap);
  }
}
